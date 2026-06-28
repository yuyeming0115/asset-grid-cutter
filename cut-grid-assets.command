#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"

if [ "$#" -eq 0 ]; then
  echo "把图片或图片文件夹拖到这个 command 文件上，或在终端传入路径。"
  echo "示例：$0 /path/to/sheet.png"
  exit 1
fi

for input_path in "$@"; do
  python3 "$SCRIPT_DIR/asset_grid_cutter.py" "$input_path" \
    --rows 6 \
    --cols 12 \
    --trim \
    --padding 8 \
    --preview
done
