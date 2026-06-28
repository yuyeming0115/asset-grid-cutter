#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"
python3 "$SCRIPT_DIR/asset_grid_cutter_web.py" "$@"
