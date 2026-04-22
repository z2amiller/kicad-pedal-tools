"""Tests for manifest_creator.footprint_export."""

from __future__ import annotations

from unittest.mock import MagicMock

from manifest_creator.footprint_export import export_footprint_geometries

NM_PER_MM = 1_000_000


def _make_fp(
    ref,
    value="10K",
    layer_int=0,
    pos_x_nm=10_000_000,
    pos_y_nm=20_000_000,
    exclude_from_bom=False,
    dnp=False,
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
    fp.orientation.to_radians.return_value = 0.0
    fp.attributes.do_not_populate = dnp
    fp.attributes.exclude_from_bill_of_materials = exclude_from_bom
    bb = MagicMock()
    bb.width = bbox_w_nm
    bb.height = bbox_h_nm
    fp.bounding_box = bb
    return fp


def _make_board(footprints):
    board = MagicMock()
    board.get_footprints.return_value = footprints
    return board


class TestExportFootprintGeometries:
    def test_only_front_layer_returned(self):
        fps = [
            _make_fp("R1", layer_int=0),  # front
            _make_fp("R2", layer_int=31),  # back (integer 31 = BL_B_Cu)
        ]
        board = _make_board(fps)
        result = export_footprint_geometries(board)

        refs = [e["ref"] for e in result]
        assert "R1" in refs
        assert "R2" not in refs

    def test_excluded_from_bom_included_for_overlay(self):
        # exclude_from_bom footprints are pre-installed; they should appear in
        # the geometry export so the overlay can render them non-interactively.
        fps = [
            _make_fp("R1", exclude_from_bom=False),
            _make_fp("R2", exclude_from_bom=True),
        ]
        board = _make_board(fps)
        result = export_footprint_geometries(board)

        refs = [e["ref"] for e in result]
        assert "R1" in refs
        assert "R2" in refs

    def test_outline_present_and_correct_type(self):
        fps = [_make_fp("R1", bbox_w_nm=4_000_000, bbox_h_nm=3_000_000)]
        board = _make_board(fps)
        result = export_footprint_geometries(board)

        assert len(result) == 1
        outline = result[0]["outline"]
        assert outline["type"] == "bbox"
        assert "w" in outline["bbox"]
        assert "h" in outline["bbox"]
        assert abs(outline["bbox"]["w"] - 4.0) < 0.001
        assert abs(outline["bbox"]["h"] - 3.0) < 0.001

    def test_returned_dict_has_expected_keys(self):
        fps = [_make_fp("R1")]
        board = _make_board(fps)
        result = export_footprint_geometries(board)

        expected_keys = {"ref", "pos_x", "pos_y", "rotation", "outline"}
        assert expected_keys == set(result[0].keys())

    def test_dnp_component_included(self):
        """DNP components are still on the board so they appear in the overlay."""
        fps = [_make_fp("R1", dnp=True)]
        board = _make_board(fps)
        result = export_footprint_geometries(board)
        assert len(result) == 1

    def test_empty_board_returns_empty_list(self):
        board = _make_board([])
        result = export_footprint_geometries(board)
        assert result == []
