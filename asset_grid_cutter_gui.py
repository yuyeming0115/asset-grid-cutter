#!/usr/bin/env python3
"""Small Tkinter GUI for Asset Grid Cutter."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from asset_grid_cutter import CutSettings, cut_image, iter_images


class AssetGridCutterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Asset Grid Cutter")
        self.geometry("760x620")
        self.minsize(680, 560)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None

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

        self._build_ui()
        self.after(100, self._drain_log_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(1, weight=1)

        title = ttk.Label(root, text="Asset Grid Cutter", font=("TkDefaultFont", 18, "bold"))
        title.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 14))

        ttk.Label(root, text="Input").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.input_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(root, text="Choose File", command=self.choose_file).grid(row=1, column=2, padx=(8, 0), pady=6)
        ttk.Button(root, text="Choose Folder", command=self.choose_folder).grid(row=1, column=3, padx=(8, 0), pady=6)

        ttk.Label(root, text="Output").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(root, textvariable=self.output_var).grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Button(root, text="Choose", command=self.choose_output).grid(row=2, column=2, columnspan=2, sticky="ew", padx=(8, 0), pady=6)

        grid_box = ttk.LabelFrame(root, text="Grid", padding=12)
        grid_box.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(14, 8))
        for col in range(6):
            grid_box.columnconfigure(col, weight=1)

        ttk.Label(grid_box, text="Rows").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(grid_box, from_=1, to=100, textvariable=self.rows_var, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(grid_box, text="Columns").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(grid_box, from_=1, to=100, textvariable=self.cols_var, width=8).grid(row=0, column=3, sticky="w")
        ttk.Checkbutton(grid_box, text="Detect grid lines", variable=self.detect_grid_var).grid(row=0, column=4, sticky="w")
        ttk.Checkbutton(grid_box, text="Recursive folder", variable=self.recursive_var).grid(row=0, column=5, sticky="w")

        process_box = ttk.LabelFrame(root, text="Processing", padding=12)
        process_box.grid(row=4, column=0, columnspan=4, sticky="ew", pady=8)
        for col in range(6):
            process_box.columnconfigure(col, weight=1)

        ttk.Checkbutton(process_box, text="Trim background", variable=self.trim_var).grid(row=0, column=0, sticky="w")
        ttk.Label(process_box, text="Padding").grid(row=0, column=1, sticky="e")
        ttk.Spinbox(process_box, from_=0, to=100, textvariable=self.padding_var, width=8).grid(row=0, column=2, sticky="w")
        ttk.Label(process_box, text="Trim tolerance").grid(row=0, column=3, sticky="e")
        ttk.Spinbox(process_box, from_=0, to=255, textvariable=self.trim_tolerance_var, width=8).grid(row=0, column=4, sticky="w")
        ttk.Checkbutton(process_box, text="Preview", variable=self.preview_var).grid(row=0, column=5, sticky="w")

        ttk.Checkbutton(process_box, text="Transparent background", variable=self.transparent_var).grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Label(process_box, text="Tolerance").grid(row=1, column=1, sticky="e", pady=(10, 0))
        ttk.Spinbox(process_box, from_=0, to=255, textvariable=self.transparent_tolerance_var, width=8).grid(row=1, column=2, sticky="w", pady=(10, 0))
        ttk.Label(process_box, text="Softness").grid(row=1, column=3, sticky="e", pady=(10, 0))
        ttk.Spinbox(process_box, from_=0, to=255, textvariable=self.transparent_softness_var, width=8).grid(row=1, column=4, sticky="w", pady=(10, 0))

        action_bar = ttk.Frame(root)
        action_bar.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(12, 8))
        action_bar.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(action_bar, text="Cut Assets", command=self.run)
        self.run_button.grid(row=0, column=1, sticky="e")
        ttk.Button(action_bar, text="Clear Log", command=self.clear_log).grid(row=0, column=2, sticky="e", padx=(8, 0))

        log_frame = ttk.LabelFrame(root, text="Log", padding=8)
        log_frame.grid(row=6, column=0, columnspan=4, sticky="nsew", pady=(8, 0))
        root.rowconfigure(6, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=12, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
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
            for image_path in images:
                out_dir = self._output_dir(image_path, output_path, multiple_inputs)
                manifest = cut_image(image_path, out_dir, settings)
                grid = manifest["grid"]
                self.log_queue.put(
                    f"OK {image_path.name}: {manifest['count']} PNGs "
                    f"({grid['cols']}x{grid['rows']}, {grid['source']}) -> {out_dir}"
                )
            self.log_queue.put("DONE")
        except Exception as exc:
            self.log_queue.put(f"ERROR {exc}")
        finally:
            self.log_queue.put("__ENABLE_RUN__")

    @staticmethod
    def _output_dir(image_path: Path, output_path: Path | None, multiple_inputs: bool) -> Path:
        if output_path:
            return output_path / image_path.stem if multiple_inputs else output_path
        return image_path.with_name(f"{image_path.stem}_slices")

    def log(self, message: str) -> None:
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)

    def clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if message == "__ENABLE_RUN__":
                self.run_button.configure(state=tk.NORMAL)
            else:
                self.log(message)
        self.after(100, self._drain_log_queue)


def main() -> int:
    app = AssetGridCutterApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
