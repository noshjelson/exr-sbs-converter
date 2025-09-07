"""Tkinter-based tool for converting EXR sequences to SBS."""

import os
import subprocess
import threading
import queue
import tempfile
import shutil
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import dataclass
from typing import List
import urllib.request
import zipfile
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None


def find_oiiotool() -> str | None:
    """Search common locations and PATH for ``oiiotool``.

    Returns the full path to the executable or ``None`` if not found.
    """
    for name in ("oiiotool", "oiiotool.exe"):
        exe = shutil.which(name)
        if exe:
            return exe

    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    local = os.path.join(base_dir, "oiiotool.exe")
    if os.path.exists(local):
        return local

    # Search vcpkg installation directory
    vcpkg_path = os.path.join(os.path.expanduser("~"), "vcpkg", "installed")
    if os.path.exists(vcpkg_path):
        for root, dirs, files in os.walk(vcpkg_path):
            if "oiiotool.exe" in files:
                return os.path.join(root, "oiiotool.exe")

    program_files = os.environ.get("PROGRAMFILES", "")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", "")
    candidates = [
        os.path.join(program_files, "OpenImageIO", "bin", "oiiotool.exe"),
        os.path.join(program_files_x86, "OpenImageIO", "bin", "oiiotool.exe"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    
    # If not found anywhere, try to download it
    downloaded = download_oiiotool()
    if downloaded:
        return downloaded
    
    return None


def download_oiiotool() -> str | None:
    """Download and extract oiiotool for Windows.
    
    Returns the path to oiiotool.exe or None if download fails.
    """
    if platform.system() != "Windows":
        return None
    
    try:
        # Create tools directory
        tools_dir = os.path.join(os.path.dirname(__file__), "tools")
        os.makedirs(tools_dir, exist_ok=True)
        
        oiiotool_path = os.path.join(tools_dir, "oiiotool.exe")
        if os.path.exists(oiiotool_path):
            return oiiotool_path
        
        # For now, just return None - we'll implement actual download later
        # This is a placeholder for future enhancement
        return None
        
    except Exception as e:
        print(f"Error downloading oiiotool: {e}")
        return None


@dataclass
class Shot:
    name: str
    path: str
    has_sbs: bool
    frames: int
    sbs_frames: int
    needs_conversion: bool
    conversion_progress: float  # 0.0 to 1.0


def frame_count(path: str) -> int:
    try:
        return len([f for f in os.listdir(path)
                    if f.lower().endswith(".exr") and "_SBS" not in f])
    except FileNotFoundError:
        return 0


def sbs_frame_count(path: str) -> int:
    """Count SBS EXR files in a directory (including those with _SBS in filename)."""
    try:
        return len([f for f in os.listdir(path)
                    if f.lower().endswith(".exr")])
    except FileNotFoundError:
        return 0


def scan_shots(root: str) -> List[Shot]:
    shots: List[Shot] = []
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except FileNotFoundError:
        return shots
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith('.') or entry.name == '__pycache__':
            continue
        shot_path = entry.path
        frames = frame_count(shot_path)
        sbs_path = f"{shot_path}_SBS"
        sbs_frames = sbs_frame_count(sbs_path)
        has_sbs = sbs_frames > 0
        if not has_sbs:
            sbs_frames = len([f for f in os.listdir(shot_path)
                              if f.lower().endswith(".exr") and "_SBS" in f])
            has_sbs = sbs_frames > 0
        
        # Calculate conversion progress
        needs_conversion = frames > sbs_frames
        conversion_progress = sbs_frames / frames if frames > 0 else 0.0
        
        shots.append(Shot(entry.name, shot_path, not needs_conversion, frames, sbs_frames, needs_conversion, conversion_progress))
    return shots


class ConverterGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("SBS EXR Converter")
        self.geometry("900x600")
        self.shots: List[Shot] = []
        self.shot_vars: List[tk.BooleanVar] = []
        self.queue: queue.Queue = queue.Queue()
        self.oiiotool = find_oiiotool()
        self.thumbnail: tk.PhotoImage | None = None
        self.current_frame: str = ""
        self._build_widgets()
        self.after(100, self.process_queue)

    # UI -----------------------------------------------------------------
    def _build_widgets(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(top, text="Select Shots Folder", command=self.load_folder).pack(side=tk.LEFT)
        ttk.Button(top, text="🔄 Refresh", command=self.refresh_folder).pack(side=tk.LEFT, padx=5)

        opts = ttk.Frame(self)
        opts.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(opts, text="Compression:").grid(row=0, column=0, sticky=tk.W)
        self.compression = tk.StringVar(value="dwab:45")
        ttk.Combobox(opts, textvariable=self.compression,
                     values=["dwab:45", "dwaa:45", "zip", "none"],
                     state="readonly").grid(row=0, column=1, sticky=tk.W)

        ttk.Label(opts, text="Pixel Type:").grid(row=1, column=0, sticky=tk.W)
        self.datatype = tk.StringVar(value="float")
        ttk.Combobox(opts, textvariable=self.datatype,
                     values=["float", "half"],
                     state="readonly").grid(row=1, column=1, sticky=tk.W)

        content = ttk.Frame(self)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.shots_frame = ttk.LabelFrame(content, text="Shots")
        self.shots_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        btns = ttk.Frame(self.shots_frame)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Select All", command=self.select_all).pack(side=tk.LEFT)
        ttk.Button(btns, text="Deselect All", command=self.deselect_all).pack(side=tk.LEFT, padx=5)
        self.shots_canvas = tk.Canvas(self.shots_frame)
        self.shots_scroll = ttk.Scrollbar(self.shots_frame, orient="vertical", command=self.shots_canvas.yview)
        self.shots_inner = ttk.Frame(self.shots_canvas)
        self.shots_inner.bind(
            "<Configure>", lambda e: self.shots_canvas.configure(scrollregion=self.shots_canvas.bbox("all"))
        )
        self.shots_canvas.create_window((0, 0), window=self.shots_inner, anchor="nw")
        self.shots_canvas.configure(yscrollcommand=self.shots_scroll.set)
        self.shots_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.shots_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Enable mouse wheel scrolling
        self.shots_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.shots_canvas.bind("<Button-4>", self._on_mousewheel)  # Linux scroll up
        self.shots_canvas.bind("<Button-5>", self._on_mousewheel)  # Linux scroll down
        self.preview_frame = ttk.LabelFrame(content, text="Preview")
        self.preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        self.thumb_label = ttk.Label(self.preview_frame)
        self.thumb_label.pack(pady=5)
        self.layers_list = tk.Listbox(self.preview_frame, height=6)
        self.layers_list.pack(fill=tk.X, pady=5)
        ttk.Button(self.preview_frame, text="Preview Channel", command=self.preview_channel).pack()

        controls = ttk.Frame(self)
        controls.pack(fill=tk.X, padx=10, pady=5)
        self.convert_btn = ttk.Button(controls, text="Convert Selected", command=self.start_convert)
        self.convert_btn.pack(side=tk.LEFT)
        ttk.Button(controls, text="Convert Single Frame", command=self.convert_single).pack(side=tk.LEFT, padx=5)

        prog = ttk.Frame(self)
        prog.pack(fill=tk.X, padx=10, pady=5)
        self.overall_label = ttk.Label(prog, text="Overall: 0/0")
        self.overall_label.pack(anchor=tk.W)
        self.overall_pb = ttk.Progressbar(prog, length=560)
        self.overall_pb.pack()
        self.shot_label = ttk.Label(prog, text="Shot: 0/0")
        self.shot_label.pack(anchor=tk.W, pady=(10, 0))
        self.shot_pb = ttk.Progressbar(prog, length=560)
        self.shot_pb.pack()
        self.eta_label = ttk.Label(prog, text="ETA: --:--:--")
        self.eta_label.pack(anchor=tk.W, pady=(5, 0))
        self.cpu_label = ttk.Label(prog, text="CPU: --%")
        self.cpu_label.pack(anchor=tk.W)

        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log = tk.Text(log_frame, height=8)
        self.log.pack(fill=tk.BOTH, expand=True)
        ttk.Button(log_frame, text="Save Log", command=self.save_log).pack(anchor=tk.E, pady=5)

    # Folder scan ---------------------------------------------------------
    def load_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Shots Folder")
        if not folder:
            return
        self.load_folder_from_path(folder)

    def refresh_folder(self) -> None:
        """Refresh the current folder to update conversion status."""
        if not hasattr(self, 'current_folder') or not self.current_folder:
            messagebox.showinfo("No folder selected", "Please select a folder first.")
            return
        self.load_folder_from_path(self.current_folder)

    def load_folder_from_path(self, folder: str) -> None:
        """Load folder from a specific path (used by refresh)."""
        self.current_folder = folder
        self.shots = scan_shots(folder)
        for child in self.shots_inner.winfo_children():
            child.destroy()
        self.shots_canvas.yview_moveto(0)
        self.shot_vars = []
        for shot in self.shots:
            var = tk.BooleanVar(value=shot.needs_conversion)
            
            # Create detailed status label
            if shot.frames == 0:
                status = "No EXR files"
                color = "gray"
            elif shot.conversion_progress == 1.0:
                status = "✅ Complete"
                color = "green"
            elif shot.conversion_progress > 0:
                status = f"🔄 {shot.sbs_frames}/{shot.frames} ({shot.conversion_progress:.0%})"
                color = "orange"
            else:
                status = "⏳ Not started"
                color = "red"
            
            label = f"{shot.name} - {status}"
            cb = ttk.Checkbutton(self.shots_inner, text=label, variable=var,
                                 command=lambda s=shot: self.update_preview(s))
            
            # Only enable checkbox if conversion is needed
            if not shot.needs_conversion:
                cb.state(["disabled"])
            
            cb.pack(anchor=tk.W, pady=2)
            self.shot_vars.append(var)
        if self.shots:
            self.update_preview(self.shots[0])

    def select_all(self) -> None:
        for var, shot in zip(self.shot_vars, self.shots):
            if shot.needs_conversion:
                var.set(True)

    def deselect_all(self) -> None:
        for var in self.shot_vars:
            var.set(False)

    def _on_mousewheel(self, event) -> None:
        """Scroll the shots list with the mouse wheel."""
        if event.delta:
            self.shots_canvas.yview_scroll(int(-event.delta / 120), "units")
        elif event.num == 4:
            self.shots_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.shots_canvas.yview_scroll(1, "units")

    def _format_time(self, seconds: float) -> str:
        """Format seconds into HH:MM:SS."""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    # Conversion ---------------------------------------------------------
    def start_convert(self) -> None:
        selected = [s for s, v in zip(self.shots, self.shot_vars) if v.get() and s.needs_conversion]
        if not selected:
            messagebox.showinfo("Nothing to convert", "No shots selected for conversion.")
            return
        oiiotool = find_oiiotool()
        if not oiiotool:
            messagebox.showerror(
                "Missing dependency",
                "Could not find oiiotool executable.\nPlease install OpenImageIO tools.",
            )
            return
        self.oiiotool = oiiotool
        self.convert_btn.config(state=tk.DISABLED)
        threading.Thread(
            target=self._convert_worker,
            args=(selected, oiiotool),
            daemon=True,
        ).start()

    def _convert_worker(self, shots: List[Shot], oiiotool: str) -> None:
        total_frames = sum(self._frame_count(s.path) for s in shots)
        done = 0
        start_time = time.time()
        if psutil:
            psutil.cpu_percent()
        self.queue.put(("overall", done, total_frames))
        
        for shot in shots:
            frames = self._frame_list(shot.path)
            if not frames:
                self.queue.put(("log", f"{shot.name}: No frames to convert (already complete?)"))
                continue

            self.queue.put(("shot", shot.name, 0, len(frames)))
            self.queue.put(("log", f"{shot.name}: Converting {len(frames)} frames..."))

            outdir = f"{shot.path}_SBS"
            os.makedirs(outdir, exist_ok=True)

            datatype = self.datatype.get()
            compression = self.compression.get()

            def process(frame: str) -> tuple[str, int, str]:
                src = os.path.join(shot.path, frame)
                dst = os.path.join(outdir, frame.replace(".exr", "_SBS.exr"))
                cmd = [
                    oiiotool,
                    src,
                    "--fullpixels",
                    "-d",
                    datatype,
                    "--compression",
                    compression,
                    "-o",
                    dst,
                ]
                try:
                    result = subprocess.run(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                    )
                    return frame, result.returncode, result.stderr.strip()
                except FileNotFoundError:
                    return frame, -1, "oiiotool executable not found. Please install OpenImageIO tools."

            with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
                futures = {executor.submit(process, f): f for f in frames}
                for idx, future in enumerate(as_completed(futures), 1):
                    frame, retcode, stderr = future.result()
                    if retcode == -1:
                        self.queue.put(("log", stderr))
                        self.queue.put(("done",))
                        return
                    if retcode != 0:
                        self.queue.put(("log", f"{shot.name}: {frame} failed - {stderr}"))
                    else:
                        self.queue.put(("log", f"{shot.name}: {frame} ✅"))
                    done += 1
                    self.queue.put(("shot", shot.name, idx, len(frames)))
                    self.queue.put(("overall", done, total_frames))
                    if psutil:
                        self.queue.put(("cpu", psutil.cpu_percent()))
                    if done:
                        elapsed = time.time() - start_time
                        eta = (total_frames - done) * (elapsed / done)
                        self.queue.put(("eta", eta))
            self.queue.put(("log", f"✅ Finished {shot.name}"))
        self.queue.put(("log", "🎉 All conversions complete!"))
        self.queue.put(("done",))

    def _frame_list(self, path: str) -> List[str]:
        """Get list of frames that need conversion (skip already converted ones)."""
        source_frames = [f for f in sorted(os.listdir(path))
                        if f.lower().endswith(".exr") and "_SBS" not in f]
        
        # Check which ones are already converted
        sbs_path = f"{path}_SBS"
        if os.path.exists(sbs_path):
            try:
                existing_sbs = set(os.listdir(sbs_path))
                # Filter out frames that already have SBS versions
                source_frames = [f for f in source_frames 
                                if f.replace(".exr", "_SBS.exr") not in existing_sbs]
            except (OSError, FileNotFoundError):
                pass  # If we can't read the SBS directory, convert all frames
        
        return source_frames

    def _frame_count(self, path: str) -> int:
        return len(self._frame_list(path))

    # Preview -------------------------------------------------------------
    def update_preview(self, shot: Shot) -> None:
        frames = self._frame_list(shot.path)
        if not frames:
            return
        frame_path = os.path.join(shot.path, frames[0])
        self.current_frame = frame_path
        self.thumbnail = self._make_thumbnail(frame_path)
        if self.thumbnail:
            self.thumb_label.configure(image=self.thumbnail)
        channels = self._get_channels(frame_path)
        self.layers_list.delete(0, tk.END)
        for c in channels:
            self.layers_list.insert(tk.END, c)

    def _make_thumbnail(self, frame: str) -> tk.PhotoImage | None:
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            cmd = [self.oiiotool, frame, "--resize", "200x200", "-o", tmp_path]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            img = tk.PhotoImage(file=tmp_path)
            os.unlink(tmp_path)
            return img
        except Exception:
            return None

    def _get_channels(self, frame: str) -> List[str]:
        if not self.oiiotool:
            return []
        try:
            result = subprocess.run(
                [self.oiiotool, frame, "--info", "-v"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError:
            return []
        for line in result.stdout.splitlines():
            if "channel list:" in line:
                return [c.strip() for c in line.split("channel list:", 1)[1].split(",")]
        return []

    def preview_channel(self) -> None:
        sel = self.layers_list.curselection()
        if not sel or not self.current_frame:
            return
        channel = self.layers_list.get(sel[0])
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            cmd = [self.oiiotool, self.current_frame, "-ch", channel,
                   "--resize", "200x200", "-o", tmp_path]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            img = tk.PhotoImage(file=tmp_path)
            os.unlink(tmp_path)
            self.thumbnail = img
            self.thumb_label.configure(image=self.thumbnail)
        except Exception as e:
            messagebox.showerror("Preview failed", str(e))

    # Single frame -------------------------------------------------------
    def convert_single(self) -> None:
        file = filedialog.askopenfilename(
            title="Select EXR frame", filetypes=[("OpenEXR", "*.exr")]
        )
        if not file:
            return
        oiiotool = find_oiiotool()
        if not oiiotool:
            messagebox.showerror(
                "Missing dependency",
                "Could not find oiiotool executable.\nPlease install OpenImageIO tools.",
            )
            return
        out = file.replace(".exr", "_SBS.exr")
        cmd = [
            oiiotool,
            file,
            "--fullpixels",
            "-d",
            self.datatype.get(),
            "--compression",
            self.compression.get(),
            "-o",
            out,
        ]
        try:
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
        except FileNotFoundError:
            messagebox.showerror(
                "Conversion failed",
                "oiiotool executable not found. Please install OpenImageIO tools.",
            )
            return
        if result.returncode != 0:
            messagebox.showerror("Conversion failed", result.stderr.strip())
            self.log.insert(tk.END, f"{os.path.basename(file)} failed - {result.stderr.strip()}\n")
        else:
            messagebox.showinfo("Conversion complete", f"Saved {out}")
            self.log.insert(tk.END, f"Converted {os.path.basename(file)}\n")
        self.log.see(tk.END)

    def save_log(self) -> None:
        file = filedialog.asksaveasfilename(title="Save Log", defaultextension=".txt",
                                            filetypes=[("Text Files", "*.txt")])
        if not file:
            return
        with open(file, "w", encoding="utf-8") as fh:
            fh.write(self.log.get("1.0", tk.END))

    # Queue processing ----------------------------------------------------
    def process_queue(self) -> None:
        try:
            while True:
                msg = self.queue.get_nowait()
                if msg[0] == "shot":
                    _, name, done, total = msg
                    self.shot_label.config(text=f"{name}: {done}/{total}")
                    self.shot_pb.configure(maximum=total, value=done)
                elif msg[0] == "overall":
                    _, done, total = msg
                    self.overall_label.config(text=f"Overall: {done}/{total}")
                    self.overall_pb.configure(maximum=total, value=done)
                elif msg[0] == "log":
                    _, text = msg
                    self.log.insert(tk.END, text + "\n")
                    self.log.see(tk.END)
                elif msg[0] == "eta":
                    _, remaining = msg
                    self.eta_label.config(text=f"ETA: {self._format_time(remaining)}")
                elif msg[0] == "cpu":
                    _, percent = msg
                    if os.cpu_count():
                        threads = percent / 100 * os.cpu_count()
                        self.cpu_label.config(text=f"CPU: {percent:.0f}% (~{threads:.1f} threads)")
                    else:
                        self.cpu_label.config(text=f"CPU: {percent:.0f}%")
                elif msg[0] == "done":
                    self.convert_btn.config(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.after(100, self.process_queue)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SBS EXR Converter GUI")
    parser.add_argument("--scan-only", dest="scan_only", help="Scan folder and print shot status")
    args = parser.parse_args()
    if args.scan_only:
        shots = scan_shots(args.scan_only)
        for s in shots:
            print(f"{s.name}: {'has SBS' if s.has_sbs else 'needs conversion'}")
    else:
        app = ConverterGUI()
        app.mainloop()
