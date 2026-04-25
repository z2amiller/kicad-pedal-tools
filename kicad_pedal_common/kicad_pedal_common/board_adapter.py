"""BoardAdapter protocol and KipyBoardAdapter implementation.

Provides a kipy-independent interface for reading board data so callers
don't depend on kipy directly, enabling future headless/kiutils adapters.

Python 3.9 compatible — no match/case, no |union syntax, no walrus in
type annotations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from kicad_pedal_common.drill import DrillHole

NM_PER_MM = 1_000_000  # kipy uses nanometres


# ---------------------------------------------------------------------------
# Data containers (plain Python — no kipy dependency)
# ---------------------------------------------------------------------------


@dataclass
class FootprintData:
    """Plain-Python representation of a single footprint.

    All callers should treat ``_raw`` as opaque — it holds the underlying
    kipy / kiutils footprint object and is used internally by the adapter.
    """

    ref: str
    value: str
    footprint_id: str       # "LibName:FpName"
    layer: str              # "F" or "B"
    pos_x: float            # mm
    pos_y: float            # mm
    rotation: float         # degrees 0-360 CCW
    dnp: bool
    exclude_from_bom: bool
    description: str = ""   # human-readable component description (optional)
    fields: Dict[str, str] = field(default_factory=dict)  # custom KiCad fields, lowercase keys
    pad_count: int = 0
    # Opaque reference to the underlying fp object; not shown in repr.
    _raw: object = field(default=None, repr=False, compare=False)


@dataclass
class BBoxCenter:
    """Bounding-box centre in mm."""

    cx_mm: float
    cy_mm: float


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class BoardAdapter:
    """Protocol describing the minimal board interface needed by manifest-creator.

    Implementations wrap a concrete board object (kipy, kiutils, …) and
    expose only the data needed by the plugin so that the plugin code
    stays free of any direct kipy dependency.

    This is written as a regular base class with NotImplementedError rather
    than typing.Protocol so it is usable without importing the typing extras
    module at runtime, and remains compatible with Python 3.9.
    """

    def get_footprints(self) -> List[FootprintData]:
        """Return all footprints on the board as a list of :class:`FootprintData`."""
        raise NotImplementedError

    def get_item_bounding_box(
        self, fp_data: FootprintData
    ) -> Optional[BBoxCenter]:
        """Return the bounding-box centre for *fp_data*, or None if unavailable."""
        raise NotImplementedError

    def get_drill_holes(self) -> List[DrillHole]:
        """Return all THT/NPTH drill holes on the board in board-space mm."""
        return []

    def get_board_path(self) -> str:
        """Return absolute path to the .kicad_pcb file."""
        return ""

    def get_board_bounding_box(self) -> Optional[Tuple[float, float, float, float]]:
        """Return (min_x_mm, max_x_mm, min_y_mm, max_y_mm) of Edge.Cuts outline, or None."""
        return None

    def get_pad_centroid_offset(self, fp_data: "FootprintData") -> Tuple[float, float]:
        """Return (dx_mm, dy_mm) pad centroid offset from fp position in board frame."""
        return (0.0, 0.0)


# ---------------------------------------------------------------------------
# KipyBoardAdapter
# ---------------------------------------------------------------------------


class KipyBoardAdapter(BoardAdapter):
    """BoardAdapter implementation that wraps a live kipy board object."""

    def __init__(self, board: object) -> None:
        self._board = board

    # ------------------------------------------------------------------
    # BoardAdapter interface
    # ------------------------------------------------------------------

    def get_footprints(self) -> List[FootprintData]:
        """Return all footprints from the kipy board as :class:`FootprintData`.

        Footprints with empty or placeholder refs (REF**, ~*) are skipped.
        All error-handling mirrors the original ``get_footprints(board)``
        implementation in ``footprint.py``.
        """
        result: List[FootprintData] = []
        try:
            footprints = list(self._board.get_footprints())
        except Exception:
            return result

        for fp in footprints:
            fp_data = self._parse_footprint(fp)
            if fp_data is not None:
                result.append(fp_data)

        return result

    def get_item_bounding_box(
        self, fp_data: FootprintData
    ) -> Optional[BBoxCenter]:
        """Return the bounding-box centre in mm, or None if unavailable."""
        if fp_data._raw is None:
            return None
        try:
            bb = self._board.get_item_bounding_box(fp_data._raw)
            if bb is None:
                return None
            center = bb.center()
            fp_raw = fp_data._raw
            fp_x = fp_raw.position.x
            fp_y = fp_raw.position.y

            dx_nm = center.x - fp_x
            dy_nm = center.y - fp_y

            cx_mm = dx_nm / NM_PER_MM
            cy_mm = dy_nm / NM_PER_MM
            return BBoxCenter(cx_mm=cx_mm, cy_mm=cy_mm)
        except Exception:
            return None

    def get_board_path(self) -> str:
        import os
        board = self._board
        try:
            name = board.name
        except Exception:
            return ""
        if name and os.path.isabs(name) and os.path.exists(name):
            return name
        try:
            project_dir = board.get_project().path
            if project_dir:
                candidate = os.path.join(project_dir, os.path.basename(name))
                if os.path.exists(candidate):
                    return candidate
        except Exception:
            pass
        return name or ""

    def get_board_bounding_box(self) -> Optional[Tuple[float, float, float, float]]:
        try:
            from kipy.board import BoardLayer  # type: ignore[import]
            shapes = [
                s for s in self._board.get_shapes()
                if s.layer == BoardLayer.BL_Edge_Cuts
            ]
            if not shapes:
                return None
            bboxes = self._board.get_item_bounding_box(shapes)
            if not bboxes:
                return None
            result = bboxes[0]
            for b in bboxes[1:]:
                result.merge(b)
            center = result.center()
            size = result.size
            cx = center.x / NM_PER_MM
            cy = center.y / NM_PER_MM
            hw = size.x / NM_PER_MM / 2.0
            hh = size.y / NM_PER_MM / 2.0
            return (cx - hw, cx + hw, cy - hh, cy + hh)
        except Exception:
            return None

    def get_pad_centroid_offset(self, fp_data: "FootprintData") -> Tuple[float, float]:
        fp = fp_data._raw
        if fp is None:
            return (0.0, 0.0)
        try:
            pads = list(fp.definition.pads)
            if not pads:
                return (0.0, 0.0)
            cx = sum(p.position.x for p in pads) / len(pads) - fp.position.x
            cy = sum(p.position.y for p in pads) / len(pads) - fp.position.y
            return (cx / NM_PER_MM, cy / NM_PER_MM)
        except Exception:
            return (0.0, 0.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_footprint(self, fp: object) -> Optional[FootprintData]:
        """Convert a single kipy footprint object to :class:`FootprintData`.

        Returns None if the footprint should be skipped (empty/placeholder ref,
        or unrecoverable parse error).
        """
        try:
            ref = fp.reference_field.text.value  # type: ignore[union-attr]
        except Exception:
            return None

        if not ref or ref.startswith("~") or ref in ("REF**", ""):
            return None

        try:
            value = fp.value_field.text.value  # type: ignore[union-attr]
        except Exception:
            value = ""

        try:
            fp_id = "{}:{}".format(
                fp.definition.id.library,  # type: ignore[union-attr]
                fp.definition.id.name,     # type: ignore[union-attr]
            )
        except Exception:
            fp_id = ""

        layer = _detect_layer(fp)

        # Position in mm
        try:
            pos_x = fp.position.x / NM_PER_MM  # type: ignore[union-attr]
            pos_y = fp.position.y / NM_PER_MM  # type: ignore[union-attr]
        except Exception:
            pos_x = 0.0
            pos_y = 0.0

        # Rotation: convert from radians, normalize 0-360
        rotation = 0.0
        try:
            rad = fp.orientation.to_radians()  # type: ignore[union-attr]
            rotation = math.degrees(rad) % 360.0
        except Exception:
            rotation = 0.0

        # Attribute flags
        dnp = False
        exclude_from_bom = False
        try:
            attrs = fp.attributes  # type: ignore[union-attr]
            dnp = bool(attrs.do_not_populate)
            exclude_from_bom = bool(attrs.exclude_from_bill_of_materials)
        except Exception:
            pass

        # Description field — stored in fp.fields alongside Ref/Value
        description = ""
        try:
            for field in fp.fields:  # type: ignore[union-attr]
                try:
                    if field.name.lower() == "description":
                        description = field.text.value or ""
                        break
                except Exception:
                    pass
        except Exception:
            pass

        # Custom fields (lowercase keys)
        fields: Dict[str, str] = {}
        try:
            for item in fp.texts_and_fields:  # type: ignore[union-attr]
                item_name = getattr(item, "name", None)
                if item_name:
                    text_val = ""
                    try:
                        text_val = str(
                            getattr(getattr(item, "text", None), "value", "")
                        ).strip()
                    except Exception:
                        pass
                    fields[item_name.lower()] = text_val
        except Exception:
            pass

        # Pad count — use fp.definition.pads (the footprint template's pad list),
        # not fp.pads (instance-level overrides that are often empty in kipy).
        pad_count = 0
        try:
            pad_count = len(list(fp.definition.pads))  # type: ignore[union-attr]
        except Exception:
            pass

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


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------


def _detect_layer(fp: object) -> str:
    """Return "F" or "B" for a kipy footprint object.

    Mirrors the layer-detection logic in ``footprint.py`` exactly, including
    the numeric-31 fallback needed when kipy is mocked in tests.
    """
    try:
        layer_raw = fp.layer  # type: ignore[union-attr]
        layer_int = layer_raw.value if hasattr(layer_raw, "value") else layer_raw
        if layer_int == 31:
            return "B"
        # Enum check: only compare against real BoardLayer enum (not MagicMock).
        try:
            import inspect

            from kipy.board import BoardLayer  # type: ignore[import]

            if inspect.isclass(BoardLayer) and layer_raw == BoardLayer.BL_B_Cu:
                return "B"
        except Exception:
            pass
    except Exception:
        pass
    return "F"
