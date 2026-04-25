"""KiutilsBoardAdapter — reads a .kicad_pcb file without a live KiCad session.

Uses the kiutils library (pip install kiutils) to parse the S-expression board
file directly, enabling headless / standalone manifest export.

Key differences from KipyBoardAdapter (kipy uses nanometres; kiutils uses mm):
- All positions/sizes from kiutils are already in mm.
- Pad positions are in footprint-LOCAL coordinates (not board coords).
- Rotation comes from fp.position.angle (degrees, not radians).
- No equivalent of board.get_item_bounding_box — we derive it from pads.

Python 3.9 compatible.
"""

from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, Tuple

from kicad_pedal_common.board_adapter import (
    BBoxCenter,
    BoardAdapter,
    FootprintData,
)
from kicad_pedal_common.drill import DrillHole, get_drill_holes_kiutils


class KiutilsBoardAdapter(BoardAdapter):
    """BoardAdapter implementation backed by a kiutils Board parsed from disk."""

    def __init__(self, pcb_path: str) -> None:
        from kiutils.board import Board  # deferred so absence of kiutils fails late

        _patch_kiutils_kicad10_compat()
        self._pcb_path = os.path.abspath(pcb_path)
        self._board = Board.from_file(pcb_path)

    # ------------------------------------------------------------------
    # BoardAdapter interface
    # ------------------------------------------------------------------

    def get_drill_holes(self) -> List[DrillHole]:
        """Return all THT/NPTH drill holes in board-space mm."""
        try:
            return get_drill_holes_kiutils(self._board)
        except Exception:
            return []

    def get_footprints(self) -> List[FootprintData]:
        result: List[FootprintData] = []
        try:
            for fp in self._board.footprints:
                fp_data = self._parse_footprint(fp)
                if fp_data is not None:
                    result.append(fp_data)
        except Exception:
            pass
        return result

    def get_item_bounding_box(
        self, fp_data: FootprintData
    ) -> Optional[BBoxCenter]:
        """Derive bounding-box centre from full footprint geometry.

        Uses all graphicItems (silkscreen lines, fab outlines, circles) plus
        pad positions/sizes to compute the footprint's local bounding box.
        This matches kicad-cli's SVG viewBox much better than pad-only, which
        fails badly for components whose body extends far from the pads (e.g.
        right-angle pots where the body is entirely above the mounting pins).

        Positions are footprint-LOCAL mm coordinates (kiutils stores them that
        way in placed footprints).  We rotate the local bbox centre to board
        space so the caller's un-rotation round-trips correctly.
        """
        fp = fp_data._raw
        if fp is None:
            return None
        try:
            xs, ys = self._collect_geometry_points(fp)

            if not xs or not ys:
                return None

            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)

            cx_local = (min_x + max_x) / 2.0
            cy_local = (min_y + max_y) / 2.0

            # Rotate local → board space so the caller can un-rotate it.
            # KiCad CCW in Y-down: R(θ):
            #   x_board =  x_local * cos θ + y_local * sin θ
            #   y_board = -x_local * sin θ + y_local * cos θ
            rot_rad = math.radians(fp_data.rotation)
            cx_board = cx_local * math.cos(rot_rad) + cy_local * math.sin(rot_rad)
            cy_board = -cx_local * math.sin(rot_rad) + cy_local * math.cos(rot_rad)

            return BBoxCenter(cx_mm=cx_board, cy_mm=cy_board)
        except Exception:
            return None

    def get_bounding_box_size(self, fp_data: FootprintData) -> Dict[str, float]:
        """Return {"w": float, "h": float} bounding box in mm from full geometry.

        Falls back to 5×5 if no geometry is available.
        """
        fp = fp_data._raw
        if fp is None:
            return {"w": 5.0, "h": 5.0}
        try:
            xs, ys = self._collect_geometry_points(fp)
            if not xs or not ys:
                return {"w": 5.0, "h": 5.0}
            w = abs(max(xs) - min(xs))
            h = abs(max(ys) - min(ys))
            if w > 0 and h > 0:
                return {"w": w, "h": h}
        except Exception:
            pass
        return {"w": 5.0, "h": 5.0}

    def get_board_path(self) -> str:
        return self._pcb_path

    def get_board_bounding_box(self) -> Optional[Tuple[float, float, float, float]]:
        xs: list = []
        ys: list = []
        for item in getattr(self._board, "graphicItems", []) or []:
            try:
                layer = getattr(item, "layer", "") or ""
                if layer != "Edge.Cuts":
                    continue
                for attr in ("start", "end"):
                    pt = getattr(item, attr, None)
                    if pt is not None:
                        xs.append(float(pt.X))
                        ys.append(float(pt.Y))
                center = getattr(item, "center", None)
                end = getattr(item, "end", None)
                if center is not None and end is not None:
                    r = math.hypot(end.X - center.X, end.Y - center.Y)
                    xs.extend([center.X - r, center.X + r])
                    ys.extend([center.Y - r, center.Y + r])
            except Exception:
                pass
        if not xs or not ys:
            return None
        return (min(xs), max(xs), min(ys), max(ys))

    def get_pad_centroid_offset(self, fp_data: "FootprintData") -> Tuple[float, float]:
        fp = fp_data._raw
        if fp is None:
            return (0.0, 0.0)
        try:
            pads = getattr(fp, "pads", None) or []
            if not pads:
                return (0.0, 0.0)
            cx_local = sum(getattr(p.position, "X", 0.0) for p in pads) / len(pads)
            cy_local = sum(getattr(p.position, "Y", 0.0) for p in pads) / len(pads)
            rot_rad = math.radians(fp_data.rotation)
            cos_r = math.cos(rot_rad)
            sin_r = math.sin(rot_rad)
            dx = cx_local * cos_r + cy_local * sin_r
            dy = -cx_local * sin_r + cy_local * cos_r
            return (dx, dy)
        except Exception:
            return (0.0, 0.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_geometry_points(fp: object) -> tuple:
        """Return (xs, ys) lists of all geometry extremes in local mm coords."""
        xs: list = []
        ys: list = []
        for p in getattr(fp, "pads", []):
            try:
                xs.extend([p.position.X - p.size.X / 2.0, p.position.X + p.size.X / 2.0])
                ys.extend([p.position.Y - p.size.Y / 2.0, p.position.Y + p.size.Y / 2.0])
            except Exception:
                pass
        for item in getattr(fp, "graphicItems", []):
            try:
                for attr in ("start", "end"):
                    pt = getattr(item, attr, None)
                    if pt is not None:
                        xs.append(pt.X)
                        ys.append(pt.Y)
                center = getattr(item, "center", None)
                end = getattr(item, "end", None)
                if center is not None and end is not None:
                    r = math.hypot(end.X - center.X, end.Y - center.Y)
                    xs.extend([center.X - r, center.X + r])
                    ys.extend([center.Y - r, center.Y + r])
            except Exception:
                pass
        return xs, ys

    def _parse_footprint(self, fp: object) -> Optional[FootprintData]:
        ref = self._get_ref(fp)
        if not ref or ref.startswith("~") or ref in ("REF**", ""):
            return None

        value = self._get_value(fp)

        # footprint_id: "LibraryNickname:EntryName"
        try:
            fp_id = "{}:{}".format(fp.libraryNickname, fp.entryName)  # type: ignore[union-attr]
        except Exception:
            fp_id = ""

        # Layer
        layer = "F"
        try:
            if fp.layer == "B.Cu":  # type: ignore[union-attr]
                layer = "B"
        except Exception:
            pass

        # Position in mm (kiutils already in mm)
        pos_x = 0.0
        pos_y = 0.0
        rotation = 0.0
        try:
            pos_x = float(fp.position.X)  # type: ignore[union-attr]
            pos_y = float(fp.position.Y)  # type: ignore[union-attr]
            if fp.position.angle is not None:  # type: ignore[union-attr]
                rotation = float(fp.position.angle) % 360.0  # type: ignore[union-attr]
        except Exception:
            pass

        # Attributes
        dnp = False
        exclude_from_bom = False
        try:
            attrs = fp.attributes  # type: ignore[union-attr]
            exclude_from_bom = bool(attrs.excludeFromBom)
        except Exception:
            pass
        try:
            dnp = bool(fp.attributes.dnp)  # type: ignore[union-attr]
        except Exception:
            pass

        description = self._get_description(fp)

        # Custom fields (lowercase keys, excluding Reference/Value)
        fields: Dict[str, str] = {}
        try:
            for k, v in fp.properties.items():  # type: ignore[union-attr]
                if k.lower() not in ("reference", "value"):
                    fields[k.lower()] = str(v).strip() if v else ""
        except Exception:
            pass

        pad_count = len(getattr(fp, "pads", None) or [])

        return FootprintData(
            ref=ref,
            value=value,
            footprint_id=fp_id,
            layer=layer,
            pos_x=pos_x,
            pos_y=pos_y,
            rotation=rotation,
            dnp=dnp,
            exclude_from_bom=exclude_from_bom,
            description=description,
            fields=fields,
            pad_count=pad_count,
            _raw=fp,
        )

    @staticmethod
    def _get_ref(fp: object) -> str:
        # KiCad 7+: stored in fp.properties dict
        try:
            val = fp.properties.get("Reference", "")  # type: ignore[union-attr]
            if val:
                return val
        except Exception:
            pass
        # Older format: FpText items in graphicItems
        try:
            for item in fp.graphicItems:  # type: ignore[union-attr]
                if getattr(item, "type", None) == "reference":
                    text = getattr(item, "text", "")
                    if text:
                        return text
        except Exception:
            pass
        return ""

    @staticmethod
    def _get_description(fp: object) -> str:
        try:
            val = fp.properties.get("Description", "")  # type: ignore[union-attr]
            if val:
                return val
        except Exception:
            pass
        return ""

    @staticmethod
    def _get_value(fp: object) -> str:
        try:
            val = fp.properties.get("Value", "")  # type: ignore[union-attr]
            if val:
                return val
        except Exception:
            pass
        try:
            for item in fp.graphicItems:  # type: ignore[union-attr]
                if getattr(item, "type", None) == "value":
                    return getattr(item, "text", "")
        except Exception:
            pass
        return ""


# ---------------------------------------------------------------------------
# kiutils compatibility shims
# ---------------------------------------------------------------------------

_kiutils_patched = False


def _patch_kiutils_kicad10_compat() -> None:
    """Patch kiutils to tolerate KiCad 10 format variations.

    kiutils 1.4.8 assumes pad net entries always have the form ``(net N name)``
    (three elements), but KiCad 10 (file version 20260206) emits ``(net N)``
    without a name when the net name is implicit.  This one-time monkey-patch
    makes ``Net.from_sexpr`` default the name to ``""`` when exp[2] is absent.
    """
    global _kiutils_patched
    if _kiutils_patched:
        return
    try:
        from kiutils.items import common as _common

        @classmethod  # type: ignore[misc]
        def _patched_from_sexpr(cls, exp):  # type: ignore[misc]
            obj = cls()
            obj.number = exp[1]
            obj.name = exp[2] if len(exp) > 2 else ""
            return obj

        _common.Net.from_sexpr = _patched_from_sexpr  # type: ignore[method-assign]
        _kiutils_patched = True
    except Exception:
        pass
