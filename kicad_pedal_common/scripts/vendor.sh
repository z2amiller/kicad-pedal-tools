#!/usr/bin/env bash
# Usage: vendor.sh <target_dir>
# Copies kicad_pedal_common/ source into target_dir for PCM archive building.
set -euo pipefail
TARGET="${1:?Usage: vendor.sh <target_dir>}"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cp -rf "$SCRIPT_DIR/kicad_pedal_common" "$TARGET/"
echo "Vendored kicad_pedal_common -> $TARGET/kicad_pedal_common"
