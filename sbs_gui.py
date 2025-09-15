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
from typing import List, Dict
import urllib.request
import zipfile
import platform
import json
import random
import webbrowser
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
    dropbox_status: str # "Not Started", "In Progress", "Complete"
    dropbox_progress: float # 0.0 to 1.0
    is_moved: bool = False
    moved_path: str = ""


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


def load_shot_statuses(root: str) -> Dict[str, dict]:
    """Load shot statuses from .shot_status.json."""
    status_file = os.path.join(root, ".shot_status.json")
    if os.path.exists(status_file):
        with open(status_file, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_shot_statuses(root: str, statuses: Dict[str, dict]) -> None:
    """Save shot statuses to .shot_status.json."""
    status_file = os.path.join(root, ".shot_status.json")
    with open(status_file, "w") as f:
        json.dump(statuses, f, indent=4)

def scan_shots(root: str, ready_for_comp_path: str) -> List[Shot]:
    """Scan for shots in both source and comp folders, using the filesystem as the source of truth."""
    shots_map: Dict[str, Shot] = {}
    statuses = load_shot_statuses(root)

    # 1. Scan the source directory for monoscopic shots
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except FileNotFoundError:
        entries = []

    for entry in entries:
        if not entry.is_dir() or entry.name.startswith('.') or entry.name == '__pycache__' or entry.name.endswith("_SBS"):
            continue

        shot_name = entry.name
        shot_path = entry.path
        frames = frame_count(shot_path)
        
        # Filesystem is the source of truth for 'is_moved'
        source_sbs_path = f"{shot_path}_SBS"
        comp_sbs_path = os.path.join(ready_for_comp_path, f"{shot_name}_SBS")
        
        sbs_frames = 0
        is_moved = False
        if os.path.exists(comp_sbs_path):
            sbs_frames = sbs_frame_count(comp_sbs_path)
            is_moved = True
        elif os.path.exists(source_sbs_path):
            sbs_frames = sbs_frame_count(source_sbs_path)
            is_moved = False

        shot_status = statuses.get(shot_name, {})
        shot_status['is_moved'] = is_moved  # Update status based on filesystem reality

        needs_conversion = frames > sbs_frames
        conversion_progress = sbs_frames / frames if frames > 0 else 0.0
        
        # --- Dropbox Status ---
        # This is based on the local SBS folder, assuming Dropbox client is syncing it.
        dropbox_progress = conversion_progress
        if dropbox_progress >= 1.0:
            dropbox_status = "Complete"
            dropbox_progress = 1.0
        elif dropbox_progress > 0:
            dropbox_status = "In Progress"
        else:
            dropbox_status = "Not Started"
        
        shot_status['dropbox_status'] = dropbox_status
        shot_status['dropbox_progress'] = dropbox_progress

        shots_map[shot_name] = Shot(
            name=shot_name,
            path=shot_path,
            has_sbs=not needs_conversion,
            frames=frames,
            sbs_frames=sbs_frames,
            needs_conversion=needs_conversion,
            conversion_progress=conversion_progress,
            dropbox_status=dropbox_status,
            dropbox_progress=dropbox_progress,
            is_moved=is_moved,
            moved_path=ready_for_comp_path if is_moved else ""
        )

        shot_status.update({
            "path": shot_path,
            "frames": frames,
            "sbs_frames": sbs_frames,
        })
        statuses[shot_name] = shot_status

    # 2. Add shots that are only in the status file (e.g., folder deleted from source)
    for name, status in statuses.items():
        if name not in shots_map and status.get("is_moved"):
            # Verify it's still in the comp folder, otherwise it's just gone
            comp_sbs_path = os.path.join(ready_for_comp_path, f"{name}_SBS")
            if os.path.exists(comp_sbs_path):
                shots_map[name] = Shot(
                    name=name,
                    path=status.get("path", ""), # Path might be stale, but it's all we have
                    has_sbs=True,
                    frames=status.get("frames", 0),
                    sbs_frames=status.get("sbs_frames", 0),
                    needs_conversion=False,
                    conversion_progress=1.0,
                    dropbox_status="Complete",
                    dropbox_progress=1.0,
                    is_moved=True,
                    moved_path=status.get("moved_path", ready_for_comp_path)
                )

    save_shot_statuses(root, statuses)
    return sorted(shots_map.values(), key=lambda s: s.name)


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
        self.scanning = False
        self.selected_shot_frame: ttk.Frame | None = None
        self.ready_for_comp_path = tk.StringVar(value=r"D:\Boona Dropbox\Boona Slate\01_Active\Silver_SIL_JUL25_BS-144\Production\Output\Silver - Renders\Unreal Renders\ReadyForComp")
        self.live_mode_thread = None
        self.shot_last_activity: Dict[str, float] = {}

        # Custom styles
        style = ttk.Style(self)
        style.configure("black.TLabel", foreground="black")
        style.configure("blue.TLabel", foreground="blue")
        style.configure("green.Horizontal.TProgressbar", background='green')
        style.configure("yellow.Horizontal.TProgressbar", background='yellow')

        self._build_widgets()
        self.after(100, self.process_queue)
        self.after(60000, self._periodic_cleanup)

    # UI -----------------------------------------------------------------
    def _build_widgets(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=5)
        self.load_folder_btn = ttk.Button(top, text="Select Shots Folder", command=self.load_folder)
        self.load_folder_btn.pack(side=tk.LEFT)
        self.refresh_btn = ttk.Button(top, text="🔄 Refresh", command=self.refresh_folder)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)

        # Ready for Comp folder selection
        comp_frame = ttk.Frame(top)
        comp_frame.pack(side=tk.LEFT, padx=10)
        ttk.Button(comp_frame, text="Set 'Ready For Comp' Folder", command=self.select_ready_for_comp_folder).pack(side=tk.LEFT)
        ttk.Label(comp_frame, textvariable=self.ready_for_comp_path, foreground="gray").pack(side=tk.LEFT, padx=5)

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

        ttk.Label(opts, text="Max Parallel Jobs:").grid(row=0, column=2, sticky=tk.W, padx=(10, 0))
        self.max_workers = tk.IntVar(value=os.cpu_count() or 4)
        ttk.Spinbox(opts, from_=1, to=os.cpu_count() or 32, textvariable=self.max_workers).grid(row=0, column=3, sticky=tk.W)

        # Live Mode Controls
        live_frame = ttk.Frame(opts)
        live_frame.grid(row=1, column=2, columnspan=2, sticky=tk.W, padx=(10, 0))
        self.live_mode_active = tk.BooleanVar(value=False)
        ttk.Checkbutton(live_frame, text="Live Mode", variable=self.live_mode_active, command=self._toggle_live_mode).pack(side=tk.LEFT)
        
        ttk.Label(live_frame, text="Min Delay (s):").pack(side=tk.LEFT, padx=(10, 0))
        self.min_delay = tk.IntVar(value=30)
        ttk.Spinbox(live_frame, from_=5, to=3600, textvariable=self.min_delay, width=5).pack(side=tk.LEFT)

        ttk.Label(live_frame, text="Frame Time x").pack(side=tk.LEFT, padx=(10, 0))
        self.frame_time_multiplier = tk.IntVar(value=5)
        ttk.Spinbox(live_frame, from_=2, to=20, textvariable=self.frame_time_multiplier, width=4).pack(side=tk.LEFT)

        content = ttk.Frame(self)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.shots_frame = ttk.LabelFrame(content, text="Shots")
        self.shots_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        btns = ttk.Frame(self.shots_frame)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Select All", command=self.select_all).pack(side=tk.LEFT)
        ttk.Button(btns, text="Deselect All", command=self.deselect_all).pack(side=tk.LEFT, padx=5)
        
        # Add the label to the right of the buttons
        dropbox_header = ttk.Label(btns, text="SBS Dropbox Upload Status")
        dropbox_header.pack(side=tk.RIGHT, padx=10)

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
        
        self.preview_buttons_frame = ttk.Frame(self.preview_frame)
        self.preview_buttons_frame.pack(pady=5)

        self.shot_details_frame = ttk.LabelFrame(self.preview_frame, text="Shot Details")
        self.shot_details_frame.pack(fill=tk.X, padx=5, pady=5)

        self.layers_list = tk.Listbox(self.preview_frame, height=6)
        self.layers_list.pack(fill=tk.X, pady=5)
        ttk.Button(self.preview_frame, text="Preview Channel", command=self.preview_channel).pack()

        controls = ttk.Frame(self)
        controls.pack(fill=tk.X, padx=10, pady=5)
        self.convert_btn = ttk.Button(controls, text="Convert Selected", command=self.start_convert)
        self.convert_btn.pack(side=tk.LEFT)
        ttk.Button(controls, text="Convert Single Frame", command=self.convert_single).pack(side=tk.LEFT, padx=5)
        self.move_selected_btn = ttk.Button(controls, text="Move Selected to Comp", command=self.move_selected_to_comp)
        self.move_selected_btn.pack(side=tk.LEFT, padx=5)

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

    def select_ready_for_comp_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select 'Ready For Comp' Folder")
        if folder:
            self.ready_for_comp_path.set(folder)

    def refresh_folder(self) -> None:
        """Refresh the current folder to update conversion status."""
        if not hasattr(self, 'current_folder') or not self.current_folder:
            messagebox.showinfo("No folder selected", "Please select a folder first.")
            return
        self.load_folder_from_path(self.current_folder)

    def load_folder_from_path(self, folder: str) -> None:
        """Load folder from a specific path (used by refresh)."""
        self.current_folder = folder
        self.queue.put(("scan_started",))
        comp_folder = self.ready_for_comp_path.get()
        threading.Thread(
            target=self._scan_worker,
            args=(folder, comp_folder),
            daemon=True,
        ).start()

    def _scan_worker(self, folder: str, comp_folder: str) -> None:
        """Scan for shots in a background thread."""
        shots = scan_shots(folder, comp_folder)
        self.queue.put(("scan_finished", shots))

    def _update_shot_list(self, shots: List[Shot]) -> None:
        """Update the UI with the list of shots."""
        self.shots = shots
        self.selected_shot_frame = None # Reset selected frame
        for child in self.shots_inner.winfo_children():
            child.destroy()
        self.shots_canvas.yview_moveto(0)
        self.shot_vars = []
        if not shots:
            ttk.Label(self.shots_inner, text="No shots found.").pack(pady=10)
            return

        for shot in self.shots:
            var = tk.BooleanVar(value=shot.needs_conversion)
            
            shot_frame = ttk.Frame(self.shots_inner)
            shot_frame.pack(fill=tk.X, pady=2, padx=5)
            # Configure the grid columns. Column 1 should expand.
            shot_frame.columnconfigure(1, weight=1)
            shot_frame.columnconfigure(2, minsize=120) # Give status column a fixed width

            cb = ttk.Checkbutton(shot_frame, variable=var)
            cb.grid(row=0, column=0, sticky=tk.W, padx=(0, 5))

            if shot.is_moved:
                cb.state(["disabled"])

            # Create detailed status label
            if shot.is_moved:
                status = "✅ Moved to Comp"
                color = "blue"
            elif shot.frames == 0:
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
            
            label_text = f"{shot.name} - {status}"
            label = ttk.Label(shot_frame, text=label_text, foreground=color, cursor="hand2")
            label.grid(row=0, column=1, sticky=tk.W)

            # Dropbox status
            if shot.dropbox_status == "Complete":
                progress_text = f"{shot.sbs_frames}/{shot.sbs_frames}"
                style = "blue.TLabel" if shot.is_moved else "black.TLabel"
            else:
                progress_text = f"{int(shot.dropbox_progress * shot.frames)}/{shot.frames}"
                style = "black.TLabel"
            
            status_label = ttk.Label(shot_frame, text=progress_text, style=style)
            status_label.grid(row=0, column=2, sticky=tk.E, padx=10)
            
            # Bind click event to the frame, label, and checkbox
            widgets = [shot_frame, label, cb, status_label]
            for widget in widgets:
                widget.bind("<Button-1>", lambda e, s=shot, sf=shot_frame: self._on_shot_select(s, sf))

            self.shot_vars.append(var)
        if self.shots:
            self.update_preview(self.shots[0])

    def _open_dropbox_url(self, shot: Shot) -> None:
        """Open a placeholder Dropbox URL in the default web browser."""
        # This is a placeholder. In a real implementation, you would get the URL from the Dropbox API.
        url = f"https://www.dropbox.com/sh/{shot.name.lower().replace(' ', '-')}/?dl=0"
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("Failed to open URL", f"Could not open the URL:\n{url}\n\nError: {e}")

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

    def _toggle_live_mode(self) -> None:
        """Start or stop the live mode worker thread."""
        if self.live_mode_active.get():
            self.queue.put(("log", "🟢 Live mode enabled."))
            # Disable manual controls that could interfere
            self.convert_btn.config(state=tk.DISABLED)
            self.move_selected_btn.config(state=tk.DISABLED)

            self.live_mode_thread = threading.Thread(
                target=self._live_mode_worker,
                daemon=True
            )
            self.live_mode_thread.start()
        else:
            self.queue.put(("log", "🔴 Live mode disabled."))
            # Re-enable manual controls
            self.convert_btn.config(state=tk.NORMAL)
            self.move_selected_btn.config(state=tk.NORMAL)

    def _live_mode_worker(self) -> None:
        """Periodically triggers a folder refresh when in live mode."""
        while self.live_mode_active.get():
            if hasattr(self, 'current_folder') and self.current_folder and not self.scanning:
                self.refresh_folder()
            
            time.sleep(15) # Wait 15 seconds before the next scan

    def _handle_auto_processing(self, shots: List[Shot]) -> None:
        """Automatically convert and move shots based on their status and render activity."""
        if not self.live_mode_active.get():
            return

        # --- Auto Conversion ---
        is_converting = self.convert_btn.cget('state') == tk.DISABLED
        if not is_converting:
            shots_to_convert = [s for s in shots if s.needs_conversion]
            if shots_to_convert:
                self.queue.put(("log", f"Live mode: Found {len(shots_to_convert)} shot(s) needing conversion. Starting..."))
                threading.Thread(
                    target=self._convert_worker,
                    args=(shots_to_convert, self.oiiotool),
                    daemon=True,
                ).start()

        # --- Auto Move Logic ---
        now = time.time()
        shots_ready_to_move = []
        
        for shot in shots:
            # Only consider shots that are otherwise ready
            if shot.is_moved or shot.needs_conversion or shot.dropbox_status != "Complete":
                continue

            try:
                frame_files = sorted([os.path.join(shot.path, f) for f in os.listdir(shot.path) if f.lower().endswith(".exr")])
                if len(frame_files) < 2: # Need at least 2 frames to calculate a delta
                    continue

                # Calculate average time delta between frames
                timestamps = [os.path.getmtime(f) for f in frame_files]
                deltas = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
                avg_delta = sum(deltas) / len(deltas) if deltas else 0

                # Determine the required delay
                adaptive_delay = avg_delta * self.frame_time_multiplier.get()
                required_delay = max(self.min_delay.get(), adaptive_delay)
                
                time_since_last_frame = now - timestamps[-1]

                if time_since_last_frame > required_delay:
                    shots_ready_to_move.append(shot)
                    self.queue.put(("log", f"Shot {shot.name} appears complete. (Idle for {time_since_last_frame:.0f}s > {required_delay:.0f}s)"))

            except (FileNotFoundError, ValueError, IndexError):
                continue # Folder might be empty or files disappeared

        if shots_ready_to_move:
            self.queue.put(("log", f"Live mode: Found {len(shots_ready_to_move)} completed shot(s). Moving..."))
            self._move_multiple_worker(shots_ready_to_move)

    def move_selected_to_comp(self) -> None:
        """Move all selected and eligible shots to the 'Ready for Comp' folder."""
        selected = [s for s, v in zip(self.shots, self.shot_vars) if v.get()]
        eligible = [s for s in selected if not s.is_moved and not s.needs_conversion and s.dropbox_status == "Complete"]
        
        if not eligible:
            messagebox.showinfo("Nothing to Move", "No selected shots are ready to be moved.\nA shot must be fully converted and uploaded.")
            return

        confirm = messagebox.askyesno("Confirm Move", f"Are you sure you want to move {len(eligible)} shot(s) to the 'Ready for Comp' folder?")
        if not confirm:
            return

        threading.Thread(
            target=self._move_multiple_worker,
            args=(eligible,),
            daemon=True,
        ).start()

    def _move_multiple_worker(self, shots: List[Shot]) -> None:
        """Worker thread to move multiple shots."""
        for shot in shots:
            self.queue.put(("log", f"Moving {shot.name}_SBS..."))
            dest_folder = self.ready_for_comp_path.get()
            shot_sbs_path = f"{shot.path}_SBS"
            dest_sbs_path = os.path.join(dest_folder, f"{shot.name}_SBS")

            if not os.path.exists(shot_sbs_path) or os.path.exists(dest_sbs_path):
                self.queue.put(("log", f"Skipping {shot.name}_SBS (source missing or destination exists)."))
                continue
            
            try:
                shutil.move(shot_sbs_path, dest_sbs_path)
                statuses = load_shot_statuses(self.current_folder)
                statuses.setdefault(shot.name, {}).update({"is_moved": True, "moved_path": dest_folder})
                save_shot_statuses(self.current_folder, statuses)
                self.queue.put(("log", f"Successfully moved {shot.name}_SBS."))
            except Exception as e:
                self.queue.put(("log", f"Failed to move {shot.name}_SBS: {e}"))
        
        self.queue.put(("log", "All moves complete."))
        self.queue.put(("refresh_request",))

    # Cleanup ------------------------------------------------------------
    def _periodic_cleanup(self) -> None:
        """Periodically scan for and remove old temp files."""
        if hasattr(self, 'current_folder') and self.current_folder:
            threading.Thread(
                target=self._cleanup_temp_files,
                args=(self.current_folder,),
                daemon=True
            ).start()
        # Reschedule after 1 minute
        self.after(60000, self._periodic_cleanup)

    def _cleanup_temp_files(self, folder: str) -> None:
        """Scan for and remove temporary .exr files older than 5 minutes."""
        self.queue.put(("log", "🧹 Running periodic cleanup..."))
        now = time.time()
        cleaned_count = 0
        try:
            for entry in os.scandir(folder):
                if entry.is_dir() and entry.name.endswith("_SBS"):
                    sbs_dir = entry.path
                    for sub_entry in os.scandir(sbs_dir):
                        if sub_entry.is_file() and sub_entry.name.startswith("tmp") and sub_entry.name.endswith(".exr"):
                            try:
                                file_path = sub_entry.path
                                file_age = now - os.path.getmtime(file_path)
                                if file_age > 300:  # 5 minutes
                                    os.remove(file_path)
                                    self.queue.put(("log", f"Removed old temp file: {file_path}"))
                                    cleaned_count += 1
                            except (OSError, FileNotFoundError) as e:
                                self.queue.put(("log", f"Error removing temp file {sub_entry.name}: {e}"))
        except (OSError, FileNotFoundError) as e:
            self.queue.put(("log", f"Error during cleanup scan: {e}"))
        
        if cleaned_count > 0:
            self.queue.put(("log", f"🧹 Cleanup finished. Removed {cleaned_count} files."))
        else:
            self.queue.put(("log", "🧹 Cleanup finished. No old temp files found."))

    # Conversion ---------------------------------------------------------
    def start_convert(self) -> None:
        # Run a cleanup pass before starting a new conversion
        if hasattr(self, 'current_folder') and self.current_folder:
            self.queue.put(("log", "Running pre-conversion cleanup..."))
            self._cleanup_temp_files(self.current_folder)

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
        
        max_workers = self.max_workers.get()
        semaphore = threading.Semaphore(max_workers)

        def process(shot: Shot, frame: str, outdir: str) -> tuple[str, str, int, str]:
            """Process a single frame, respecting the semaphore."""
            with semaphore:
                src = os.path.join(shot.path, frame)
                dst = os.path.join(outdir, frame.replace(".exr", "_SBS.exr"))
                
                try:
                    with tempfile.NamedTemporaryFile(suffix=".exr", dir=outdir, delete=False) as tmp:
                        temp_dst = tmp.name
                except Exception as e:
                    return shot.name, frame, -1, f"Failed to create temp file: {e}"

                cmd = [
                    oiiotool,
                    src,
                    "--fullpixels",
                    "-d",
                    self.datatype.get(),
                    "--compression",
                    self.compression.get(),
                    "-o",
                    temp_dst,
                ]
                
                try:
                    result = subprocess.run(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
                    )
                    
                    if result.returncode != 0:
                        return shot.name, frame, result.returncode, result.stderr.strip()
                    else:
                        os.rename(temp_dst, dst)
                        return shot.name, frame, 0, ""
                except Exception as e:
                    return shot.name, frame, -1, str(e)
                finally:
                    if os.path.exists(temp_dst):
                        try:
                            os.remove(temp_dst)
                        except OSError:
                            pass # Ignore errors on temp file removal

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for shot in shots:
                frames = self._frame_list(shot.path)
                if not frames:
                    self.queue.put(("log", f"{shot.name}: No frames to convert (already complete?)"))
                    continue

                outdir = f"{shot.path}_SBS"
                os.makedirs(outdir, exist_ok=True)

                self.queue.put(("shot", shot.name, 0, len(frames)))
                self.queue.put(("log", f"{shot.name}: Converting {len(frames)} frames..."))
                for frame in frames:
                    futures.append(executor.submit(process, shot, frame, outdir))

            shot_progress = {shot.name: {"done": 0, "total": len(self._frame_list(shot.path))} for shot in shots}

            for future in as_completed(futures):
                shot_name, frame, retcode, stderr = future.result()
                
                if retcode != 0:
                    self.queue.put(("log", f"{shot_name}: {frame} failed - {stderr}"))
                else:
                    self.queue.put(("log", f"{shot_name}: {frame} ✅"))
                
                done += 1
                shot_progress[shot_name]["done"] += 1
                self.queue.put(("shot", shot_name, shot_progress[shot_name]["done"], shot_progress[shot_name]["total"]))
                self.queue.put(("overall", done, total_frames))
                
                if psutil:
                    self.queue.put(("cpu", psutil.cpu_percent()))
                if done:
                    elapsed = time.time() - start_time
                    eta = (total_frames - done) * (elapsed / done)
                    self.queue.put(("eta", eta))

        self.queue.put(("log", "🎉 All conversions complete!"))
        self.queue.put(("done",))

        # Auto-move completed shots
        self.queue.put(("log", "Checking for completed shots to auto-move..."))
        statuses = load_shot_statuses(self.current_folder)
        shots_to_move = []
        for shot in shots:
            shot_status = statuses.get(shot.name, {})
            # Refresh shot data from disk/status file
            sbs_frames = sbs_frame_count(f"{shot.path}_SBS")
            frames = frame_count(shot.path)
            
            if sbs_frames == frames and shot_status.get("dropbox_status") == "Complete":
                if not shot_status.get("is_moved"):
                    shots_to_move.append(shot)

        if shots_to_move:
            self.queue.put(("log", f"Found {len(shots_to_move)} shots to move automatically."))
            self._move_multiple_worker(shots_to_move)
        else:
            self.queue.put(("log", "No shots ready for automatic moving."))
        
        self.queue.put(("refresh_request",))

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

    def _on_shot_select(self, shot: Shot, shot_frame: ttk.Frame) -> None:
        """Handle shot selection, showing a loading state."""
        if self.selected_shot_frame:
            self.selected_shot_frame.config(relief=tk.FLAT)
        
        shot_frame.config(relief=tk.GROOVE, borderwidth=2)
        self.selected_shot_frame = shot_frame
        
        # Show loading indicator
        self.thumb_label.configure(image=None)
        self.thumb_label.config(text="Loading...")
        self.layers_list.delete(0, tk.END)
        
        # Update preview in a separate thread to avoid blocking the GUI
        threading.Thread(
            target=self.update_preview,
            args=(shot,),
            daemon=True,
        ).start()

    # Preview -------------------------------------------------------------
    def update_preview(self, shot: Shot) -> None:
        # This now runs in a background thread, so GUI updates must be queued
        
        # Clear previous buttons
        for widget in self.preview_buttons_frame.winfo_children():
            widget.destroy()

        # Determine the correct paths based on whether the shot is moved
        mono_path = shot.path
        sbs_path = os.path.join(shot.moved_path, f"{shot.name}_SBS") if shot.is_moved else f"{shot.path}_SBS"

        # Add new buttons
        mono_button = ttk.Button(self.preview_buttons_frame, text="Open Mono Folder", command=lambda: self.open_folder(mono_path))
        mono_button.pack(side=tk.LEFT, padx=5)

        sbs_button = ttk.Button(self.preview_buttons_frame, text="Open SBS Folder", command=lambda: self.open_folder(sbs_path))
        sbs_button.pack(side=tk.LEFT, padx=5)
        
        dropbox_button = ttk.Button(self.preview_buttons_frame, text="Dropbox", command=lambda: self._open_dropbox_url(shot))
        dropbox_button.pack(side=tk.LEFT, padx=5)

        move_button = ttk.Button(self.preview_buttons_frame, text="Move to Ready for Comp", command=lambda: self._move_shot_to_comp(shot))
        move_button.pack(side=tk.LEFT, padx=5)
        if shot.is_moved or shot.needs_conversion or shot.dropbox_status != "Complete":
            move_button.config(state=tk.DISABLED)

        if not os.path.exists(mono_path):
            mono_button.config(state=tk.DISABLED)
        if not os.path.exists(sbs_path):
            sbs_button.config(state=tk.DISABLED)

        if shot.is_moved:
            self.queue.put(("preview_update", None, [], shot, ""))
            return

        frames = self._frame_list(shot.path)
        if not frames:
            # Even if there are no frames to convert, we might have a preview
            source_frames = []
            try:
                source_frames = [f for f in sorted(os.listdir(shot.path))
                                 if f.lower().endswith(".exr") and "_SBS" not in f]
            except FileNotFoundError:
                pass # Ignore if folder doesn't exist
            if not source_frames:
                self.queue.put(("preview_update", None, [], shot, ""))
                return
            frames = source_frames

        frame_path = os.path.join(shot.path, frames[0])
        thumbnail = self._make_thumbnail(frame_path)
        channels = self._get_channels(frame_path)
        
        self.queue.put(("preview_update", thumbnail, channels, shot, frame_path))
        
    def _move_shot_to_comp(self, shot: Shot) -> None:
        """Move the shot's SBS folder to the 'Ready for Comp' directory."""
        dest_folder = self.ready_for_comp_path.get()
        if not os.path.isdir(dest_folder):
            messagebox.showerror("Invalid Destination", f"The folder '{dest_folder}' does not exist.")
            return

        shot_sbs_path = f"{shot.path}_SBS"
        dest_sbs_path = os.path.join(dest_folder, f"{shot.name}_SBS")

        if not os.path.exists(shot_sbs_path):
            messagebox.showerror("Source Missing", f"The source folder '{shot_sbs_path}' does not exist.")
            return

        if os.path.exists(dest_sbs_path):
            messagebox.showerror("Destination Exists", "An SBS folder for this shot already exists in the destination.")
            return

        try:
            shutil.move(shot_sbs_path, dest_sbs_path)

            # Update the status file
            statuses = load_shot_statuses(self.current_folder)
            statuses.setdefault(shot.name, {}).update({
                "is_moved": True,
                "moved_path": dest_folder,
            })
            save_shot_statuses(self.current_folder, statuses)

            messagebox.showinfo("Move Complete", f"Moved '{shot.name}_SBS' to '{dest_folder}'.")
            self.refresh_folder()

        except Exception as e:
            messagebox.showerror("Move Failed", f"An error occurred while moving the shot: {e}")

    def _update_preview_ui(self, thumbnail, channels, shot, frame_path):
        """Update the preview UI from the main thread."""
        self.current_frame = frame_path
        self.thumb_label.config(text="") # Clear loading text
        
        if shot.is_moved:
            self.thumb_label.configure(image=None)
            self.thumb_label.config(text="Shot has been moved.")
            self.layers_list.delete(0, tk.END)
            self._update_shot_details(shot, "")
            return

        if thumbnail:
            self.thumbnail = thumbnail
            self.thumb_label.configure(image=self.thumbnail)
        else:
            self.thumb_label.configure(image=None)
            self.thumb_label.config(text="Preview not available")

        self.layers_list.delete(0, tk.END)
        for c in channels:
            self.layers_list.insert(tk.END, c)

        # Update shot details
        self._update_shot_details(shot, frame_path)

    def _update_shot_details(self, shot: Shot, frame_path: str) -> None:
        """Update the shot details frame."""
        for widget in self.shot_details_frame.winfo_children():
            widget.destroy()

        ttk.Label(self.shot_details_frame, text=f"Frames: {shot.frames}").pack(anchor=tk.W)
        
        if shot.is_moved:
            status = "Moved to Comp"
            ttk.Label(self.shot_details_frame, text=f"Status: {status}").pack(anchor=tk.W)
            ttk.Label(self.shot_details_frame, text=f"Location: {shot.moved_path}").pack(anchor=tk.W)
            return

        status = "Complete" if shot.conversion_progress == 1.0 else "Incomplete"
        ttk.Label(self.shot_details_frame, text=f"Conversion: {status}").pack(anchor=tk.W)
        
        details = self._get_shot_details(frame_path)
        if details:
            ttk.Label(self.shot_details_frame, text=f"Compression: {details.get('compression', 'N/A')}").pack(anchor=tk.W)
            ttk.Label(self.shot_details_frame, text=f"Resolution: {details.get('resolution', 'N/A')}").pack(anchor=tk.W)
            ttk.Label(self.shot_details_frame, text=f"File Size: {details.get('filesize', 'N/A')}").pack(anchor=tk.W)

    def open_folder(self, path: str) -> None:
        """Open a folder in the default file explorer."""
        if not os.path.exists(path):
            messagebox.showerror("Folder not found", f"The folder '{path}' does not exist.")
            return
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", path], check=True)
            else:  # Linux
                subprocess.run(["xdg-open", path], check=True)
        except Exception as e:
            messagebox.showerror("Failed to open folder", str(e))

    def _get_shot_details(self, frame_path: str) -> dict:
        """Get details for a shot from oiiotool."""
        if not self.oiiotool or not os.path.exists(frame_path):
            return {}
        try:
            result = subprocess.run(
                [self.oiiotool, frame_path, "--info", "-v"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            output = result.stdout
            details = {}
            for line in output.splitlines():
                if "compression:" in line:
                    details["compression"] = line.split("compression:")[1].strip().strip('"')
                if "resolution:" in line:
                    details["resolution"] = line.split("resolution:")[1].strip()
                if "file size:" in line:
                    details["filesize"] = line.split("file size:")[1].strip()
            return details
        except (subprocess.CalledProcessError, FileNotFoundError):
            return {}

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
                if msg[0] == "scan_started":
                    self.scanning = True
                    self.load_folder_btn.config(state=tk.DISABLED)
                    self.refresh_btn.config(state=tk.DISABLED)
                    for child in self.shots_inner.winfo_children():
                        child.destroy()
                    ttk.Label(self.shots_inner, text="Scanning...").pack(pady=10)
                elif msg[0] == "scan_finished":
                    self.scanning = False
                    self.load_folder_btn.config(state=tk.NORMAL)
                    self.refresh_btn.config(state=tk.NORMAL)
                    shots = msg[1]
                    self._update_shot_list(shots)
                    if self.live_mode_active.get():
                        self._handle_auto_processing(shots)
                elif msg[0] == "shot":
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
                elif msg[0] == "preview_update":
                    _, thumbnail, channels, shot, frame_path = msg
                    self._update_preview_ui(thumbnail, channels, shot, frame_path)
                elif msg[0] == "refresh_request":
                    self.refresh_folder()
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
