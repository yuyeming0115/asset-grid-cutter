---
name: batch-image-upscale
description: Batch upscale image folders while preserving their directory structure. Use when the user asks Codex to enlarge, upscale,高清放大,批量放大, resize, or prepare a folder of PNG/JPG/WebP/BMP/TIFF images for higher-resolution output with a local Pillow backend.
---

# Batch Image Upscale

## Overview

Use this skill to upscale every supported image in a folder while preserving the relative directory structure. The first version uses local Pillow `LANCZOS` resizing, not AI super-resolution or AI redraw.

## Workflow

1. Confirm the input folder and respect the active workspace/user permission rules.
2. Choose a scale factor. Default to `2` when the user does not specify one.
3. Run the bundled script:

```powershell
python scripts/upscale_images.py "D:\path\input_folder" --scale 2
```

When running from outside the skill folder, resolve the script path relative to this `SKILL.md`, for example:

```powershell
python C:\Users\EDY\.codex\skills\batch-image-upscale\scripts\upscale_images.py "D:\path\input_folder" --scale 2
```

4. Report the output folder, image count, skipped count, and manifest path.
5. For verification, inspect a representative original/upscaled pair and confirm dimensions increased as expected.

## Script Behavior

- Supported image extensions: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tif`, `.tiff`.
- Default output folder: sibling `input_folder_upscaled`.
- If the default output folder already exists, the script creates `input_folder_upscaled_02`, `_03`, etc.
- Relative paths are preserved, for example `01/01.png` becomes `01/01.png` in the output folder.
- `preview.png` is skipped by default.
- If `manifest.json` exists and contains `files`, those files are used as the source list.
- The script writes `upscale_manifest.json` in the output folder.

## Common Commands

Upscale by 2x:

```powershell
python scripts/upscale_images.py "D:\path\sheet_cut" --scale 2
```

Upscale by 4x:

```powershell
python scripts/upscale_images.py "D:\path\sheet_cut" --scale 4
```

Choose an explicit output folder:

```powershell
python scripts/upscale_images.py "D:\path\sheet_cut" -o "D:\path\sheet_cut_upscaled" --scale 2
```

Overwrite existing output files:

```powershell
python scripts/upscale_images.py "D:\path\sheet_cut" --scale 2 --overwrite
```

Dry run:

```powershell
python scripts/upscale_images.py "D:\path\sheet_cut" --scale 2 --dry-run
```

## AI Backend Note

This skill intentionally starts with a deterministic Pillow backend. If the user asks for AI super-resolution or AI redraw, explain that a separate backend must be added, such as Real-ESRGAN, ComfyUI, or an image API.
