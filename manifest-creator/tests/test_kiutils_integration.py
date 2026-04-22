"""Integration test: full standalone manifest export using KiutilsBoardAdapter.

Skipped automatically when the fx-SixSeven board file is not present.
Run from the manifest-creator directory:

    python -m pytest tests/test_kiutils_integration.py -v
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

BOARD_PATH = "/Users/andrewmiller/Documents/repos/fx-SixSeven/fx-SixSeven.kicad_pcb"

pytestmark = pytest.mark.skipif(
    not os.path.exists(BOARD_PATH),
    reason="fx-SixSeven board not present on this machine",
)


@pytest.fixture(scope="module")
def adapter():
    from kicad_pedal_common.kiutils_board_adapter import KiutilsBoardAdapter
    return KiutilsBoardAdapter(BOARD_PATH)


@pytest.fixture(scope="module")
def manifest_zip(tmp_path_factory):
    """Run the full CLI export once per session and return the ZIP path."""
    out = str(tmp_path_factory.mktemp("manifest") / "test.manifest.zip")
    from manifest_creator.packager import create_manifest_zip
    from kicad_pedal_common.kiutils_board_adapter import KiutilsBoardAdapter

    a = KiutilsBoardAdapter(BOARD_PATH)
    create_manifest_zip(
        board=None,
        board_path=BOARD_PATH,
        output_path=out,
        version="1.0.0-test",
        adapter=a,
    )
    return out


class TestKiutilsBoardAdapter:
    def test_loads_board(self, adapter):
        fps = adapter.get_footprints()
        assert len(fps) > 0

    def test_footprint_count(self, adapter):
        fps = adapter.get_footprints()
        assert len(fps) == 95

    def test_known_refs_present(self, adapter):
        refs = {fp.ref for fp in adapter.get_footprints()}
        for ref in ("R34", "C23", "R10"):
            assert ref in refs

    def test_footprint_positions_non_zero(self, adapter):
        fps = adapter.get_footprints()
        positions = [(fp.pos_x, fp.pos_y) for fp in fps]
        assert any(x != 0.0 or y != 0.0 for x, y in positions)

    def test_footprint_ids_have_colon(self, adapter):
        fps = adapter.get_footprints()
        for fp in fps:
            assert ":" in fp.footprint_id, f"{fp.ref} has bad footprint_id: {fp.footprint_id}"

    def test_installed_components(self, adapter):
        fps = adapter.get_footprints()
        installed = [fp for fp in fps if fp.exclude_from_bom]
        assert len(installed) == 11

    def test_bbox_center_offset(self, adapter):
        fps = adapter.get_footprints()
        results = [adapter.get_item_bounding_box(fp) for fp in fps[:5]]
        assert any(r is not None for r in results)


class TestManifestExport:
    def test_zip_produced(self, manifest_zip):
        assert os.path.exists(manifest_zip)
        assert os.path.getsize(manifest_zip) > 0

    def test_manifest_json_valid(self, manifest_zip):
        with zipfile.ZipFile(manifest_zip) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["schema_version"] == "1.0"
        assert manifest["board_name"] == "fx-sixseven"

    def test_component_count(self, manifest_zip):
        with zipfile.ZipFile(manifest_zip) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert len(manifest["components"]) == 94

    def test_installed_components_in_manifest(self, manifest_zip):
        with zipfile.ZipFile(manifest_zip) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        installed = [c for c in manifest["components"] if c.get("installed")]
        assert len(installed) == 10

    def test_layers_present(self, manifest_zip):
        with zipfile.ZipFile(manifest_zip) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        layers = manifest["layers"]
        assert "edge_cuts" in layers
        assert "f_silks" in layers
