"""Tests for manifest_creator.packager."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import zipfile
from typing import Dict
from unittest.mock import MagicMock, patch

import jsonschema
import pytest

from manifest_creator.packager import _validate_manifest, create_manifest_zip

# ---------------------------------------------------------------------------
# Paths to shared fixtures
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).parent.parent
_SCHEMA_DIR = _REPO_ROOT / "kicad_pedal_common" / "schema"
_FUZZ_FACE_ZIP = (
    pathlib.Path(__file__).parent.parent.parent / "pedal-build" / "spec" / "fuzz-face.manifest.zip"
)
_FUZZ_FACE_MANIFEST = (
    pathlib.Path(__file__).parent.parent.parent
    / "pedal-build"
    / "spec"
    / "examples"
    / "fuzz-face"
    / "manifest.json"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NM_PER_MM = 1_000_000


def _make_fp(
    ref,
    value,
    layer_int=0,
    pos_x_nm=10_000_000,
    pos_y_nm=20_000_000,
    rotation_rad=0.0,
    dnp=False,
    exclude_from_bom=False,
    bbox_w_nm=3_000_000,
    bbox_h_nm=2_000_000,
):
    fp = MagicMock()
    fp.reference_field.text.value = ref
    fp.value_field.text.value = value
    fp.definition.id.library = "Resistor_THT"
    fp.definition.id.name = "R_Axial"
    fp.layer = layer_int
    fp.position.x = pos_x_nm
    fp.position.y = pos_y_nm
    fp.orientation.to_radians.return_value = rotation_rad
    fp.attributes.do_not_populate = dnp
    fp.attributes.exclude_from_bill_of_materials = exclude_from_bom
    bb = MagicMock()
    bb.width = bbox_w_nm
    bb.height = bbox_h_nm
    fp.bounding_box = bb
    return fp


def _make_board(footprints=None):
    board = MagicMock()
    board.get_footprints.return_value = footprints or []
    # Board bounding box in mm (small values → packager treats them as mm)
    bb = MagicMock()
    bb.left = 0.0
    bb.top = 0.0
    bb.right = 60.96
    bb.bottom = 76.2
    board.bounding_box = bb
    return board


def _make_layers_map() -> Dict[str, str]:
    return {
        "f_mask": "svg/f_mask.svg",
        "f_paste": "svg/f_paste.svg",
        "edge_cuts": "svg/edge_cuts.svg",
        "f_silks": "svg/f_silks.svg",
        "pth_drills": "svg/pth_drills.svg",
    }


def _stub_export_all_layers(tmp_dir: str, layers_map: Dict[str, str]) -> None:
    """Write stub SVG files into tmp_dir so the zip writer can find them."""
    svg_dir = pathlib.Path(tmp_dir) / "svg"
    svg_dir.mkdir(parents=True, exist_ok=True)
    for zip_path in layers_map.values():
        (pathlib.Path(tmp_dir) / zip_path).write_text("<svg/>")


# ---------------------------------------------------------------------------
# _validate_manifest
# ---------------------------------------------------------------------------


class TestValidateManifest:
    def _minimal_manifest(self) -> Dict:
        return {
            "schema_version": "1.0",
            "board_name": "test-board",
            "version": "1.0.0",
            "created_at": "2026-01-01T00:00:00Z",
            "board_bounds": {"x": 0.0, "y": 0.0, "width": 60.96, "height": 76.2},
            "layers": {
                "f_mask": "svg/f_mask.svg",
                "f_paste": "svg/f_paste.svg",
                "edge_cuts": "svg/edge_cuts.svg",
                "f_silks": "svg/f_silks.svg",
            },
            "components": [],
        }

    def test_valid_minimal_manifest_passes(self):
        _validate_manifest(self._minimal_manifest())

    def test_valid_manifest_with_components_passes(self):
        m = self._minimal_manifest()
        m["components"] = [
            {
                "ref": "R1",
                "value": "10K",
                "footprint": "Resistor_THT:R_Axial",
                "description": "Resistor",
                "notes": "",
                "layer": "F",
                "pos_x": 10.0,
                "pos_y": 20.0,
                "rotation": 0.0,
                "do_not_populate": False,
                "exclude_from_bom": False,
                "outline": {"type": "bbox", "bbox": {"w": 3.0, "h": 2.0}},
            }
        ]
        _validate_manifest(m)

    def test_missing_required_field_raises(self):
        m = self._minimal_manifest()
        del m["board_name"]
        with pytest.raises(jsonschema.ValidationError):
            _validate_manifest(m)

    def test_invalid_schema_version_raises(self):
        m = self._minimal_manifest()
        m["schema_version"] = "2.0"
        with pytest.raises(jsonschema.ValidationError):
            _validate_manifest(m)

    def test_board_name_pattern_enforced(self):
        m = self._minimal_manifest()
        m["board_name"] = "INVALID BOARD"
        with pytest.raises(jsonschema.ValidationError):
            _validate_manifest(m)

    def test_rotation_out_of_range_raises(self):
        m = self._minimal_manifest()
        m["components"] = [
            {
                "ref": "R1",
                "value": "10K",
                "footprint": "Resistor_THT:R_Axial",
                "layer": "F",
                "pos_x": 10.0,
                "pos_y": 20.0,
                "rotation": 360.0,  # exclusiveMaximum = 360 → invalid
                "outline": {"type": "bbox", "bbox": {"w": 3.0, "h": 2.0}},
            }
        ]
        with pytest.raises(jsonschema.ValidationError):
            _validate_manifest(m)


# ---------------------------------------------------------------------------
# create_manifest_zip — unit tests (all I/O mocked)
# ---------------------------------------------------------------------------


class TestCreateManifestZip:
    def _run(self, tmp_path, board=None, footprints=None, extra_kwargs=None):
        """Run create_manifest_zip with export functions mocked."""
        layers_map = _make_layers_map()
        if board is None:
            board = _make_board(footprints or [_make_fp("R1", "10K")])

        output_path = str(tmp_path / "board.manifest.zip")

        def fake_export_all_layers(board_path, output_dir, kicad_cli=None, log=None):
            _stub_export_all_layers(output_dir, layers_map)
            return layers_map

        kwargs = dict(
            board=board,
            board_path="/fake/test-board.kicad_pcb",
            output_path=output_path,
            version="1.0.0",
        )
        if extra_kwargs:
            kwargs.update(extra_kwargs)

        with (
            patch(
                "manifest_creator.packager.export_all_layers",
                side_effect=fake_export_all_layers,
            ),
            patch(
                "manifest_creator.packager.export_bom",
                return_value=[
                    {
                        "ref": "R1",
                        "value": "10K",
                        "footprint": "Resistor_THT:R_Axial",
                        "description": "Resistor",
                        "notes": "",
                        "layer": "F",
                        "pos_x": 10.0,
                        "pos_y": 20.0,
                        "rotation": 0.0,
                        "do_not_populate": False,
                        "exclude_from_bom": False,
                        "outline": {"type": "bbox", "bbox": {"w": 3.0, "h": 2.0}},
                    }
                ],
            ),
        ):
            result = create_manifest_zip(**kwargs)

        return result, output_path

    def test_returns_output_path(self, tmp_path):
        result, output_path = self._run(tmp_path)
        assert result == output_path

    def test_output_file_is_created(self, tmp_path):
        _, output_path = self._run(tmp_path)
        assert pathlib.Path(output_path).exists()

    def test_zip_contains_manifest_json(self, tmp_path):
        _, output_path = self._run(tmp_path)
        with zipfile.ZipFile(output_path) as zf:
            assert "manifest.json" in zf.namelist()

    def test_zip_contains_all_svg_entries(self, tmp_path):
        _, output_path = self._run(tmp_path)
        layers_map = _make_layers_map()
        with zipfile.ZipFile(output_path) as zf:
            names = set(zf.namelist())
        for zip_path in layers_map.values():
            assert zip_path in names, "Missing {} in zip".format(zip_path)

    def test_manifest_json_is_valid_json(self, tmp_path):
        _, output_path = self._run(tmp_path)
        with zipfile.ZipFile(output_path) as zf:
            data = json.loads(zf.read("manifest.json"))
        assert isinstance(data, dict)

    def test_manifest_json_validates_against_schema(self, tmp_path):
        _, output_path = self._run(tmp_path)
        with zipfile.ZipFile(output_path) as zf:
            data = json.loads(zf.read("manifest.json"))
        _validate_manifest(data)  # raises if invalid

    def test_board_name_derived_from_board_path(self, tmp_path):
        _, output_path = self._run(tmp_path)
        with zipfile.ZipFile(output_path) as zf:
            data = json.loads(zf.read("manifest.json"))
        assert data["board_name"] == "test-board"

    def test_display_name_defaults_to_board_stem(self, tmp_path):
        _, output_path = self._run(tmp_path)
        with zipfile.ZipFile(output_path) as zf:
            data = json.loads(zf.read("manifest.json"))
        assert data["display_name"] == "test-board"

    def test_display_name_override(self, tmp_path):
        _, output_path = self._run(tmp_path, extra_kwargs={"display_name": "My Pedal"})
        with zipfile.ZipFile(output_path) as zf:
            data = json.loads(zf.read("manifest.json"))
        assert data["display_name"] == "My Pedal"

    def test_version_stored_in_manifest(self, tmp_path):
        _, output_path = self._run(tmp_path, extra_kwargs={"version": "2.3.1"})
        with zipfile.ZipFile(output_path) as zf:
            data = json.loads(zf.read("manifest.json"))
        assert data["version"] == "2.3.1"

    def test_board_none_produces_empty_components(self, tmp_path):
        """CLI mode: board=None → components list is empty."""
        layers_map = _make_layers_map()
        output_path = str(tmp_path / "cli.manifest.zip")

        def fake_export_all_layers(board_path, output_dir, kicad_cli=None, log=None):
            _stub_export_all_layers(output_dir, layers_map)
            return layers_map

        with patch(
            "manifest_creator.packager.export_all_layers",
            side_effect=fake_export_all_layers,
        ):
            create_manifest_zip(
                board=None,
                board_path="/fake/test-board.kicad_pcb",
                output_path=output_path,
                version="1.0.0",
            )

        with zipfile.ZipFile(output_path) as zf:
            data = json.loads(zf.read("manifest.json"))
        assert data["components"] == []

    def test_log_callback_is_called(self, tmp_path):
        log_messages = []
        layers_map = _make_layers_map()
        output_path = str(tmp_path / "logged.manifest.zip")

        def fake_export_all_layers(board_path, output_dir, kicad_cli=None, log=None):
            _stub_export_all_layers(output_dir, layers_map)
            return layers_map

        with (
            patch(
                "manifest_creator.packager.export_all_layers",
                side_effect=fake_export_all_layers,
            ),
            patch(
                "manifest_creator.packager.export_bom",
                return_value=[],
            ),
        ):
            create_manifest_zip(
                board=_make_board(),
                board_path="/fake/test-board.kicad_pcb",
                output_path=output_path,
                version="1.0.0",
                log=log_messages.append,
            )

        assert len(log_messages) > 0

    def test_export_all_layers_called_once(self, tmp_path):
        layers_map = _make_layers_map()
        output_path = str(tmp_path / "board.manifest.zip")

        def fake_export_all_layers(board_path, output_dir, kicad_cli=None, log=None):
            _stub_export_all_layers(output_dir, layers_map)
            return layers_map

        with (
            patch(
                "manifest_creator.packager.export_all_layers",
                side_effect=fake_export_all_layers,
            ) as mock_layers,
            patch(
                "manifest_creator.packager.export_bom",
                return_value=[],
            ),
        ):
            create_manifest_zip(
                board=_make_board(),
                board_path="/fake/test-board.kicad_pcb",
                output_path=output_path,
                version="1.0.0",
            )

        mock_layers.assert_called_once()

    def test_export_bom_called_once_with_board(self, tmp_path):
        layers_map = _make_layers_map()
        output_path = str(tmp_path / "board.manifest.zip")
        board = _make_board()

        def fake_export_all_layers(board_path, output_dir, kicad_cli=None, log=None):
            _stub_export_all_layers(output_dir, layers_map)
            return layers_map

        with (
            patch(
                "manifest_creator.packager.export_all_layers",
                side_effect=fake_export_all_layers,
            ),
            patch(
                "manifest_creator.packager.export_bom",
                return_value=[],
            ) as mock_bom,
        ):
            create_manifest_zip(
                board=board,
                board_path="/fake/test-board.kicad_pcb",
                output_path=output_path,
                version="1.0.0",
            )

        mock_bom.assert_called_once_with(board)

    def test_export_bom_not_called_when_board_none(self, tmp_path):
        layers_map = _make_layers_map()
        output_path = str(tmp_path / "cli.manifest.zip")

        def fake_export_all_layers(board_path, output_dir, kicad_cli=None, log=None):
            _stub_export_all_layers(output_dir, layers_map)
            return layers_map

        with (
            patch(
                "manifest_creator.packager.export_all_layers",
                side_effect=fake_export_all_layers,
            ),
            patch(
                "manifest_creator.packager.export_bom",
            ) as mock_bom,
        ):
            create_manifest_zip(
                board=None,
                board_path="/fake/test-board.kicad_pcb",
                output_path=output_path,
                version="1.0.0",
            )

        mock_bom.assert_not_called()


# ---------------------------------------------------------------------------
# Fixture round-trip: fuzz-face.manifest.zip
# ---------------------------------------------------------------------------


class TestFuzzFaceZipFixture:
    """Validate the hand-built fuzz-face.manifest.zip against the schema."""

    @pytest.fixture(autouse=True)
    def skip_if_missing(self):
        if not _FUZZ_FACE_ZIP.exists():
            pytest.skip("fuzz-face.manifest.zip fixture not found at {}".format(_FUZZ_FACE_ZIP))

    def test_zip_contains_manifest_json(self):
        with zipfile.ZipFile(_FUZZ_FACE_ZIP) as zf:
            assert "manifest.json" in zf.namelist()

    def test_zip_contains_expected_svg_entries(self):
        expected = [
            "svg/edge_cuts.svg",
            "svg/f_mask.svg",
            "svg/f_paste.svg",
            "svg/f_silks.svg",
            "svg/pth_drills.svg",
        ]
        with zipfile.ZipFile(_FUZZ_FACE_ZIP) as zf:
            names = set(zf.namelist())
        for path in expected:
            assert path in names, "Missing {} in fuzz-face.manifest.zip".format(path)

    def test_manifest_json_validates_against_schema(self):
        with zipfile.ZipFile(_FUZZ_FACE_ZIP) as zf:
            data = json.loads(zf.read("manifest.json"))
        _validate_manifest(data)

    def test_manifest_has_18_components(self):
        with zipfile.ZipFile(_FUZZ_FACE_ZIP) as zf:
            data = json.loads(zf.read("manifest.json"))
        assert len(data["components"]) == 18

    def test_manifest_board_name_is_fuzz_face(self):
        with zipfile.ZipFile(_FUZZ_FACE_ZIP) as zf:
            data = json.loads(zf.read("manifest.json"))
        assert data["board_name"] == "fuzz-face"


# ---------------------------------------------------------------------------
# Fixture round-trip: fuzz-face/manifest.json (example directory)
# ---------------------------------------------------------------------------


class TestFuzzFaceManifestExample:
    """Validate the standalone example manifest.json against the schema."""

    @pytest.fixture(autouse=True)
    def skip_if_missing(self):
        if not _FUZZ_FACE_MANIFEST.exists():
            pytest.skip(
                "fuzz-face example manifest.json not found at {}".format(_FUZZ_FACE_MANIFEST)
            )

    def test_example_manifest_validates(self):
        with open(_FUZZ_FACE_MANIFEST) as f:
            data = json.load(f)
        _validate_manifest(data)

    def test_example_has_18_components(self):
        with open(_FUZZ_FACE_MANIFEST) as f:
            data = json.load(f)
        assert len(data["components"]) == 18


# ---------------------------------------------------------------------------
# End-to-end: mock board → create_manifest_zip → valid zip
# ---------------------------------------------------------------------------


def _make_board_with_components(components):
    """Build a mock board with footprints and a bounding box in nm."""
    footprints = []
    for comp in components:
        fp = _make_fp(
            ref=comp["ref"],
            value=comp["value"],
            layer_int=comp.get("layer", 0),
            pos_x_nm=comp.get("pos_x_nm", 10_000_000),
            pos_y_nm=comp.get("pos_y_nm", 20_000_000),
        )
        footprints.append(fp)

    board = MagicMock()
    board.get_footprints.return_value = footprints

    # Bounding box in nm — _get_board_bounds will detect abs(val) > 1000 and convert
    bb = MagicMock()
    bb.left = 0
    bb.top = 0
    bb.right = 60_000_000
    bb.bottom = 76_000_000
    board.bounding_box = bb
    return board


class TestEndToEnd:
    def test_full_pipeline_with_mock_board(self, tmp_path):
        """create_manifest_zip with mock board produces a valid, loadable zip."""
        board = _make_board_with_components(
            [
                {
                    "ref": "R1",
                    "value": "10K",
                    "layer": 0,
                    "pos_x_nm": 10_000_000,
                    "pos_y_nm": 20_000_000,
                },
                {
                    "ref": "C1",
                    "value": "100nF",
                    "layer": 0,
                    "pos_x_nm": 30_000_000,
                    "pos_y_nm": 40_000_000,
                },
            ]
        )

        out_zip = str(tmp_path / "test.manifest.zip")

        with (
            patch("manifest_creator.packager.export_all_layers") as mock_svg,
            patch("manifest_creator.packager.export_bom") as mock_bom,
        ):

            def fake_svg(board_path, output_dir, **kwargs):
                svg_dir = os.path.join(output_dir, "svg")
                os.makedirs(svg_dir, exist_ok=True)
                for layer in ["edge_cuts", "f_mask", "f_paste", "f_silks", "pth_drills"]:
                    with open(os.path.join(svg_dir, f"{layer}.svg"), "w") as f:
                        f.write(
                            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 76"><g/></svg>'
                        )
                return {
                    layer: f"svg/{layer}.svg"
                    for layer in ["edge_cuts", "f_mask", "f_paste", "f_silks", "pth_drills"]
                }

            mock_svg.side_effect = fake_svg

            mock_bom.return_value = [
                {
                    "ref": "R1",
                    "value": "10K",
                    "footprint": "Resistor_THT:R_Axial",
                    "description": "",
                    "notes": "",
                    "layer": "F",
                    "pos_x": 10.0,
                    "pos_y": 20.0,
                    "rotation": 0.0,
                    "do_not_populate": False,
                    "exclude_from_bom": False,
                    "outline": {"type": "bbox", "bbox": {"w": 6.0, "h": 2.0}},
                },
                {
                    "ref": "C1",
                    "value": "100nF",
                    "footprint": "Capacitor_THT:C_Disc",
                    "description": "",
                    "notes": "",
                    "layer": "F",
                    "pos_x": 30.0,
                    "pos_y": 40.0,
                    "rotation": 0.0,
                    "do_not_populate": False,
                    "exclude_from_bom": False,
                    "outline": {"type": "bbox", "bbox": {"w": 4.0, "h": 4.0}},
                },
            ]

            result = create_manifest_zip(
                board=board,
                board_path="/fake/test.kicad_pcb",
                output_path=out_zip,
                version="1.0.0",
            )

        assert result == out_zip
        assert os.path.exists(out_zip)

        with zipfile.ZipFile(out_zip) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "svg/edge_cuts.svg" in names

            data = json.loads(zf.read("manifest.json"))
            assert data["board_name"] == "test"
            assert data["version"] == "1.0.0"
            assert len(data["components"]) == 2

    def test_full_pipeline_manifest_validates_against_schema(self, tmp_path):
        """The manifest produced end-to-end passes schema validation."""
        board = _make_board_with_components([{"ref": "R1", "value": "10K", "layer": 0}])
        out_zip = str(tmp_path / "schema-check.manifest.zip")

        with (
            patch("manifest_creator.packager.export_all_layers") as mock_svg,
            patch("manifest_creator.packager.export_bom") as mock_bom,
        ):

            def fake_svg(board_path, output_dir, **kwargs):
                svg_dir = os.path.join(output_dir, "svg")
                os.makedirs(svg_dir, exist_ok=True)
                for layer in ["edge_cuts", "f_mask", "f_paste", "f_silks", "pth_drills"]:
                    with open(os.path.join(svg_dir, f"{layer}.svg"), "w") as f:
                        f.write('<svg xmlns="http://www.w3.org/2000/svg"><g/></svg>')
                return {
                    layer: f"svg/{layer}.svg"
                    for layer in ["edge_cuts", "f_mask", "f_paste", "f_silks", "pth_drills"]
                }

            mock_svg.side_effect = fake_svg
            mock_bom.return_value = [
                {
                    "ref": "R1",
                    "value": "10K",
                    "footprint": "Resistor_THT:R_Axial",
                    "description": "",
                    "notes": "",
                    "layer": "F",
                    "pos_x": 10.0,
                    "pos_y": 20.0,
                    "rotation": 0.0,
                    "do_not_populate": False,
                    "exclude_from_bom": False,
                    "outline": {"type": "bbox", "bbox": {"w": 3.0, "h": 2.0}},
                }
            ]

            create_manifest_zip(
                board=board,
                board_path="/fake/test-board.kicad_pcb",
                output_path=out_zip,
                version="1.2.3",
            )

        with zipfile.ZipFile(out_zip) as zf:
            data = json.loads(zf.read("manifest.json"))
        _validate_manifest(data)  # raises if invalid


# ---------------------------------------------------------------------------
# Smoke test: kicad-cli (skipped when not on PATH)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    shutil.which("kicad-cli") is None,
    reason="kicad-cli not on PATH — skipping smoke test",
)
class TestKicadCliSmoke:
    def test_export_layer_svg_smoke(self, tmp_path):
        """If kicad-cli is available, verify it is executable and responds to --version."""
        cli = shutil.which("kicad-cli")
        assert cli is not None
        result = subprocess.run(
            [cli, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert (
            result.returncode == 0
            or "kicad" in result.stdout.lower()
            or "kicad" in result.stderr.lower()
        )
