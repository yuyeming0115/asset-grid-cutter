#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"
export TK_SILENCE_DEPRECATION=1
python3 "$SCRIPT_DIR/asset_grid_cutter_gui.py" "$@"
