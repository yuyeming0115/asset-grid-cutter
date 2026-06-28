#!/usr/bin/env python3
"""Small Tkinter GUI for Asset Grid Cutter."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk

from asset_grid_cutter import CutSettings, cut_image, ensure_output_dir, iter_images


BG = "#f4f6f8"
PANEL = "#ffffff"
TEXT = "#1f2933"
MUTED = "#52606d"
BORDER = "#cbd2d9"
ACCENT = "#2563eb"


class AssetGridCutterApp(tk.Tk):
    def __init__(self, initial_paths: list[str] | None = None) -> None:
        super().__init__()
        self.title("Asset Grid Cutter")
        self.geometry("900x760")
        self.minsize(760, 680)
        self.configure(background=BG)

        self.log_queue: queue.Queue[object] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_output_dir: Path | None = None
        self.last_preview_path: Path | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.progress_fill: int | None = None

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.rows_var = tk.IntVar(value=6)
        self.cols_var = tk.IntVar(value=12)
        self.recursive_var = tk.BooleanVar(value=False)
        self.detect_grid_var = tk.BooleanVar(value=True)
        self.trim_var = tk.BooleanVar(value=True)
        self.padding_var = tk.IntVar(value=8)
        self.trim_tolerance_var = tk.IntVar(value=14)
        self.transparent_var = tk.BooleanVar(value=False)
        self.transparent_tolerance_var = tk.IntVar(value=8)
        self.transparent_softness_var = tk.IntVar(value=24)
        self.preview_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        if initial_paths:
            self.load_initial_paths(initial_paths)
        self.after(100, self._drain_log_queue)

    def _label(self, parent: tk.Misc, text: str, **kwargs: object) -> tk.Label:
        return tk.Label(parent, text=text, bg=kwargs.pop("bg", BG), fg=kwargs.pop("fg", TEXT), **kwargs)

    def _button(self, parent: tk.Misc, text: str, command: object, **kwargs: object) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=PANEL,
            fg=TEXT,
            activebackground="#e4e7eb",
            activeforeground=TEXT,
            disabledforeground="#9aa5b1",
            relief=tk.RAISED,
            borderwidth=1,
            padx=10,
            pady=4,
            **kwargs,
        )

    def _entry(self, parent: tk.Misc, variable: tk.StringVar) -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=variable,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.SOLID,
            borderwidth=1,
        )

    def _spinbox(self, parent: tk.Misc, variable: tk.IntVar, from_: int, to: int) -> tk.Spinbox:
        return tk.Spinbox(
            parent,
            from_=from_,
            to=to,
            textvariable=variable,
            width=8,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            buttonbackground="#e4e7eb",
            relief=tk.SOLID,
            borderwidth=1,
        )

    def _checkbutton(self, parent: tk.Misc, text: str, variable: tk.BooleanVar) -> tk.Checkbutton:
        return tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            bg=BG,
            fg=TEXT,
            selectcolor=PANEL,
            activebackground=BG,
            activeforeground=TEXT,
            anchor="w",
        )

    def _labelframe(self, parent: tk.Misc, text: str) -> tk.LabelFrame:
        return tk.LabelFrame(
            parent,
            text=text,
            bg=BG,
            fg=MUTED,
            relief=tk.GROOVE,
            borderwidth=1,
            padx=12,
            pady=10,
        )

    def _build_ui(self) -> None:
        root = tk.Frame(self, bg=BG, padx=18, pady=18)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(1, weight=1)

        title = self._label(root, "Asset Grid Cutter", font=("TkDefaultFont", 20, "bold"))
        title.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 14))

        self._label(root, "Input").grid(row=1, column=0, sticky="w", pady=6)
        self._entry(root, self.input_var).grid(row=1, column=1, sticky="ew", pady=6)
        self._button(root, "Choose File", self.choose_file).grid(row=1, column=2, padx=(8, 0), pady=6)
        self._button(root, "Choose Folder", self.choose_folder).grid(row=1, column=3, padx=(8, 0), pady=6)

        self._label(root, "Output").grid(row=2, column=0, sticky="w", pady=6)
        self._entry(root, self.output_var).grid(row=2, column=1, sticky="ew", pady=6)
        self._button(root, "Choose", self.choose_output).grid(row=2, column=2, columnspan=2, sticky="ew", padx=(8, 0), pady=6)

        grid_box = self._labelframe(root, "Grid")
        grid_box.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(14, 8))
        for col in range(6):
            grid_box.columnconfigure(col, weight=1)

        self._label(grid_box, "Rows").grid(row=0, column=0, sticky="w")
        self._spinbox(grid_box, self.rows_var, 1, 100).grid(row=0, column=1, sticky="w")
        self._label(grid_box, "Columns").grid(row=0, column=2, sticky="w")
        self._spinbox(grid_box, self.cols_var, 1, 100).grid(row=0, column=3, sticky="w")
        self._checkbutton(grid_box, "Detect grid lines", self.detect_grid_var).grid(row=0, column=4, sticky="w")
        self._checkbutton(grid_box, "Recursive folder", self.recursive_var).grid(row=0, column=5, sticky="w")

        process_box = self._labelframe(root, "Processing")
        process_box.grid(row=4, column=0, columnspan=4, sticky="ew", pady=8)
        for col in range(6):
            process_box.columnconfigure(col, weight=1)

        self._checkbutton(process_box, "Trim background", self.trim_var).grid(row=0, column=0, sticky="w")
        self._label(process_box, "Padding").grid(row=0, column=1, sticky="e")
        self._spinbox(process_box, self.padding_var, 0, 100).grid(row=0, column=2, sticky="w")
        self._label(process_box, "Trim tolerance").grid(row=0, column=3, sticky="e")
        self._spinbox(process_box, self.trim_tolerance_var, 0, 255).grid(row=0, column=4, sticky="w")
        self._checkbutton(process_box, "Preview", self.preview_var).grid(row=0, column=5, sticky="w")

        self._checkbutton(process_box, "Transparent background", self.transparent_var).grid(row=1, column=0, sticky="w", pady=(10, 0))
        self._label(process_box, "Tolerance").grid(row=1, column=1, sticky="e", pady=(10, 0))
        self._spinbox(process_box, self.transparent_tolerance_var, 0, 255).grid(row=1, column=2, sticky="w", pady=(10, 0))
        self._label(process_box, "Softness").grid(row=1, column=3, sticky="e", pady=(10, 0))
        self._spinbox(process_box, self.transparent_softness_var, 0, 255).grid(row=1, column=4, sticky="w", pady=(10, 0))

        action_bar = tk.Frame(root, bg=BG)
        action_bar.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(12, 8))
        action_bar.columnconfigure(0, weight=1)
        self.run_button = self._button(action_bar, "Cut Assets", self.run)
        self.run_button.grid(row=0, column=1, sticky="e")
        self.open_output_button = self._button(action_bar, "Open Output Folder", self.open_output_folder, state=tk.DISABLED)
        self.open_output_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.open_preview_button = self._button(action_bar, "Open Preview", self.open_preview, state=tk.DISABLED)
        self.open_preview_button.grid(row=0, column=3, sticky="e", padx=(8, 0))
        self._button(action_bar, "Clear Log", self.clear_log).grid(row=0, column=4, sticky="e", padx=(8, 0))

        status_bar = tk.Frame(root, bg=BG)
        status_bar.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        status_bar.columnconfigure(0, weight=1)
        self._label(status_bar, "", textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.progress_canvas = tk.Canvas(status_bar, width=220, height=12, bg="#e4e7eb", highlightthickness=0)
        self.progress_canvas.grid(row=0, column=1, sticky="e")
        self.progress_fill = self.progress_canvas.create_rectangle(0, 0, 0, 12, fill=ACCENT, outline="")

        preview_frame = self._labelframe(root, "Preview")
        preview_frame.grid(row=7, column=0, columnspan=4, sticky="nsew", pady=(8, 0))
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.preview_label = self._label(
            preview_frame,
            "A preview contact sheet will appear here after cutting.",
            bg=BG,
            anchor="center",
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        log_frame = self._labelframe(root, "Log")
        log_frame.grid(row=8, column=0, columnspan=4, sticky="nsew", pady=(8, 0))
        root.rowconfigure(7, weight=2)
        root.rowconfigure(8, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.SOLID,
            borderwidth=1,
            highlightthickness=0,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose asset sheet",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.input_var.set(path)

    def choose_folder(self) -> None:
        path = filedialog.askdirectory(title="Choose input folder")
        if path:
            self.input_var.set(path)

    def choose_output(self) -> None:
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.output_var.set(path)

    def load_initial_paths(self, paths: list[str]) -> None:
        if not paths:
            return

        resolved = [str(Path(path).expanduser().resolve()) for path in paths]
        if len(resolved) == 1:
            self.input_var.set(resolved[0])
            self.log(f"Loaded input: {resolved[0]}")
            return

        first_parent = Path(resolved[0]).parent
        if all(Path(path).parent == first_parent for path in resolved):
            self.input_var.set(str(first_parent))
            self.log(f"Loaded folder from dropped files: {first_parent}")
        else:
            self.input_var.set(str(first_parent))
            self.log("Loaded the first dropped file's folder. Put mixed-location files in one folder for batch mode.")

    def settings(self) -> CutSettings:
        return CutSettings(
            rows=max(1, int(self.rows_var.get())),
            cols=max(1, int(self.cols_var.get())),
            detect_grid=bool(self.detect_grid_var.get()),
            trim=bool(self.trim_var.get()),
            padding=max(0, int(self.padding_var.get())),
            trim_tolerance=max(0, int(self.trim_tolerance_var.get())),
            transparent_bg=bool(self.transparent_var.get()),
            transparent_tolerance=max(0, int(self.transparent_tolerance_var.get())),
            transparent_softness=max(0, int(self.transparent_softness_var.get())),
            preview=bool(self.preview_var.get()),
            line_fraction=0.55,
        )

    def run(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        input_text = self.input_var.get().strip()
        if not input_text:
            messagebox.showwarning("Missing input", "Please choose an input image or folder.")
            return

        input_path = Path(input_text).expanduser().resolve()
        output_path = Path(self.output_var.get()).expanduser().resolve() if self.output_var.get().strip() else None

        self.run_button.configure(state=tk.DISABLED)
        self.open_output_button.configure(state=tk.DISABLED)
        self.open_preview_button.configure(state=tk.DISABLED)
        self.last_output_dir = None
        self.last_preview_path = None
        self.set_progress(0)
        self.status_var.set("Running...")
        self.preview_photo = None
        self.preview_label.configure(image="", text="A preview contact sheet will appear here after cutting.")
        self.log(f"Starting: {input_path}")
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(input_path, output_path, self.settings(), bool(self.recursive_var.get())),
            daemon=True,
        )
        self.worker.start()

    def _run_worker(
        self,
        input_path: Path,
        output_path: Path | None,
        settings: CutSettings,
        recursive: bool,
    ) -> None:
        try:
            images = iter_images(input_path, recursive)
            if not images:
                raise ValueError(f"No supported images found in {input_path}")

            multiple_inputs = len(images) > 1
            total = len(images)
            self.log_queue.put(("status", f"Processing 0/{total}"))
            for index, image_path in enumerate(images, start=1):
                out_dir = ensure_output_dir(image_path, output_path, multiple_inputs)
                manifest = cut_image(image_path, out_dir, settings)
                grid = manifest["grid"]
                self.log_queue.put(
                    f"OK {image_path.name}: {manifest['count']} PNGs "
                    f"({grid['cols']}x{grid['rows']}, {grid['source']}) -> {out_dir}"
                )
                self.log_queue.put(("output_dir", out_dir))
                if manifest.get("preview"):
                    self.log_queue.put(("preview", out_dir / str(manifest["preview"])))
                self.log_queue.put(("progress", index, total))
            self.log_queue.put("DONE")
        except Exception as exc:
            self.log_queue.put(f"ERROR {exc}")
        finally:
            self.log_queue.put("__ENABLE_RUN__")

    def set_progress(self, percent: float) -> None:
        percent = max(0, min(100, percent))
        width = max(1, int(self.progress_canvas.winfo_width() or 220))
        if self.progress_fill is not None:
            self.progress_canvas.coords(self.progress_fill, 0, 0, width * percent / 100, 12)

    def log(self, message: str) -> None:
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)

    def clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def open_output_folder(self) -> None:
        if not self.last_output_dir:
            return
        try:
            subprocess.run(["open", str(self.last_output_dir)], check=False)
        except Exception as exc:
            messagebox.showerror("Open output failed", str(exc))

    def open_preview(self) -> None:
        if not self.last_preview_path:
            return
        try:
            subprocess.run(["open", str(self.last_preview_path)], check=False)
        except Exception as exc:
            messagebox.showerror("Open preview failed", str(exc))

    def show_preview(self, preview_path: Path) -> None:
        if not preview_path.exists():
            return

        self.last_preview_path = preview_path
        self.open_preview_button.configure(state=tk.NORMAL)
        image = Image.open(preview_path).convert("RGB")
        max_width = max(320, self.preview_label.winfo_width() - 24)
        max_height = 260
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(image)
        self.preview_label.configure(image=self.preview_photo, text="")

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if message == "__ENABLE_RUN__":
                self.run_button.configure(state=tk.NORMAL)
                if self.status_var.get() == "Running...":
                    self.status_var.set("Ready")
            elif isinstance(message, tuple) and message[0] == "output_dir":
                self.last_output_dir = Path(message[1])
                self.open_output_button.configure(state=tk.NORMAL)
            elif isinstance(message, tuple) and message[0] == "preview":
                self.show_preview(Path(message[1]))
            elif isinstance(message, tuple) and message[0] == "progress":
                done = int(message[1])
                total = max(1, int(message[2]))
                self.set_progress(done / total * 100)
                self.status_var.set(f"Processing {done}/{total}")
            elif isinstance(message, tuple) and message[0] == "status":
                self.status_var.set(str(message[1]))
            elif message == "DONE":
                self.set_progress(100)
                self.status_var.set("Done")
                self.log(str(message))
            else:
                text = str(message)
                if text.startswith("ERROR "):
                    self.status_var.set("Error")
                self.log(text)
        self.after(100, self._drain_log_queue)


def main() -> int:
    app = AssetGridCutterApp(sys.argv[1:])
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
