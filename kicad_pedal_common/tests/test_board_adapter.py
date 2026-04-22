"""Tests for kicad_pedal_common.board_adapter (KipyBoardAdapter)."""

import math
from unittest.mock import MagicMock

import pytest

from kicad_pedal_common.board_adapter import (
    BBoxCenter,
    FootprintData,
    KipyBoardAdapter,
)


# ---------------------------------------------------------------------------
# Helpers — mirrors _make_fp / _make_board in test_footprint.py
# ---------------------------------------------------------------------------


def _make_fp(
    ref="R1",
    value="10K",
    library="Resistor_THT",
    fp_name="R_Axial",
    layer=0,           # 0 = front copper, 31 = back copper
    pos_x_nm=10_000_000,
    pos_y_nm=20_000_000,
    rotation_rad=0.0,
    dnp=False,
    exclude_from_bom=False,
):
    """Return a MagicMock that quacks like a kipy Footprint."""
    fp = MagicMock()
    fp.reference_field.text.value = ref
    fp.value_field.text.value = value
    fp.definition.id.library = library
    fp.definition.id.name = fp_name
    fp.layer = layer
    fp.position.x = pos_x_nm
    fp.position.y = pos_y_nm
    fp.orientation.to_radians.return_value = rotation_rad
    fp.attributes.do_not_populate = dnp
    fp.attributes.exclude_from_bill_of_materials = exclude_from_bom
    return fp


def _make_board(*footprints):
    board = MagicMock()
    board.get_footprints.return_value = list(footprints)
    return board


def _make_bbox_center(center_x_nm, center_y_nm):
    """Return a mock bounding box whose .center() is at the given nm coords."""
    bb = MagicMock()
    bb.center.return_value = MagicMock(x=center_x_nm, y=center_y_nm)
    return bb


# ---------------------------------------------------------------------------
# KipyBoardAdapter.get_footprints
# ---------------------------------------------------------------------------


class TestKipyBoardAdapterGetFootprints:
    def test_returns_list_of_footprint_data(self):
        board = _make_board(_make_fp())
        adapter = KipyBoardAdapter(board)
        result = adapter.get_footprints()
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], FootprintData)

    def test_ref_and_value(self):
        board = _make_board(_make_fp(ref="C3", value="100nF"))
        result = KipyBoardAdapter(board).get_footprints()
        assert result[0].ref == "C3"
        assert result[0].value == "100nF"

    def test_footprint_id(self):
        board = _make_board(_make_fp(library="Resistor_THT", fp_name="R_Axial"))
        result = KipyBoardAdapter(board).get_footprints()
        assert result[0].footprint_id == "Resistor_THT:R_Axial"

    def test_front_layer(self):
        board = _make_board(_make_fp(layer=0))
        result = KipyBoardAdapter(board).get_footprints()
        assert result[0].layer == "F"

    def test_back_layer_value_31(self):
        board = _make_board(_make_fp(layer=31))
        result = KipyBoardAdapter(board).get_footprints()
        assert result[0].layer == "B"

    def test_position_in_mm(self):
        board = _make_board(_make_fp(pos_x_nm=15_000_000, pos_y_nm=25_000_000))
        result = KipyBoardAdapter(board).get_footprints()
        assert result[0].pos_x == pytest.approx(15.0)
        assert result[0].pos_y == pytest.approx(25.0)

    def test_rotation_degrees(self):
        board = _make_board(_make_fp(rotation_rad=math.pi / 2))
        result = KipyBoardAdapter(board).get_footprints()
        assert result[0].rotation == pytest.approx(90.0)

    def test_rotation_normalized_to_360(self):
        board = _make_board(_make_fp(rotation_rad=-math.pi / 2))
        result = KipyBoardAdapter(board).get_footprints()
        assert result[0].rotation == pytest.approx(270.0)

    def test_dnp_flag(self):
        board = _make_board(_make_fp(dnp=True))
        result = KipyBoardAdapter(board).get_footprints()
        assert result[0].dnp is True

    def test_exclude_from_bom_flag(self):
        board = _make_board(_make_fp(exclude_from_bom=True))
        result = KipyBoardAdapter(board).get_footprints()
        assert result[0].exclude_from_bom is True

    def test_skips_empty_ref(self):
        board = _make_board(_make_fp(ref=""))
        assert KipyBoardAdapter(board).get_footprints() == []

    def test_skips_ref_star(self):
        board = _make_board(_make_fp(ref="REF**"))
        assert KipyBoardAdapter(board).get_footprints() == []

    def test_skips_tilde_ref(self):
        board = _make_board(_make_fp(ref="~R1"))
        assert KipyBoardAdapter(board).get_footprints() == []

    def test_multiple_footprints(self):
        board = _make_board(
            _make_fp(ref="R1"),
            _make_fp(ref="C1"),
            _make_fp(ref="Q1"),
        )
        result = KipyBoardAdapter(board).get_footprints()
        refs = {fp.ref for fp in result}
        assert refs == {"R1", "C1", "Q1"}

    def test_board_exception_returns_empty(self):
        board = MagicMock()
        board.get_footprints.side_effect = RuntimeError("no board")
        assert KipyBoardAdapter(board).get_footprints() == []

    def test_raw_field_is_original_kipy_fp(self):
        """_raw must reference the original kipy object for adapter internals."""
        fp = _make_fp(ref="D1")
        board = _make_board(fp)
        result = KipyBoardAdapter(board).get_footprints()
        assert result[0]._raw is fp

    def test_raw_field_not_in_repr(self):
        board = _make_board(_make_fp())
        fp_data = KipyBoardAdapter(board).get_footprints()[0]
        assert "_raw" not in repr(fp_data)


