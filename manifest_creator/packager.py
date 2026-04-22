"""Create a .manifest.zip artifact from a KiCad board."""

from __future__ import annotations

import json
import math
import os
import pathlib
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import jsonschema
import jsonschema.exceptions
from referencing import Registry, Resource

from manifest_creator.bom_export import export_bom, export_bom_from_adapter
from manifest_creator.footprint_svg_export import export_footprint_svgs
from manifest_creator.svg_export import export_all_layers

# Path to the vendored schema files (relative to this file's package root)
_SCHEMA_DIR = pathlib.Path(__file__).parent.parent / "kicad_pedal_common" / "schema"


def _load_schema(name: str) -> Dict:
    with open(_SCHEMA_DIR / name) as f:
        return json.load(f)


def _rewrite_svg_viewbox(svg_path: str, x: float, y: float, w: float, h: float) -> None:
    """Crop an SVG's viewBox to the board area, updating width/height attributes."""
    try:
        with open(svg_path, encoding="utf-8") as fh:
            data = fh.read()
        vb_new = "{:.4f} {:.4f} {:.4f} {:.4f}".format(x, y, w, h)
        data = re.sub(r'viewBox="[^"]*"', 'viewBox="{}"'.format(vb_new), data)
        data = re.sub(r'width="[^"]*mm"', 'width="{:.4f}mm"'.format(w), data)
        data = re.sub(r'height="[^"]*mm"', 'height="{:.4f}mm"'.format(h), data)
        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(data)
    except OSError:
        pass


def _validate_manifest(manifest: Dict) -> None:
    """Validate manifest dict against the JSON Schema."""
    top_schema = _load_schema("manifest-v1.schema.json")
    entry_schema = _load_schema("bom-entry.schema.json")

    registry = Registry().with_resource(
        entry_schema["$id"],
        Resource.from_contents(entry_schema),
    )
    validator = jsonschema.Draft7Validator(top_schema, registry=registry)
    errors = list(validator.iter_errors(manifest))
    if errors:
        best = jsonschema.exceptions.best_match(errors)
        raise jsonschema.ValidationError(
            "Manifest failed schema validation: {}".format(best.message),
            context=errors,
        )


