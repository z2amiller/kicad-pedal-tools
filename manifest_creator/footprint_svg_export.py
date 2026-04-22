"""Export per-footprint SVG files for each unique footprint type on a board.

Python 3.9 compatible — no match/case, no |union syntax, no tomllib.
"""

from __future__ import annotations

import math
import os
import re
from typing import Callable, Dict, List, Optional, Tuple

from kicad_pedal_common.footprint import get_footprints
from kicad_pedal_common.plotting import (
    export_footprint_svg,
    parse_svg_viewbox,
    resolve_fp_library,
)


def _parse_svg_pad_centers(svg_path: str) -> List[Tuple[float, float]]:
    """Return (cx, cy) pad centre positions from an overlay SVG.

    Handles two shapes kicad-cli uses for THT drill holes:
    - Round drills     → <circle cx="…" cy="…" …>
    - Oval/slot drills → <path d="M x1 y1 L x2 y2"> inside a stroke:#FFFFFF group

    kicad-cli renders drill holes with a black outer shape then a white inner
    cutout.  The white (stroke:#FFFFFF) paths are unique to drill slots —
    silkscreen, courtyard, and fab lines are always black or coloured, never
    white.  Restricting to white groups avoids false matches on body outlines.
    """
    try:
        with open(svg_path, encoding="utf-8") as fh:
            data = fh.read()
        results: List[Tuple[float, float]] = []

        # Round drills (circles are unambiguous — keep as-is)
        for m in re.finditer(r'<circle\b[^>]*>', data):
            tag = m.group(0)
            cx_m = re.search(r'\bcx="([^"]+)"', tag)
            cy_m = re.search(r'\bcy="([^"]+)"', tag)
            if cx_m and cy_m:
                results.append((float(cx_m.group(1)), float(cy_m.group(1))))

        # Oval/slot drills: only match M-L paths inside stroke:#FFFFFF groups.
        # Parse as a stream: track current group stroke color, emit midpoints
        # only when inside a white group.
        in_white_group = False
        group_depth = 0
        white_entry_depth: Optional[int] = None
        for tok in re.split(r'(<[^>]+>)', data):
            if not tok.startswith('<'):
                continue
            if re.match(r'<g\b', tok):
                group_depth += 1
                if re.search(r'stroke:#FFFFFF', tok):
                    in_white_group = True
                    white_entry_depth = group_depth
            elif tok.startswith('</g'):
                if in_white_group and group_depth == white_entry_depth:
                    in_white_group = False
                    white_entry_depth = None
                group_depth -= 1
            elif in_white_group and re.match(r'<path\b', tok):
                m = re.search(
                    r'd="M\s*([-\d.]+)\s+([-\d.]+)\s*\n?L\s*([-\d.]+)\s+([-\d.]+)\s*\n?"',
                    tok,
                )
                if m:
                    x1, y1 = float(m.group(1)), float(m.group(2))
                    x2, y2 = float(m.group(3)), float(m.group(4))
                    results.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))

        return results
    except Exception:
        return []