# ---------------------------------------------------------------------------
# KipyBoardAdapter.get_item_bounding_box
# ---------------------------------------------------------------------------


class TestKipyBoardAdapterGetItemBoundingBox:
    def _adapter_with_bbox(self, fp, bbox_center_x_nm=None, bbox_center_y_nm=None):
        """Build an adapter whose board.get_item_bounding_box returns the given center."""
        board = MagicMock()
        board.get_footprints.return_value = [fp]
        if bbox_center_x_nm is None:
            board.get_item_bounding_box.return_value = None
        else:
            board.get_item_bounding_box.return_value = _make_bbox_center(
                bbox_center_x_nm, bbox_center_y_nm
            )
        return KipyBoardAdapter(board)

    def test_returns_none_when_bbox_unavailable(self):
        fp = _make_fp()
        adapter = self._adapter_with_bbox(fp)
        fp_data_list = adapter.get_footprints()
        result = adapter.get_item_bounding_box(fp_data_list[0])
        assert result is None

    def test_returns_bbox_center_instance(self):
        fp = _make_fp(pos_x_nm=10_000_000, pos_y_nm=20_000_000)
        adapter = self._adapter_with_bbox(fp, 13_000_000, 24_000_000)
        fp_data_list = adapter.get_footprints()
        result = adapter.get_item_bounding_box(fp_data_list[0])
        assert isinstance(result, BBoxCenter)

    def test_center_values_in_mm(self):
        # fp at (10, 20) mm; bbox centre at (13, 24) mm → offset (3, 4) mm
        fp = _make_fp(pos_x_nm=10_000_000, pos_y_nm=20_000_000)
        adapter = self._adapter_with_bbox(fp, 13_000_000, 24_000_000)
        fp_data_list = adapter.get_footprints()
        result = adapter.get_item_bounding_box(fp_data_list[0])
        assert result.cx_mm == pytest.approx(3.0)
        assert result.cy_mm == pytest.approx(4.0)

    def test_zero_offset_when_center_at_origin(self):
        fp = _make_fp(pos_x_nm=10_000_000, pos_y_nm=20_000_000)
        adapter = self._adapter_with_bbox(fp, 10_000_000, 20_000_000)
        fp_data_list = adapter.get_footprints()
        result = adapter.get_item_bounding_box(fp_data_list[0])
        assert result.cx_mm == pytest.approx(0.0)
        assert result.cy_mm == pytest.approx(0.0)

    def test_returns_none_when_raw_is_none(self):
        """Manually constructed FootprintData with _raw=None should return None."""
        board = MagicMock()
        board.get_item_bounding_box.return_value = _make_bbox_center(1_000_000, 2_000_000)
        adapter = KipyBoardAdapter(board)
        fp_data = FootprintData(
            ref="R1",
            value="10K",
            footprint_id="Lib:Fp",
            layer="F",
            pos_x=0.0,
            pos_y=0.0,
            rotation=0.0,
            dnp=False,
            exclude_from_bom=False,
            _raw=None,
        )
        assert adapter.get_item_bounding_box(fp_data) is None

    def test_exception_returns_none(self):
        board = MagicMock()
        board.get_footprints.return_value = [_make_fp()]
        board.get_item_bounding_box.side_effect = RuntimeError("board error")
        adapter = KipyBoardAdapter(board)
        fp_data_list = adapter.get_footprints()
        assert adapter.get_item_bounding_box(fp_data_list[0]) is None

    def test_passes_raw_fp_to_board(self):
        """board.get_item_bounding_box should be called with the original kipy fp."""
        fp = _make_fp()
        board = MagicMock()
        board.get_footprints.return_value = [fp]
        board.get_item_bounding_box.return_value = None
        adapter = KipyBoardAdapter(board)
        fp_data_list = adapter.get_footprints()
        adapter.get_item_bounding_box(fp_data_list[0])
        board.get_item_bounding_box.assert_called_once_with(fp)
