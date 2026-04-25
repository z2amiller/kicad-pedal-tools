"""Drill hole data structures and extraction utilities.

Shared between manifest-creator (for bundling drill data in the manifest zip)
and kicad-build-doc-plugin (for Tayda drill templates and enclosure layout).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List


@dataclass
class DrillHole:
    """A single drill hole in board-coordinate space (mm from board origin).

    For through-hole (PTH) and non-plated (NPTH) pads.  Oval/slot drills
    are represented by their longest axis diameter; ``oval`` is set True.
    """

    x_mm: float
    y_mm: float
    diameter_mm: float
    label: str = ""          # typically the footprint reference
    plated: bool = True      # False = NPTH (mounting holes, slots)
    oval: bool = False       # True = slot drill; diameter_mm is the long axis


def get_drill_holes_kiutils(board: object) -> List[DrillHole]:
    """Extract all THT and NPTH drill holes from a kiutils ``Board`` object.

    Transforms each pad's local position into board space using the
    footprint's position and rotation.  SMD pads are skipped.

    Compatible with KiCad 7–10 via the ``_patch_kiutils_kicad10_compat``
    workaround already applied by ``KiutilsBoardAdapter.__init__``.

    Parameters
    ----------
    board:
        A ``kiutils.board.Board`` instance (already loaded).

    Returns
    -------
    List[DrillHole]
        One entry per THT/NPTH pad, in board-coordinate mm.
    """
    holes: List[DrillHole] = []

    for fp in getattr(board, "footprints", []):
        try:
            fp_x = float(fp.position.X)
            fp_y = float(fp.position.Y)
            angle_deg = float(getattr(fp.position, "angle", 0) or 0)
            angle_rad = math.radians(angle_deg)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            ref = str(getattr(fp, "entryName", "") or "")
        except Exception:
            continue

        for p in getattr(fp, "pads", []):
            try:
                pad_type = getattr(p, "type", "")
                if pad_type not in ("thru_hole", "np_thru_hole"):
                    continue
                drill = getattr(p, "drill", None)
                if drill is None:
                    continue
                diameter = float(getattr(drill, "diameter", 0) or 0)
                if diameter <= 0:
                    continue

                is_oval = bool(getattr(drill, "oval", False))
                plated = pad_type == "thru_hole"

                # Rotate local pad position into board space.
                # KiCad rotation is clockwise (positive angle = CW).
                lx = float(p.position.X)
                ly = float(p.position.Y)
                bx = fp_x + lx * cos_a - ly * sin_a
                by = fp_y + lx * sin_a + ly * cos_a

                holes.append(DrillHole(
                    x_mm=round(bx, 4),
                    y_mm=round(by, 4),
                    diameter_mm=round(diameter, 4),
                    label=ref,
                    plated=plated,
                    oval=is_oval,
                ))
            except Exception:
                continue

    return holes
