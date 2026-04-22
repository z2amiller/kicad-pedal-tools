"""CLI entry point for build_doc (build-doc-plugin).

Usage:
    python -m build_doc --board foo.kicad_pcb --out foo-build-doc.pdf

Generates a PDF build document from a .kicad_pcb file without a live KiCad session.
Requires kiutils (pip install kiutils) for headless board parsing.
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="build_doc",
        description="Generate a PDF build document from a KiCad board file.",
    )
    parser.add_argument(
        "--board", required=True, metavar="PATH", help="Path to the .kicad_pcb file"
    )
    parser.add_argument(
        "--out", required=True, metavar="PATH", help="Output path for the PDF"
    )
    parser.add_argument(
        "--name", default=None, metavar="NAME",
        help="Project name (defaults to board file stem)",
    )
    parser.add_argument(
        "--author", default="", metavar="AUTHOR", help="Author name for the build doc"
    )
    parser.add_argument(
        "--revision", default="1.0", metavar="REV", help="Revision string (default: 1.0)"
    )
    parser.add_argument(
        "--blurb", default="", metavar="TEXT",
        help="Optional description text for the cover page",
    )
    parser.add_argument(
        "--sch", default="", metavar="PATH",
        help="Path to root .kicad_sch (auto-detected if omitted)",
    )
    parser.add_argument(
        "--kicad-cli", default=None, metavar="PATH",
        help="Explicit path to kicad-cli (auto-detected if omitted)",
    )
    parser.add_argument("--no-cover", action="store_true", help="Omit cover page")
    parser.add_argument("--no-bom", action="store_true", help="Omit BOM page")
    parser.add_argument(
        "--no-enclosure", action="store_true", help="Omit enclosure drilling template"
    )
    parser.add_argument(
        "--sch-include", action="store_true",
        help="Include schematic pages (off by default in CLI mode)",
    )
    args = parser.parse_args(argv)

    board_path = os.path.abspath(args.board)
    if not os.path.exists(board_path):
        print(f"ERROR: Board file not found: {board_path}", file=sys.stderr)
        sys.exit(1)

    project_name = args.name or os.path.splitext(os.path.basename(board_path))[0]

    def _log(msg: str) -> None:
        print(msg, file=sys.stderr)

    try:
        from kicad_pedal_common.kiutils_board_adapter import KiutilsBoardAdapter

        adapter = KiutilsBoardAdapter(board_path)
        _log("Using kiutils adapter for headless board parsing.")
    except ImportError:
        print(
            "ERROR: kiutils is required for CLI mode (pip install kiutils)",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Failed to parse board: {exc}", file=sys.stderr)
        sys.exit(1)

    # Override kicad-cli if specified
    if args.kicad_cli:
        import cli_utils

        cli_utils.set_kicad_cli_path(args.kicad_cli)

    # Add the plugin dir to sys.path so local imports work
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    from build_doc_generator import BuildDocGenerator, GeneratorParams

    params = GeneratorParams(
        project_name=project_name,
        output_path=args.out,
        author=args.author,
        revision=args.revision,
        blurb=args.blurb,
        sch_path=args.sch,
        include_cover=not args.no_cover,
        include_bom=not args.no_bom,
        include_enclosure=not args.no_enclosure,
        include_sch=args.sch_include,
        include_tayda=False,
    )

    try:
        gen = BuildDocGenerator(adapter, params, log=_log)
        gen.generate()
        print(args.out)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
