"""Export per-footprint SVG files for each unique footprint type on a board.

Python 3.9 compatible — no match/case, no |union syntax, no tomllib.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Dict, Optional

from kicad_pedal_common.footprint import get_footprints
from kicad_pedal_common.plotting import (
    export_footprint_svg,
    parse_svg_viewbox,
    resolve_fp_library,
)


def _safe_dir_name(footprint_id: str) -> str:
    """Convert 'Lib:FootprintName.ext' to a safe directory name."""
    return re.sub(r"[^\w\-]", "_", footprint_id.replace(":", "__"))


def export_footprint_svgs(
    board,
    board_path: str,
    output_dir: str,
    kicad_cli: Optional[str] = None,
    log: Optional[Callable] = None,
) -> Dict[str, Dict]:
    """Export overlay, courtyard, and fab SVGs for each unique footprint type.

    Returns a dict mapping footprint_id to:
        {
            "overlay_svg":   zip-relative path (str) or None,
            "fab_svg":       zip-relative path (str) or None,
            "courtyard_svg": zip-relative path (str) or None,
            "bbox":          {"x": float, "y": float, "w": float, "h": float} or None,
        }

    Footprint IDs for which library resolution or kicad-cli export fails are
    omitted; the caller falls back to the existing bbox outline for those.
    """

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    fp_dicts = get_footprints(board)

    # Collect unique footprint IDs (skip empties and back-layer footprints).
    seen: Dict[str, bool] = {}
    for fp in fp_dicts:
        fp_id = fp.get("footprint_id", "")
        if fp_id and fp_id not in seen:
            seen[fp_id] = True

    result: Dict[str, Dict] = {}

    for fp_id in sorted(seen.keys()):
        if ":" not in fp_id:
            _log("WARNING: unparseable footprint_id {!r}, skipping SVG export".format(fp_id))
            continue

        lib_nickname, fp_name = fp_id.split(":", 1)
        lib_path = resolve_fp_library(lib_nickname, board_path=board_path)

        if lib_path is None:
            _log(
                "WARNING: library {!r} not in fp-lib-table, skipping SVG for {}".format(
                    lib_nickname, fp_id
                )
            )
            continue

        safe = _safe_dir_name(fp_id)
        fp_out_dir = os.path.join(output_dir, "fp", safe)
        os.makedirs(fp_out_dir, exist_ok=True)

        # --- Courtyard only (extract bounding box via viewBox) ---
        courtyard_abs = os.path.join(fp_out_dir, "courtyard.svg")
        courtyard_zip = None
        bbox = None
        try:
            export_footprint_svg(
                lib_path, fp_name, "F.Courtyard", courtyard_abs, kicad_cli=kicad_cli
            )
            courtyard_zip = "fp/{}/courtyard.svg".format(safe)
            vb = parse_svg_viewbox(courtyard_abs)
            if vb:
                bbox = {"x": vb[0], "y": vb[1], "w": vb[2], "h": vb[3]}
        except Exception as exc:
            _log("WARNING: courtyard SVG failed for {}: {}".format(fp_id, exc))

        # --- Overlay: F.Courtyard + F.Cu + F.Mask ---
        overlay_abs = os.path.join(fp_out_dir, "overlay.svg")
        overlay_zip = None
        try:
            export_footprint_svg(
                lib_path,
                fp_name,
                "F.Courtyard,F.Cu,F.Mask",
                overlay_abs,
                kicad_cli=kicad_cli,
            )
            overlay_zip = "fp/{}/overlay.svg".format(safe)
        except Exception as exc:
            _log("WARNING: overlay SVG failed for {}: {}".format(fp_id, exc))

        # --- Fab layer (hidden by default in build-manager) ---
        fab_abs = os.path.join(fp_out_dir, "fab.svg")
        fab_zip = None
        try:
            export_footprint_svg(
                lib_path, fp_name, "F.Fab", fab_abs, kicad_cli=kicad_cli
            )
            fab_zip = "fp/{}/fab.svg".format(safe)
        except Exception as exc:
            _log("WARNING: fab SVG failed for {}: {}".format(fp_id, exc))

        if overlay_zip or bbox:
            result[fp_id] = {
                "overlay_svg": overlay_zip,
                "fab_svg": fab_zip,
                "courtyard_svg": courtyard_zip,
                "bbox": bbox,
            }
            _log("Footprint SVG exported: {}".format(fp_id))

    return result
