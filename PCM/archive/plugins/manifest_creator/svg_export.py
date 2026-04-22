"""Export per-layer SVGs from a KiCad board file using kicad-cli."""

from __future__ import annotations

import pathlib
from typing import Dict, List, Optional

from kicad_pedal_common.plotting import (
    LAYER_MAP,
    export_drill_map_svg,
    export_layer_svg,
    find_kicad_cli,
)

# Default set of layers to export (drills handled separately via export_drill_map_svg)
DEFAULT_LAYERS: List[str] = ["f_mask", "f_paste", "edge_cuts", "f_silks"]


def export_all_layers(
    board_path: str,
    output_dir: str,
    kicad_cli: Optional[str] = None,
    layers: Optional[List[str]] = None,
    log=None,
) -> Dict[str, str]:
    """Export all front layers as SVGs into output_dir.

    Returns a dict of logical_name -> relative_path
    (e.g. {"edge_cuts": "svg/edge_cuts.svg"}).

    If kicad_cli is None, calls find_kicad_cli() to locate it.
    Raises RuntimeError if kicad-cli is not found.

    layers: list of logical layer names to export (default: all front layers).
    """
    cli = kicad_cli
    if cli is None:
        cli = find_kicad_cli()
    if cli is None:
        raise RuntimeError("kicad-cli not found. Install KiCad or add kicad-cli to PATH.")

    layer_names = layers if layers is not None else DEFAULT_LAYERS

    svg_dir = pathlib.Path(output_dir) / "svg"
    svg_dir.mkdir(parents=True, exist_ok=True)

    result: Dict[str, str] = {}
    for logical_name in layer_names:
        kicad_layer = LAYER_MAP[logical_name]
        filename = "{}.svg".format(logical_name)
        output_path = str(svg_dir / filename)
        export_layer_svg(board_path, kicad_layer, output_path, kicad_cli=cli)
        result[logical_name] = "svg/{}".format(filename)

    # Export drill maps (PTH / NPTH) via pcb export drill --map-format svg
    try:
        drill_dir = str(svg_dir / "drills")
        drill_svgs = export_drill_map_svg(board_path, drill_dir, kicad_cli=cli)
        for logical_name, abs_path in drill_svgs.items():
            rel = "svg/drills/{}".format(pathlib.Path(abs_path).name)
            result[logical_name] = rel
    except RuntimeError:
        pass  # drill export is best-effort

    return result
