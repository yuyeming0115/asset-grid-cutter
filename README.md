# Asset Grid Cutter

Asset Grid Cutter is a small local tool for slicing AI-generated asset sheets into individual PNG files.

它适合处理这种“很多素材排在浅灰网格里”的合集图：可以按真实网格线切割，也可以按固定行列等分切割。日常使用推荐打开本地浏览器 GUI，拖入图片后自动分析并显示预览；大批量处理可以用 CLI。

## Features

- Slice one image or a whole folder of images.
- Detect light gray grid lines automatically.
- Fall back to fixed `rows x columns` splitting.
- Trim blank background around each asset.
- Optionally convert light background to transparent alpha.
- Generate a preview contact sheet.
- Drag an image into the local web GUI for automatic grid analysis.
- Show both analysis preview and output preview.
- Open the output folder from the GUI after processing.
- Write a `manifest.json` for every processed sheet.
- Provide both GUI and command-line workflows.

## Quick Start

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Open the recommended web GUI:

```bash
python3 asset_grid_cutter_web.py
```

The web GUI opens in your browser. Drag an asset sheet into the drop zone and it will automatically analyze the grid, show a grid preview, then let you output PNG slices with a contact-sheet preview.

On macOS, you can also double-click:

```text
Asset Grid Cutter.command
```

The older Tk GUI is still available as a fallback:

```bash
python3 asset_grid_cutter_gui.py
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

## Output

For each input sheet, the tool writes:

- `sheet_r01_c01.png`, `sheet_r01_c02.png`, etc.
- `sheet_preview.png`
- `manifest.json`

## Recommended Workflow

1. Start with the web GUI for a few sample images.
2. Drag an image in and check the automatic grid analysis preview.
3. If the result looks good, use the same settings in CLI for batch processing.
4. Use `--transparent-bg` only after testing, because shadows and highlights may need a non-transparent background.

## License

MIT