def _compute_anchor_from_pad_match(
    circles: List[Tuple[float, float]],
    pad_xy_list: List[Tuple[float, float]],
    snap_threshold: float = 0.1,
) -> Optional[Tuple[float, float]]:
    """Compute anchor (footprint origin in SVG coords) by translation voting.

    Each (circle_i, pad_j) pair defines a candidate translation T where
    T = circle_i - pad_j.  The correct T has every pad matching some circle.
    We vote: for each candidate T, count how many pads are explained by a
    circle within snap_threshold mm.  The T with the most votes wins.

    This is robust even when pads have a large offset from the body (e.g.
    back-mount pots with body 25 mm above mounting pads) where nearest-pad
    distance matching assigns pads to the wrong circles.

    Returns (anchor_x, anchor_y) or None if no consistent translation found.
    """
    if not circles or not pad_xy_list:
        return None

    # Deduplicate circles (kicad-cli sometimes emits duplicate circles)
    unique_circles: List[Tuple[float, float]] = []
    for c in circles:
        if not any(math.hypot(c[0] - u[0], c[1] - u[1]) < snap_threshold for u in unique_circles):
            unique_circles.append(c)

    best_votes = 0
    best_tx = 0.0
    best_ty = 0.0

    # Try every (circle, pad) pair as the seed translation
    for svg_cx, svg_cy in unique_circles:
        for pad_x, pad_y in pad_xy_list:
            tx = svg_cx - pad_x
            ty = svg_cy - pad_y

            # Count how many pads are explained (pad + T ≈ some circle)
            votes = 0
            for px, py in pad_xy_list:
                expected_x = px + tx
                expected_y = py + ty
                if any(
                    math.hypot(expected_x - cx, expected_y - cy) < snap_threshold
                    for cx, cy in unique_circles
                ):
                    votes += 1

            if votes > best_votes:
                best_votes = votes
                best_tx = tx
                best_ty = ty

    # Only accept if at least half the pads are explained
    min_votes = max(1, len(pad_xy_list) // 2)
    if best_votes < min_votes:
        return None

    return (round(best_tx, 4), round(best_ty, 4))


def _pads_from_kicad_mod(lib_path: str, fp_name: str) -> List[Tuple[float, float]]:
    """Return local (x, y) pad positions from a .kicad_mod file.

    Tries kiutils first (exact parser), falls back to regex on the raw
    S-expression so this works even without kiutils installed.
    """
    mod_path = os.path.join(lib_path, fp_name + ".kicad_mod")
    try:
        from kiutils.footprint import Footprint as _Fp
        fp = _Fp.from_file(mod_path)
        return [(float(p.position.X), float(p.position.Y)) for p in fp.pads]
    except Exception:
        pass
    # Regex fallback: match (pad ... (at X Y ...))
    try:
        with open(mod_path, encoding="utf-8") as fh:
            data = fh.read()
        pads = []
        for m in re.finditer(r'\(pad\b[^(]*\(at\s+([-\d.]+)\s+([-\d.]+)', data):
            pads.append((float(m.group(1)), float(m.group(2))))
        return pads
    except Exception:
        return []


def _safe_dir_name(footprint_id: str) -> str:
    """Convert 'Lib:FootprintName.ext' to a safe directory name."""
    return re.sub(r"[^\w\-]", "_", footprint_id.replace(":", "__"))


def export_footprint_svgs(
    board,
    board_path: str,
    output_dir: str,
    kicad_cli: Optional[str] = None,
    log: Optional[Callable] = None,
    bbox_offsets: Optional[Dict[str, Tuple[float, float]]] = None,
    adapter=None,
) -> Dict[str, Dict]:
    """Export overlay, courtyard, and fab SVGs for each unique footprint type.

    Returns a dict mapping footprint_id to:
        {
            "overlay_svg":   zip-relative path (str) or None,
            "fab_svg":       zip-relative path (str) or None,
            "courtyard_svg": zip-relative path (str) or None,
            "bbox":          {"x": float, "y": float, "w": float, "h": float} or None,
            "anchor_x":      float or None,  # footprint origin x within overlay SVG (mm)
            "anchor_y":      float or None,  # footprint origin y within overlay SVG (mm)
        }

    Footprint IDs for which library resolution or kicad-cli export fails are
    omitted; the caller falls back to the existing bbox outline for those.
    """

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    if adapter is not None:
        fp_dicts = [
            {
                "footprint_id": fp.footprint_id,
                "layer": fp.layer,
            }
            for fp in adapter.get_footprints()
        ]
    else:
        fp_dicts = get_footprints(board)

    # Collect unique footprint IDs (skip empties).
    seen: set = set()
    for fp in fp_dicts:
        fp_id = fp.get("footprint_id", "")
        if fp_id:
            seen.add(fp_id)

    result: Dict[str, Dict] = {}
    unique_ids = sorted(seen)
    _log("Exporting SVGs for {} unique footprint types ({} total placements)".format(
        len(unique_ids), len(fp_dicts)
    ))

    for idx, fp_id in enumerate(unique_ids, 1):
        if ":" not in fp_id:
            _log("WARNING: unparseable footprint_id {!r}, skipping SVG export".format(fp_id))
            continue

        lib_nickname, fp_name = fp_id.split(":", 1)
        _log("[{}/{}] {}".format(idx, len(unique_ids), fp_id))
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
            # Compute the anchor: the position of the footprint origin within the
            # overlay SVG.  kicad-cli centers the full footprint bounding-box at
            # (vb_w/2, vb_h/2).
            anchor_x = None
            anchor_y = None
            if overlay_zip:
                # Strategy 1: pad-matching via SVG circles (THT drill holes).
                # kicad-cli renders THT pads as <circle> elements whose centres
                # are in local mm coords.  We read the same coords from the
                # .kicad_mod library file so this works for all export paths.
                circles = _parse_svg_pad_centers(overlay_abs)
                if circles and lib_path is not None:
                    pads = _pads_from_kicad_mod(lib_path, fp_name)
                    if pads:
                        match_result = _compute_anchor_from_pad_match(circles, pads)
                        if match_result is not None:
                            anchor_x, anchor_y = match_result
                            _log("  → anchor via pad-match ({}, {})".format(anchor_x, anchor_y))

                # Strategy 2: geometry bbox centre offset fallback.
                if anchor_x is None and bbox_offsets is not None:
                    fp_offset = bbox_offsets.get(fp_id)
                    if fp_offset is not None:
                        cx_local, cy_local = fp_offset
                        vb = parse_svg_viewbox(overlay_abs)
                        if vb:
                            anchor_x = round(vb[2] / 2.0 - cx_local, 4)
                            anchor_y = round(vb[3] / 2.0 - cy_local, 4)

            result[fp_id] = {
                "overlay_svg": overlay_zip,
                "fab_svg": fab_zip,
                "courtyard_svg": courtyard_zip,
                "bbox": bbox,
                "anchor_x": anchor_x,
                "anchor_y": anchor_y,
            }
            if anchor_x is None:
                _log("  → ok (no anchor computed)")

    return result
