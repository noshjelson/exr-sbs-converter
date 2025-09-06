import os
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import dataclass
from typing import List


@dataclass
class Shot:
    name: str
    path: str
    has_sbs: bool


def scan_shots(root: str) -> List[Shot]:
    shots: List[Shot] = []
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except FileNotFoundError:
        return shots
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith('.'):
            continue
        shot_path = entry.path
        sbs_path = f"{shot_path}_SBS"
        has_sbs = os.path.exists(sbs_path)
        if not has_sbs:
            for f in os.listdir(shot_path):
                if f.lower().endswith(".exr") and "_SBS" in f:
                    has_sbs = True
                    break
        shots.append(Shot(entry.name, shot_path, has_sbs))
    return shots


class ConverterGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("SBS EXR Converter")
        self.geometry("600x500")
        self.shots: List[Shot] = []
        self.shot_vars: List[tk.BooleanVar] = []
        self.queue: queue.Queue = queue.Queue()
        self._build_widgets()
        self.after(100, self.process_queue)

    # UI -----------------------------------------------------------------
    def _build_widgets(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(top, text="Select Shots Folder", command=self.load_folder).pack(side=tk.LEFT)

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

        self.shots_frame = ttk.LabelFrame(self, text="Shots")
        self.shots_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        controls = ttk.Frame(self)
        controls.pack(fill=tk.X, padx=10, pady=5)
        self.convert_btn = ttk.Button(controls, text="Convert Selected", command=self.start_convert)
        self.convert_btn.pack(side=tk.LEFT)

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

        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log = tk.Text(log_frame, height=8)
        self.log.pack(fill=tk.BOTH, expand=True)

    # Folder scan ---------------------------------------------------------
    def load_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Shots Folder")
        if not folder:
            return
        self.shots = scan_shots(folder)
        for child in self.shots_frame.winfo_children():
            child.destroy()
        self.shot_vars = []
        for shot in self.shots:
            var = tk.BooleanVar(value=not shot.has_sbs)
            cb = ttk.Checkbutton(self.shots_frame, text=shot.name, variable=var)
            if shot.has_sbs:
                cb.state(["disabled"])
            cb.pack(anchor=tk.W)
            self.shot_vars.append(var)

    # Conversion ---------------------------------------------------------
    def start_convert(self) -> None:
        selected = [s for s, v in zip(self.shots, self.shot_vars) if v.get() and not s.has_sbs]
        if not selected:
            messagebox.showinfo("Nothing to convert", "No shots selected.")
            return
        self.convert_btn.config(state=tk.DISABLED)
        threading.Thread(target=self._convert_worker, args=(selected,), daemon=True).start()

    def _convert_worker(self, shots: List[Shot]) -> None:
        total_frames = sum(self._frame_count(s.path) for s in shots)
        done = 0
        self.queue.put(("overall", done, total_frames))
        for shot in shots:
            frames = self._frame_list(shot.path)
            self.queue.put(("shot", shot.name, 0, len(frames)))
            outdir = f"{shot.path}_SBS"
            os.makedirs(outdir, exist_ok=True)
            for idx, frame in enumerate(frames, 1):
                src = os.path.join(shot.path, frame)
                dst = os.path.join(outdir, frame.replace(".exr", "_SBS.exr"))
                cmd = ["oiiotool", src, "--fullpixels", "-d", self.datatype.get(),
                       "--compression", self.compression.get(), "-o", dst]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if result.returncode != 0:
                    self.queue.put(("log", f"{shot.name}: {frame} failed - {result.stderr.strip()}"))
                else:
                    self.queue.put(("log", f"{shot.name}: {frame}"))
                done += 1
                self.queue.put(("shot", shot.name, idx, len(frames)))
                self.queue.put(("overall", done, total_frames))
            self.queue.put(("log", f"Finished {shot.name}"))
        self.queue.put(("log", "All conversions complete."))
        self.queue.put(("done",))

    def _frame_list(self, path: str) -> List[str]:
        return [f for f in sorted(os.listdir(path))
                if f.lower().endswith(".exr") and "_SBS" not in f]

    def _frame_count(self, path: str) -> int:
        return len(self._frame_list(path))

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
