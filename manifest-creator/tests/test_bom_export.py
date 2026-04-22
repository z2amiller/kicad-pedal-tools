"""Tests for manifest_creator.bom_export."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from manifest_creator.bom_export import export_bom

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
    """Build a MagicMock footprint with the given attributes."""
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
    # bounding box
    bb = MagicMock()
    bb.width = bbox_w_nm
    bb.height = bbox_h_nm
    fp.bounding_box = bb
    return fp


def _make_board(footprints):
    board = MagicMock()
    board.get_footprints.return_value = footprints
    return board


class TestExportBom:
    def test_returns_list_of_dicts_for_all_components(self):
        fps = [
            _make_fp("R1", "10K"),
            _make_fp("C1", "100nF"),
            _make_fp("Q1", "BC547", dnp=True),
        ]
        board = _make_board(fps)
        result = export_bom(board)

        # DNP component is omitted; only the two normal components are returned
        assert isinstance(result, list)
        assert len(result) == 2

    def test_each_dict_has_required_keys(self):
        fps = [_make_fp("R1", "10K")]
        board = _make_board(fps)
        result = export_bom(board)

        required_keys = {
            "ref",
            "value",
            "footprint",
            "description",
            "notes",
            "layer",
            "pos_x",
            "pos_y",
            "rotation",
            "do_not_populate",
            "exclude_from_bom",
            "outline",
        }
        assert required_keys.issubset(set(result[0].keys()))

    def test_ref_value_layer_pos_rotation_correct(self):
        fps = [_make_fp("R1", "10K", layer_int=0, pos_x_nm=15_000_000, pos_y_nm=25_000_000)]
        board = _make_board(fps)
        result = export_bom(board)
        entry = result[0]

        assert entry["ref"] == "R1"
        assert entry["value"] == "10K"
        assert entry["layer"] == "F"
        assert abs(entry["pos_x"] - 15.0) < 0.001
        assert abs(entry["pos_y"] - 25.0) < 0.001
        assert entry["rotation"] == pytest.approx(0.0, abs=0.001)

    def test_outline_has_bbox_with_w_and_h(self):
        fps = [_make_fp("R1", "10K", bbox_w_nm=6_000_000, bbox_h_nm=4_000_000)]
        board = _make_board(fps)
        result = export_bom(board)
        outline = result[0]["outline"]

        assert outline["type"] == "bbox"
        assert "w" in outline["bbox"]
        assert "h" in outline["bbox"]
        assert abs(outline["bbox"]["w"] - 6.0) < 0.001
        assert abs(outline["bbox"]["h"] - 4.0) < 0.001

    def test_non_dnp_component_not_flagged(self):
        fps = [
            _make_fp("R1", "10K", dnp=False),
        ]
        board = _make_board(fps)
        result = export_bom(board)

        r1 = next(e for e in result if e["ref"] == "R1")
        assert r1["do_not_populate"] is False

    def test_dnp_components_are_omitted(self):
        fps = [
            _make_fp("R1", "10K"),
            _make_fp("R2", "DNP", dnp=True),
        ]
        board = _make_board(fps)
        result = export_bom(board)
        refs = [e["ref"] for e in result]
        assert "R1" in refs
        assert "R2" not in refs
        assert len(result) == 1

    def test_exclude_from_bom_included_as_installed(self):
        # exclude_from_bom components (e.g. pre-installed panel-mount parts)
        # are included in the manifest with installed=True so the overlay can
        # render them as non-interactive.
        fps = [
            _make_fp("R1", "10K"),
            _make_fp("R3", "PWR", exclude_from_bom=True),
        ]
        board = _make_board(fps)
        result = export_bom(board)
        refs = [e["ref"] for e in result]
        assert "R1" in refs
        assert "R3" in refs
        r3 = next(e for e in result if e["ref"] == "R3")
        assert r3.get("installed") is True

    def test_dnp_omitted_but_exclude_from_bom_included(self):
        # DNP components are physically absent and excluded entirely.
        # exclude_from_bom components are pre-installed and included with installed=True.
        fps = [
            _make_fp("R1", "10K"),
            _make_fp("R2", "DNP", dnp=True),
            _make_fp("R3", "PWR", exclude_from_bom=True),
            _make_fp("C1", "100nF"),
        ]
        board = _make_board(fps)
        result = export_bom(board)
        refs = [e["ref"] for e in result]
        assert "R2" not in refs
        assert "R1" in refs
        assert "R3" in refs
        assert "C1" in refs
        r3 = next(e for e in result if e["ref"] == "R3")
        assert r3.get("installed") is True

    def test_empty_board_returns_empty_list(self):
        board = _make_board([])
        result = export_bom(board)
        assert result == []
