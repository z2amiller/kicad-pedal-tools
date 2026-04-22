"""CLI entry point for manifest_creator.

Usage:
    python -m manifest_creator --board foo.kicad_pcb --out foo.manifest.zip --version 1.0.0

Note: CLI mode produces a manifest with SVG layers only (no BOM/components).
BOM and footprint geometry require a live kipy board object and are only
available when manifest_creator is invoked from within KiCad via the IPC plugin.
"""

from __future__ import annotations

import argparse
import sys

from manifest_creator.packager import create_manifest_zip


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="manifest_creator",
        description=(
            "Export a KiCad board as a .manifest.zip (SVG layers only). "
            "For full BOM export, use the KiCad IPC plugin."
        ),
    )
    parser.add_argument(
        "--board",
        required=True,
        metavar="PATH",
        help="Path to the .kicad_pcb file",
    )
    parser.add_argument(
        "--out",
        required=True,
        metavar="PATH",
        help="Output path for the .manifest.zip file",
    )
    parser.add_argument(
        "--version",
        required=True,
        metavar="VERSION",
        help="Board version string, e.g. 1.0.0",
    )
    parser.add_argument(
        "--display-name",
        default=None,
        metavar="NAME",
        help="Human-readable board name (defaults to board file stem)",
    )
    parser.add_argument(
        "--kicad-cli",
        default=None,
        metavar="PATH",
        help="Explicit path to kicad-cli (auto-detected if omitted)",
    )
    args = parser.parse_args(argv)

    def _log(msg: str) -> None:
        print(msg, file=sys.stderr)

    try:
        out = create_manifest_zip(
            board=None,
            board_path=args.board,
            output_path=args.out,
            version=args.version,
            display_name=args.display_name,
            kicad_cli=args.kicad_cli,
            log=_log,
        )
        print(out)
    except Exception as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
