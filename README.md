# Asset Grid Cutter

Asset Grid Cutter is a small local tool for slicing AI-generated asset sheets into individual PNG files.

它适合处理这种“很多素材排在浅灰网格里”的合集图：可以按真实网格线切割，也可以按固定行列等分切割。日常使用推荐打开本地浏览器 GUI，拖入图片后自动分析并显示预览；大批量处理可以用 CLI。

## Features

- Slice one image or a whole folder of images.
- Detect light gray grid lines automatically.
- Detect content-based grids when no visible grid lines exist.
- Fall back to fixed `rows x columns` splitting.
- Trim blank background around each asset.
- Optionally convert light background to transparent alpha.
- Generate a preview contact sheet.
- Drag an image into the local web GUI for automatic grid analysis.
- Drag an existing cut folder into the web GUI for direct upscaling.
- Preserve per-asset folder structure for downstream upscaling.
- Show both analysis preview and output preview.
- Open the output folder from the GUI after processing.
- Write a `manifest.json` for every processed sheet.
- Provide both GUI and command-line workflows.
- Provide a reusable Codex skill for batch image upscaling.

## Quick Start

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Open the recommended web GUI:

```bash
python3 asset_grid_cutter_web.py
```

The web GUI opens in your browser. Drag an asset sheet into the drop zone and it will automatically analyze the grid, show a grid preview, then let you output PNG slices with a contact-sheet preview. You can also drag an existing `*_cut` folder, or use `Upscale Folder`, to upscale a cut folder directly.

On macOS, you can also double-click:

```text
Asset Grid Cutter.command
```

The older Tk GUI is still available as a fallback:

```bash
python3 asset_grid_cutter_gui.py
```

## Windows Usage

On Windows, open PowerShell in the project folder:

```powershell
Set-Location D:\GitWork\asset-grid-cutter
python -m pip install -r requirements.txt
python asset_grid_cutter_web.py
```

The terminal prints a local URL such as:

```text
Asset Grid Cutter Web UI: http://127.0.0.1:8765/
```

If the browser does not open automatically, copy that URL into your browser manually. Keep the PowerShell window open while using the web GUI. If `8765` is already occupied, the tool automatically tries the next free port, for example `8766`.

Fallback Tk GUI:

```powershell
python asset_grid_cutter_gui.py
```

## CLI Usage

Slice one image:

```bash
python3 asset_grid_cutter.py "/path/to/sheet.png" --rows 6 --cols 12 --trim --padding 8 --preview
```

Slice a folder:

```bash
python3 asset_grid_cutter.py "/path/to/folder" -o "/path/to/output" --rows 6 --cols 12 --trim --padding 8 --preview
```

Use equal splitting only:

```bash
python3 asset_grid_cutter.py "/path/to/sheet.png" --rows 6 --cols 12 --no-detect-grid
```

Try transparent background output:

```bash
python3 asset_grid_cutter.py "/path/to/sheet.png" --rows 6 --cols 12 --trim --transparent-bg --preview
```

## Common Options

- `--rows 6 --cols 12`: expected grid size.
- `--trim`: remove blank background around each cell.
- `--padding 8`: keep 8 pixels around the trimmed asset.
- `--preview`: create a contact-sheet preview.
- `--transparent-bg`: convert detected background to transparent alpha.
- `--no-detect-grid`: skip grid-line detection and split evenly.
- `--recursive`: process nested folders.
- `--upscale --scale 2`: upscale an existing cut folder while preserving structure.
- `--flat-output`: write all slices directly in one folder.
- `--long-names`: use source-based row/column names instead of short numeric names.

## Output

For each input sheet, the tool writes:

- `sheet_cut/01/01.png`, `sheet_cut/02/02.png`, etc.
- `preview.png`
- `manifest.json`

Each sliced asset is placed in its own short-numbered folder by default. This keeps the source output ready for high-resolution upscaling workflows: use a parallel folder such as `sheet_cut_upscaled` and keep the same `01/01.png`, `02/02.png` structure instead of mixing originals and upscaled images in one folder.

If you need the old single-folder layout, add `--flat-output`. If you need source-based row/column filenames, add `--long-names`.

## Upscaling

Upscale an existing cut folder while keeping the same folder structure:

```powershell
python asset_grid_cutter.py "D:\path\sheet_cut" --upscale --scale 2
```

This writes a parallel folder such as `sheet_cut_upscaled/01/01.png`, `sheet_cut_upscaled/02/02.png`, etc. The built-in upscaler uses Pillow `LANCZOS` resizing, so it is a local high-quality resize workflow rather than an AI super-resolution model.

In the web GUI, use either path:

- Drag a single source sheet, then click `Cut Assets`, then `Upscale`.
- Drag an existing `*_cut` folder, or click `Upscale Folder`, to upscale that folder directly.

The `Upscale` value controls the scale factor. For example, `2` doubles width and height, while `4` creates a 4x output.

AI redraw or AI super-resolution can be added later as a separate upscale backend, but it needs a concrete model or API provider such as OpenAI Images, Real-ESRGAN, or ComfyUI.

## Codex Skill

This repository also includes a reusable Codex skill:

```text
skills/batch-image-upscale
```

The skill is intended for batch upscaling image folders from Codex while preserving subfolder structure. The installed copy lives in:

```text
C:\Users\EDY\.codex\skills\batch-image-upscale
```

Example:

```powershell
python C:\Users\EDY\.codex\skills\batch-image-upscale\scripts\upscale_images.py "D:\path\sheet_cut" --scale 2
```

The first skill version uses Pillow `LANCZOS`. It is deterministic fast upscaling, not AI super-resolution.

## Recommended Workflow

1. Start with the web GUI for a few sample images.
2. Drag an image in and check the automatic grid analysis preview.
3. Click `Cut Assets` and use the generated `*_cut` folder as the clean source folder.
4. Click `Upscale` in the web GUI, or run `--upscale --scale 2` in CLI, to create a parallel `*_cut_upscaled` folder.
5. Use `--transparent-bg` only after testing, because shadows and highlights may need a non-transparent background.

If you already have a cut folder, skip re-analysis and either drag the folder into the web GUI, click `Upscale Folder`, or use the `batch-image-upscale` skill.

## License

MIT
