#!/usr/bin/env python3
"""Cut grid-based asset sheets into individual PNG files."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class CutSettings:
    rows: int | None
    cols: int | None
    detect_grid: bool
    trim: bool
    padding: int
    trim_tolerance: int
    transparent_bg: bool
    transparent_tolerance: int
    transparent_softness: int
    preview: bool
    line_fraction: float


@dataclass
class GridResult:
    rows: int
    cols: int
    source: str
    boxes: list[tuple[int, int, int, int]]
    x_lines: list[tuple[int, int]] | None = None
    y_lines: list[tuple[int, int]] | None = None


def safe_stem(path: Path) -> str:
    stem = re.sub(r"[^\w.-]+", "_", path.stem, flags=re.UNICODE).strip("_")
    return stem or "asset_sheet"


def iter_images(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image file: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise ValueError(f"Input does not exist: {input_path}")

    pattern = "**/*" if recursive else "*"
    images = [
        p
        for p in input_path.glob(pattern)
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(images)


def group_indices(indices: np.ndarray) -> list[tuple[int, int]]:
    if indices.size == 0:
        return []

    groups: list[tuple[int, int]] = []
    start = prev = int(indices[0])
    for value in indices[1:]:
        value = int(value)
        if value == prev + 1:
            prev = value
            continue
        groups.append((start, prev))
        start = prev = value
    groups.append((start, prev))
    return groups


def filter_line_groups(
    groups: list[tuple[int, int]],
    length: int,
    expected_count: int | None,
) -> list[tuple[int, int]]:
    if not groups:
        return []

    max_width = max(8, int(length * 0.01))
    groups = [g for g in groups if g[1] - g[0] + 1 <= max_width]

    if not groups:
        return []

    # Merge tiny double detections that sit on the same visual divider.
    merged: list[tuple[int, int]] = []
    for start, end in groups:
        if merged and start - merged[-1][1] <= 3:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    if expected_count and len(merged) > expected_count:
        centers = np.array([(s + e) / 2 for s, e in merged])
        # Keep the set of dividers that best resembles an even grid while still
        # allowing AI-generated sheets to have slightly uneven edge rows.
        target = np.linspace(0, length - 1, expected_count)
        selected: list[int] = []
        used: set[int] = set()
        for t in target:
            order = np.argsort(np.abs(centers - t))
            for idx in order:
                idx = int(idx)
                if idx not in used:
                    used.add(idx)
                    selected.append(idx)
                    break
        merged = [merged[i] for i in sorted(selected)]

    return merged


def detect_axis_lines(
    rgb: np.ndarray,
    axis: int,
    line_fraction: float,
    expected_count: int | None,
) -> list[tuple[int, int]]:
    max_channel = rgb.max(axis=2)
    min_channel = rgb.min(axis=2)
    mean_channel = rgb.mean(axis=2)

    # Grid lines in this asset style are low-saturation, light gray strokes.
    # Objects and shadows may be gray too, but they do not span almost the
    # entire sheet, so the per-axis fraction separates them cleanly.
    grayish = (max_channel - min_channel <= 10) & (mean_channel >= 185) & (mean_channel <= 248)
    profile = grayish.mean(axis=0 if axis == 0 else 1)

    threshold = max(line_fraction, min(0.98, float(profile.max()) * 0.72))
    groups = group_indices(np.where(profile >= threshold)[0])
    length = rgb.shape[1] if axis == 0 else rgb.shape[0]
    return filter_line_groups(groups, length, expected_count)


def detect_grid(
    image: Image.Image,
    rows: int | None,
    cols: int | None,
    line_fraction: float,
) -> GridResult | None:
    rgb = np.array(image.convert("RGB"))
    height, width = rgb.shape[:2]

    expected_x = cols + 1 if cols else None
    expected_y = rows + 1 if rows else None
    x_lines = detect_axis_lines(rgb, axis=0, line_fraction=line_fraction, expected_count=expected_x)
    y_lines = detect_axis_lines(rgb, axis=1, line_fraction=line_fraction, expected_count=expected_y)

    if len(x_lines) < 2 or len(y_lines) < 2:
        return None

    detected_cols = len(x_lines) - 1
    detected_rows = len(y_lines) - 1

    if cols and detected_cols != cols:
        return None
    if rows and detected_rows != rows:
        return None

    boxes: list[tuple[int, int, int, int]] = []
    for row in range(detected_rows):
        top = y_lines[row][1] + 1
        bottom = y_lines[row + 1][0]
        for col in range(detected_cols):
            left = x_lines[col][1] + 1
            right = x_lines[col + 1][0]
            if right > left and bottom > top:
                boxes.append((left, top, right, bottom))

    if len(boxes) != detected_cols * detected_rows:
        return None

    return GridResult(
        rows=detected_rows,
        cols=detected_cols,
        source="detected",
        boxes=boxes,
        x_lines=x_lines,
        y_lines=y_lines,
    )


def fixed_grid(image: Image.Image, rows: int, cols: int) -> GridResult:
    width, height = image.size
    x_bounds = [round(i * width / cols) for i in range(cols + 1)]
    y_bounds = [round(i * height / rows) for i in range(rows + 1)]
    boxes = [
        (x_bounds[col], y_bounds[row], x_bounds[col + 1], y_bounds[row + 1])
        for row in range(rows)
        for col in range(cols)
    ]
    return GridResult(rows=rows, cols=cols, source="fixed", boxes=boxes)


def choose_grid(image: Image.Image, settings: CutSettings) -> GridResult:
    if settings.detect_grid:
        detected = detect_grid(image, settings.rows, settings.cols, settings.line_fraction)
        if detected:
            return detected

    if not settings.rows or not settings.cols:
        raise ValueError("Could not detect grid. Re-run with --rows and --cols.")

    return fixed_grid(image, settings.rows, settings.cols)


def background_color(image: Image.Image) -> np.ndarray:
    rgb = np.array(image.convert("RGB"))
    height, width = rgb.shape[:2]
    sample = np.concatenate(
        [
            rgb[: max(1, height // 20), :, :].reshape(-1, 3),
            rgb[-max(1, height // 20) :, :, :].reshape(-1, 3),
            rgb[:, : max(1, width // 20), :].reshape(-1, 3),
            rgb[:, -max(1, width // 20) :, :].reshape(-1, 3),
        ],
        axis=0,
    )
    return np.median(sample, axis=0)


def trim_image(image: Image.Image, tolerance: int, padding: int) -> Image.Image:
    rgba = image.convert("RGBA")
    arr = np.array(rgba)
    bg = background_color(rgba)
    rgb = arr[:, :, :3].astype(np.int16)
    alpha = arr[:, :, 3]
    distance = np.abs(rgb - bg.astype(np.int16)).max(axis=2)
    mask = (distance > tolerance) | (alpha < 250)
    coords = np.argwhere(mask)

    if coords.size == 0:
        return rgba

    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0) + 1
    x0 = max(0, int(x0) - padding)
    y0 = max(0, int(y0) - padding)
    x1 = min(rgba.width, int(x1) + padding)
    y1 = min(rgba.height, int(y1) + padding)
    return rgba.crop((x0, y0, x1, y1))


def make_background_transparent(image: Image.Image, tolerance: int, softness: int) -> Image.Image:
    rgba = image.convert("RGBA")
    arr = np.array(rgba)
    bg = background_color(rgba)
    rgb = arr[:, :, :3].astype(np.int16)
    distance = np.abs(rgb - bg.astype(np.int16)).max(axis=2).astype(np.float32)

    if softness <= 0:
        alpha_factor = (distance > tolerance).astype(np.float32)
    else:
        alpha_factor = np.clip((distance - tolerance) / softness, 0, 1)

    arr[:, :, 3] = np.minimum(arr[:, :, 3].astype(np.float32), alpha_factor * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def ensure_output_dir(input_path: Path, output: Path | None, multiple_inputs: bool) -> Path:
    if output:
        return output / safe_stem(input_path) if multiple_inputs else output
    return input_path.with_name(f"{safe_stem(input_path)}_slices")


def create_preview(image_paths: list[Path], output_path: Path, thumb_size: int = 128) -> None:
    if not image_paths:
        return

    thumbs: list[Image.Image] = []
    labels: list[str] = []
    for path in image_paths:
        img = Image.open(path).convert("RGBA")
        img.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
        tile = Image.new("RGBA", (thumb_size, thumb_size), (246, 246, 246, 255))
        x = (thumb_size - img.width) // 2
        y = (thumb_size - img.height) // 2
        tile.alpha_composite(img, (x, y))
        thumbs.append(tile.convert("RGB"))
        label_match = re.search(r"(r\d{2}_c\d{2})$", path.stem)
        labels.append(label_match.group(1) if label_match else path.stem[-12:])

    cols = min(12, max(1, math.ceil(math.sqrt(len(thumbs)))))
    rows = math.ceil(len(thumbs) / cols)
    label_h = 18
    gap = 8
    sheet = Image.new(
        "RGB",
        (cols * thumb_size + (cols + 1) * gap, rows * (thumb_size + label_h) + (rows + 1) * gap),
        (235, 237, 240),
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for index, thumb in enumerate(thumbs):
        row, col = divmod(index, cols)
        x = gap + col * (thumb_size + gap)
        y = gap + row * (thumb_size + label_h + gap)
        sheet.paste(thumb, (x, y))
        text = labels[index]
        bbox = draw.textbbox((0, 0), text, font=font)
        text_x = x + (thumb_size - (bbox[2] - bbox[0])) // 2
        draw.text((text_x, y + thumb_size + 3), text, fill=(70, 77, 87), font=font)

    sheet.save(output_path)


def cut_image(input_path: Path, output_dir: Path, settings: CutSettings) -> dict:
    image = Image.open(input_path)
    grid = choose_grid(image, settings)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    stem = safe_stem(input_path)

    for index, box in enumerate(grid.boxes, start=1):
        row = (index - 1) // grid.cols + 1
        col = (index - 1) % grid.cols + 1
        cell = image.crop(box).convert("RGBA")

        if settings.trim:
            cell = trim_image(cell, settings.trim_tolerance, settings.padding)
        if settings.transparent_bg:
            cell = make_background_transparent(
                cell,
                settings.transparent_tolerance,
                settings.transparent_softness,
            )

        out_name = f"{stem}_r{row:02d}_c{col:02d}.png"
        out_path = output_dir / out_name
        cell.save(out_path)
        written.append(out_path)

    preview_path = None
    if settings.preview:
        preview_path = output_dir / f"{stem}_preview.png"
        create_preview(written, preview_path)

    manifest = {
        "input": str(input_path),
        "output_dir": str(output_dir),
        "grid": {
            "rows": grid.rows,
            "cols": grid.cols,
            "source": grid.source,
            "x_lines": grid.x_lines,
            "y_lines": grid.y_lines,
        },
        "count": len(written),
        "settings": asdict(settings),
        "files": [p.name for p in written],
        "preview": preview_path.name if preview_path else None,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cut grid-based asset sheets into individual PNG images.",
    )
    parser.add_argument("input", type=Path, help="Image file or folder of image files.")
    parser.add_argument("-o", "--output", type=Path, help="Output folder.")
    parser.add_argument("--rows", type=positive_int, help="Expected row count.")
    parser.add_argument("--cols", type=positive_int, help="Expected column count.")
    parser.add_argument("--recursive", action="store_true", help="Process folders recursively.")
    parser.add_argument(
        "--no-detect-grid",
        action="store_true",
        help="Skip gray grid-line detection and split into equal cells.",
    )
    parser.add_argument("--trim", action="store_true", help="Trim background around each asset.")
    parser.add_argument("--padding", type=int, default=8, help="Padding added after trimming.")
    parser.add_argument(
        "--trim-tolerance",
        type=int,
        default=14,
        help="RGB max-channel distance from background used for trimming.",
    )
    parser.add_argument(
        "--transparent-bg",
        action="store_true",
        help="Turn detected background color transparent after cutting.",
    )
    parser.add_argument(
        "--transparent-tolerance",
        type=int,
        default=8,
        help="Background distance that becomes fully transparent.",
    )
    parser.add_argument(
        "--transparent-softness",
        type=int,
        default=24,
        help="Soft transition range for transparent background edges.",
    )
    parser.add_argument("--preview", action="store_true", help="Create a contact-sheet preview.")
    parser.add_argument(
        "--line-fraction",
        type=float,
        default=0.55,
        help="Minimum fraction of gray pixels needed to count a grid divider.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    input_path = args.input.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output else None

    if args.no_detect_grid and (not args.rows or not args.cols):
        print("--no-detect-grid requires --rows and --cols.", file=sys.stderr)
        return 2

    settings = CutSettings(
        rows=args.rows,
        cols=args.cols,
        detect_grid=not args.no_detect_grid,
        trim=args.trim,
        padding=max(0, args.padding),
        trim_tolerance=max(0, args.trim_tolerance),
        transparent_bg=args.transparent_bg,
        transparent_tolerance=max(0, args.transparent_tolerance),
        transparent_softness=max(0, args.transparent_softness),
        preview=args.preview,
        line_fraction=max(0.01, min(1.0, args.line_fraction)),
    )

    try:
        images = iter_images(input_path, args.recursive)
        if not images:
            print(f"No supported images found in {input_path}", file=sys.stderr)
            return 1

        multiple_inputs = len(images) > 1
        manifests = []
        for image_path in images:
            output_dir = ensure_output_dir(image_path, output, multiple_inputs)
            manifest = cut_image(image_path, output_dir, settings)
            manifests.append(manifest)
            grid = manifest["grid"]
            print(
                f"OK {image_path.name}: {manifest['count']} PNGs "
                f"({grid['cols']}x{grid['rows']}, {grid['source']}) -> {output_dir}"
            )

        if output and multiple_inputs:
            batch_manifest = {
                "input": str(input_path),
                "output": str(output),
                "images": manifests,
            }
            output.mkdir(parents=True, exist_ok=True)
            (output / "batch_manifest.json").write_text(
                json.dumps(batch_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
