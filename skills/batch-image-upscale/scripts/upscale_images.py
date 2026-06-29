#!/usr/bin/env python3
"""Batch-upscale image folders while preserving relative paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - exercised by environment setup
    raise SystemExit("Pillow is required. Install it with: python -m pip install Pillow") from exc


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
DEFAULT_SKIP_NAMES = {"preview.png"}


def positive_scale(value: str) -> float:
    scale = float(value)
    if scale <= 0:
        raise argparse.ArgumentTypeError("scale must be greater than 0")
    return scale


def next_available_dir(path: Path) -> Path:
    if not path.exists():
        return path

    for index in range(2, 1000):
        candidate = path.with_name(f"{path.name}_{index:02d}")
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Too many output folders named like {path.name}")


def default_output_dir(input_dir: Path) -> Path:
    suffix = "_upscaled"
    if input_dir.name.endswith(suffix):
        return input_dir.with_name(f"{input_dir.name}_next")
    return input_dir.with_name(f"{input_dir.name}{suffix}")


def manifest_files(input_dir: Path) -> list[Path]:
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.exists():
        return []

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    paths = []
    for rel_path in data.get("files", []):
        path = input_dir / rel_path
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            paths.append(path)
    return paths


def discover_images(input_dir: Path, include_preview: bool) -> list[Path]:
    files = manifest_files(input_dir)
    if not files:
        files = [
            path
            for path in input_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]

    if not include_preview:
        files = [path for path in files if path.name.lower() not in DEFAULT_SKIP_NAMES]

    return sorted(files)


def scaled_size(width: int, height: int, scale: float) -> tuple[int, int]:
    return max(1, round(width * scale)), max(1, round(height * scale))


def create_preview(image_paths: Iterable[Path], output_path: Path, thumb_size: int = 128) -> None:
    paths = list(image_paths)
    if not paths:
        return

    thumbs: list[Image.Image] = []
    labels: list[str] = []
    for path in paths[:144]:
        image = Image.open(path).convert("RGBA")
        image.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
        tile = Image.new("RGBA", (thumb_size, thumb_size), (246, 246, 246, 255))
        x = (thumb_size - image.width) // 2
        y = (thumb_size - image.height) // 2
        tile.alpha_composite(image, (x, y))
        thumbs.append(tile.convert("RGB"))
        labels.append(path.stem[-16:])

    cols = min(12, max(1, round(len(thumbs) ** 0.5)))
    rows = (len(thumbs) + cols - 1) // cols
    gap = 8
    label_h = 18
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
        label = labels[index]
        bbox = draw.textbbox((0, 0), label, font=font)
        draw.text((x + (thumb_size - (bbox[2] - bbox[0])) // 2, y + thumb_size + 3), label, fill=(70, 77, 87), font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def upscale_folder(
    input_dir: Path,
    output_dir: Path | None,
    scale: float,
    overwrite: bool,
    include_preview: bool,
    write_preview: bool,
    dry_run: bool,
) -> dict:
    input_dir = input_dir.resolve()
    if not input_dir.is_dir():
        raise ValueError(f"Input folder does not exist: {input_dir}")

    if output_dir is None:
        output_dir = next_available_dir(default_output_dir(input_dir))
    else:
        output_dir = output_dir.resolve()

    if output_dir == input_dir:
        raise ValueError("Output folder must be different from input folder.")

    images = discover_images(input_dir, include_preview)
    if not images:
        raise ValueError(f"No supported images found in {input_dir}")

    written: list[Path] = []
    skipped: list[Path] = []

    for source_path in images:
        rel_path = source_path.relative_to(input_dir)
        target_path = output_dir / rel_path
        if target_path.exists() and not overwrite:
            skipped.append(target_path)
            continue

        if dry_run:
            written.append(target_path)
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source_path) as image:
            upscaled = image.resize(scaled_size(image.width, image.height, scale), Image.Resampling.LANCZOS)
            upscaled.save(target_path)
        written.append(target_path)

    preview_path = None
    if write_preview and written and not dry_run:
        preview_path = output_dir / "preview.png"
        create_preview(written, preview_path)

    manifest = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "scale": scale,
        "method": "Pillow LANCZOS",
        "count": len(written),
        "skipped": len(skipped),
        "dry_run": dry_run,
        "files": [path.relative_to(output_dir).as_posix() for path in written],
        "skipped_files": [path.relative_to(output_dir).as_posix() for path in skipped],
        "preview": preview_path.name if preview_path else None,
    }

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "upscale_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch-upscale image folders while preserving relative paths.")
    parser.add_argument("input_dir", type=Path, help="Folder containing images to upscale.")
    parser.add_argument("-o", "--output", type=Path, help="Output folder. Defaults to sibling *_upscaled.")
    parser.add_argument("--scale", type=positive_scale, default=2.0, help="Scale factor. Default: 2.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files.")
    parser.add_argument("--include-preview", action="store_true", help="Also upscale preview.png files.")
    parser.add_argument("--no-preview", action="store_true", help="Do not write an output preview.png contact sheet.")
    parser.add_argument("--dry-run", action="store_true", help="Print intended work without writing images.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = upscale_folder(
            input_dir=args.input_dir,
            output_dir=args.output,
            scale=args.scale,
            overwrite=args.overwrite,
            include_preview=args.include_preview,
            write_preview=not args.no_preview,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Output: {manifest['output_dir']}")
    print(f"Upscaled: {manifest['count']}")
    print(f"Skipped: {manifest['skipped']}")
    print(f"Scale: {manifest['scale']}x")
    if not manifest["dry_run"]:
        print(f"Manifest: {Path(manifest['output_dir']) / 'upscale_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
