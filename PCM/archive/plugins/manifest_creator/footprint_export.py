"""Export footprint geometry (position, rotation, outline) for overlay rendering."""

from __future__ import annotations

from typing import Dict, List

from kicad_pedal_common.footprint import get_bounding_box, get_footprints


def export_footprint_geometries(board) -> List[Dict]:
    """Return a list of footprint geometry dicts (ref, pos_x, pos_y, rotation, outline)
    for all non-excluded footprints.
    Only includes footprints on the front layer (F) — back layer is v2 scope.
    """
    fp_dicts = get_footprints(board)

    # Build a mapping from ref -> raw footprint object for get_bounding_box.
    fp_by_ref: Dict[str, object] = {}
    try:
        for fp in board.get_footprints():
            try:
                ref = fp.reference_field.text.value
                if ref and not ref.startswith("~") and ref not in ("REF**", ""):
                    fp_by_ref[ref] = fp
            except Exception:
                pass
    except Exception:
        pass

    result: List[Dict] = []
    for fp_dict in fp_dicts:
        # Only front layer, and not excluded from BOM
        if fp_dict["layer"] != "F":
            continue
        if fp_dict["exclude_from_bom"]:
            continue

        ref = fp_dict["ref"]
        fp_obj = fp_by_ref.get(ref)

        if fp_obj is not None:
            bbox_dict = get_bounding_box(fp_obj)
        else:
            bbox_dict = {"w": 5.0, "h": 5.0}

        result.append(
            {
                "ref": ref,
                "pos_x": fp_dict["pos_x"],
                "pos_y": fp_dict["pos_y"],
                "rotation": fp_dict["rotation"],
                "outline": {"type": "bbox", "bbox": bbox_dict},
            }
        )

    return result
