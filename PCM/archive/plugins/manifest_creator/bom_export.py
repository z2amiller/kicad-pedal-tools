"""Export BOM data from a kipy board as a list of component dicts."""

from __future__ import annotations

from typing import Dict, List

from kicad_pedal_common.footprint import get_bounding_box, get_footprints


def export_bom(board) -> List[Dict]:
    """Extract all components from a kipy board and return them as a list of
    dicts matching the manifest bom-entry schema.

    Calls get_footprints() from kicad_pedal_common.footprint, enriches each
    entry with a bounding-box outline, and returns the full list.
    DNP and exclude_from_bom components ARE included (flagged).
    """
    fp_dicts = get_footprints(board)

    # Build a mapping from ref -> raw footprint object so we can call
    # get_bounding_box on the original kipy object.
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
        ref = fp_dict["ref"]
        fp_obj = fp_by_ref.get(ref)

        if fp_obj is not None:
            bbox_dict = get_bounding_box(fp_obj)
        else:
            bbox_dict = {"w": 5.0, "h": 5.0}

        result.append(
            {
                "ref": ref,
                "value": fp_dict["value"],
                "footprint": fp_dict["footprint_id"],
                "description": "",
                "notes": "",
                "layer": fp_dict["layer"],
                "pos_x": fp_dict["pos_x"],
                "pos_y": fp_dict["pos_y"],
                "rotation": fp_dict["rotation"],
                "do_not_populate": fp_dict["dnp"],
                "exclude_from_bom": fp_dict["exclude_from_bom"],
                "outline": {"type": "bbox", "bbox": bbox_dict},
            }
        )

    return result