def create_manifest_zip(
    board,
    board_path: str,
    output_path: str,
    version: str,
    display_name: Optional[str] = None,
    kicad_cli: Optional[str] = None,
    log: Optional[Callable] = None,
    adapter=None,
) -> str:
    """Build a .manifest.zip from a KiCad board.

    Parameters
    ----------
    board:
        kipy board object.  Pass None to use *adapter* or for SVG-only mode.
    adapter:
        BoardAdapter instance (e.g. KiutilsBoardAdapter) for headless export.
        Takes precedence over *board* when provided.
    board_path:
        Absolute path to the .kicad_pcb file on disk.
    output_path:
        Destination path for the produced .zip file.
    version:
        Version string, e.g. ``"1.0.0"``.
    display_name:
        Human-readable name.  Defaults to the board file stem.
    kicad_cli:
        Explicit path to kicad-cli.  None = auto-locate.
    log:
        Optional ``log(msg: str)`` callback for progress messages.

    Returns
    -------
    str
        The ``output_path`` that was written.
    """
    from kicad_pedal_common.footprint import get_footprint_bbox_center_offset
    from kicad_pedal_common.plotting import (
        compute_svg_transform,
        parse_kicad_pcb_edge_cuts_bbox,
    )

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    board_stem = pathlib.Path(board_path).stem
    board_name = board_stem.lower().replace("_", "-").replace(" ", "-")
    if display_name is None:
        display_name = board_stem

    # Look for blurb.md next to the .kicad_pcb (exact stem match, then fallback names).
    _board_dir = pathlib.Path(board_path).parent
    _blurb_candidates = [
        _board_dir / (board_stem + ".md"),
        _board_dir / "blurb.md",
        _board_dir / "README.md",
    ]
    blurb_path = next((p for p in _blurb_candidates if p.exists()), None)

    _log("Exporting SVG layers…")
    with tempfile.TemporaryDirectory() as tmp_dir:
        layers_map: Dict[str, str] = export_all_layers(
            board_path=board_path,
            output_dir=tmp_dir,
            kicad_cli=kicad_cli,
            log=log,
        )

        _log("Exporting BOM…")
        # adapter kwarg is used by the standalone CLI (KiutilsBoardAdapter).
        # The IPC plugin always passes board= and leaves adapter=None so that
        # the existing export_bom(board) path — which uses kipy bounding boxes —
        # is preserved unchanged.
        if adapter is not None:
            components: List[Dict] = export_bom_from_adapter(adapter)
        elif board is not None:
            components = export_bom(board)
        else:
            components = []

        # Compute bounding-box centre offsets per footprint type so the SVG
        # exporter can calculate accurate anchor positions.
        bbox_offsets: Dict[str, tuple] = {}
        if adapter is not None:
            try:
                seen_fp_ids: set = set()
                for fp_data in adapter.get_footprints():
                    fp_id = fp_data.footprint_id
                    if not fp_id or fp_id in seen_fp_ids:
                        continue
                    seen_fp_ids.add(fp_id)
                    bbox_center = adapter.get_item_bounding_box(fp_data)
                    if bbox_center is not None:
                        rot = math.radians(fp_data.rotation)
                        dx, dy = bbox_center.cx_mm, bbox_center.cy_mm
                        cx_local = dx * math.cos(rot) - dy * math.sin(rot)
                        cy_local = dx * math.sin(rot) + dy * math.cos(rot)
                        bbox_offsets[fp_id] = (cx_local, cy_local)
            except Exception as exc:
                _log("WARNING: could not compute bbox offsets: {}".format(exc))
        elif board is not None:
            try:
                seen_fp_ids = set()
                for fp in board.get_footprints():
                    try:
                        fp_id = "{}:{}".format(
                            fp.definition.id.library, fp.definition.id.name
                        )
                    except Exception:
                        continue
                    if fp_id in seen_fp_ids:
                        continue
                    seen_fp_ids.add(fp_id)
                    offset = get_footprint_bbox_center_offset(board, fp)
                    if offset is not None:
                        bbox_offsets[fp_id] = offset
            except Exception as exc:
                _log("WARNING: could not compute bbox offsets: {}".format(exc))

        _log("Exporting footprint SVGs…")
        fp_svgs: Dict[str, Dict] = {}
        if board is not None or adapter is not None:
            try:
                fp_svgs = export_footprint_svgs(
                    board, board_path, tmp_dir, kicad_cli=kicad_cli, log=log,
                    bbox_offsets=bbox_offsets if bbox_offsets else None,
                    adapter=adapter,
                )
            except Exception as exc:
                _log("WARNING: footprint SVG export failed: {}".format(exc))

        if fp_svgs:
            _log("Merging footprint SVG outlines into components…")
            for comp in components:
                svg_data = fp_svgs.get(comp.get("footprint", ""))
                if svg_data and svg_data.get("overlay_svg") and svg_data.get("bbox"):
                    comp["outline"] = {
                        "type": "svg",
                        "overlay_svg": svg_data["overlay_svg"],
                        "fab_svg": svg_data.get("fab_svg"),
                        "courtyard_svg": svg_data.get("courtyard_svg"),
                        "bbox": svg_data["bbox"],
                        "anchor_x": svg_data.get("anchor_x"),
                        "anchor_y": svg_data.get("anchor_y"),
                    }

        # --- Coordinate normalisation ---
        # Compute the SVG page-coordinate offset from edge cuts, then rewrite
        # all component positions to board-relative mm (0,0 = top-left corner
        # of the board outline).  Also crop every layer SVG's viewBox to the
        # board area so the renderer can use the SVG directly without knowing
        # the KiCad page layout.
        _log("Computing coordinate transform from edge cuts…")
        pcb_bbox = parse_kicad_pcb_edge_cuts_bbox(board_path)
        edge_cuts_zip = layers_map.get("edge_cuts")
        edge_cuts_abs = (
            str(pathlib.Path(tmp_dir) / edge_cuts_zip) if edge_cuts_zip else None
        )

        if pcb_bbox is not None and edge_cuts_abs and os.path.exists(edge_cuts_abs):
            transform = compute_svg_transform(board_path, edge_cuts_abs)
            offset_x = transform["offset_x"]
            offset_y = transform["offset_y"]
            pcb_min_x, pcb_min_y, pcb_max_x, pcb_max_y = pcb_bbox
            pcb_w = round(pcb_max_x - pcb_min_x, 4)
            pcb_h = round(pcb_max_y - pcb_min_y, 4)
            # SVG page coordinates of the board's top-left corner
            svg_board_x = round(pcb_min_x + offset_x, 4)
            svg_board_y = round(pcb_min_y + offset_y, 4)
        else:
            _log("WARNING: could not compute coordinate transform; positions may be wrong")
            offset_x = 0.0
            offset_y = 0.0
            pcb_min_x = pcb_min_y = 0.0
            pcb_w = 60.96
            pcb_h = 76.2
            svg_board_x = svg_board_y = 0.0

        # board_bounds.x/y stores the SVG page origin of the board top-left.
        # The compositor uses this to translate layer paths to board-relative
        # coords (0,0 = top-left) via <g transform="translate(-x, -y)">.
        board_bounds = {
            "x": round(svg_board_x, 4),
            "y": round(svg_board_y, 4),
            "width": pcb_w,
            "height": pcb_h,
        }

        # Component positions are board-relative mm (0,0 = top-left of board).
        # The compositor renders them directly against the 0 0 w h viewBox.
        for comp in components:
            comp["pos_x"] = round(comp["pos_x"] - pcb_min_x, 4)
            comp["pos_y"] = round(comp["pos_y"] - pcb_min_y, 4)

        # Crop all layer SVG viewBoxes to the board area
        _log("Cropping SVG viewBoxes to board area…")
        for zip_path in layers_map.values():
            svg_file = str(pathlib.Path(tmp_dir) / zip_path)
            if os.path.exists(svg_file):
                _rewrite_svg_viewbox(svg_file, svg_board_x, svg_board_y, pcb_w, pcb_h)

        _log("Building manifest…")
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # PCB drill holes — all THT/NPTH pads, board-relative mm.
        drill_holes: list = []
        if adapter is not None:
            try:
                raw_holes = adapter.get_drill_holes()
                for h in raw_holes:
                    drill_holes.append({
                        "x_mm": round(h.x_mm - pcb_min_x, 4),
                        "y_mm": round(h.y_mm - pcb_min_y, 4),
                        "diameter_mm": h.diameter_mm,
                        "label": h.label,
                        "plated": h.plated,
                        "oval": h.oval,
                    })
                _log("Collected {} PCB drill holes.".format(len(drill_holes)))
            except Exception as exc:
                _log("WARNING: drill hole extraction failed: {}".format(exc))

        manifest: Dict = {
            "schema_version": "1.0",
            "board_name": board_name,
            "display_name": display_name,
            "version": version,
            "created_at": created_at,
            "board_bounds": board_bounds,
            "layers": layers_map,
            "components": components,
            "has_blurb": blurb_path is not None,
            "drill_holes": drill_holes,
        }

        _log("Validating manifest against schema…")
        _validate_manifest(manifest)

        _log("Writing zip to {}…".format(output_path))
        manifest_json = json.dumps(manifest, indent=2)

        output_parent = pathlib.Path(output_path).parent
        output_parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", manifest_json)

            for zip_path in layers_map.values():
                svg_file = pathlib.Path(tmp_dir) / zip_path
                if svg_file.exists():
                    zf.write(svg_file, zip_path)
                else:
                    _log("WARNING: SVG file not found: {}".format(svg_file))

            for svg_data in fp_svgs.values():
                for key in ("overlay_svg", "fab_svg", "courtyard_svg"):
                    zip_path = svg_data.get(key)
                    if zip_path:
                        svg_file = pathlib.Path(tmp_dir) / zip_path
                        if svg_file.exists():
                            zf.write(svg_file, zip_path)

            if blurb_path is not None:
                zf.write(blurb_path, "blurb.md")
                _log("Bundled blurb: {}".format(blurb_path.name))

    _log("Done: {}".format(output_path))
    return output_path
