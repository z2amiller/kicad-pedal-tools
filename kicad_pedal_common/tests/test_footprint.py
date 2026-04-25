"""Tests for kicad_pedal_common.footprint."""

import math
from unittest.mock import MagicMock

import pytest

from kicad_pedal_common.footprint import (
    get_bounding_box,
    get_footprint_bbox_center_offset,
    get_footprints,
)

# ---------------------------------------------------------------------------
# Helpers for building mock footprints
# ---------------------------------------------------------------------------


def _make_fp(
    ref="R1",
    value="10K",
    library="Resistor_THT",
    fp_name="R_Axial",
    layer=0,  # 0 = front copper, 31 = back copper
    pos_x_nm=10_000_000,  # 10 mm
    pos_y_nm=20_000_000,  # 20 mm
    rotation_rad=0.0,
    dnp=False,
    exclude_from_bom=False,
):
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


# ---------------------------------------------------------------------------
# get_footprints
# ---------------------------------------------------------------------------


class TestGetFootprints:
    def test_returns_list_of_dicts(self):
        board = _make_board(_make_fp())
        result = get_footprints(board)
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], dict)

    def test_ref_and_value(self):
        board = _make_board(_make_fp(ref="C3", value="100nF"))
        result = get_footprints(board)
        assert result[0]["ref"] == "C3"
        assert result[0]["value"] == "100nF"

    def test_footprint_id(self):
        board = _make_board(_make_fp(library="Resistor_THT", fp_name="R_Axial"))
        result = get_footprints(board)
        assert result[0]["footprint_id"] == "Resistor_THT:R_Axial"

    def test_front_layer(self):
        board = _make_board(_make_fp(layer=0))
        result = get_footprints(board)
        assert result[0]["layer"] == "F"

    def test_back_layer_value_31(self):
        # When kipy.board.BoardLayer is mocked, we fall back to layer == 31 check
        board = _make_board(_make_fp(layer=31))
        result = get_footprints(board)
        assert result[0]["layer"] == "B"

    def test_position_in_mm(self):
        board = _make_board(_make_fp(pos_x_nm=15_000_000, pos_y_nm=25_000_000))
        result = get_footprints(board)
        assert result[0]["pos_x"] == pytest.approx(15.0)
        assert result[0]["pos_y"] == pytest.approx(25.0)

    def test_rotation_degrees(self):
        # 90 degrees = pi/2 radians
        board = _make_board(_make_fp(rotation_rad=math.pi / 2))
        result = get_footprints(board)
        assert result[0]["rotation"] == pytest.approx(90.0)

    def test_rotation_normalized_to_360(self):
        # Negative rotation should be normalized to 0-360
        board = _make_board(_make_fp(rotation_rad=-math.pi / 2))
        result = get_footprints(board)
        # -90 deg should become 270 deg
        assert result[0]["rotation"] == pytest.approx(270.0)

    def test_dnp_flag(self):
        board = _make_board(_make_fp(dnp=True))
        result = get_footprints(board)
        assert result[0]["dnp"] is True

    def test_exclude_from_bom_flag(self):
        board = _make_board(_make_fp(exclude_from_bom=True))
        result = get_footprints(board)
        assert result[0]["exclude_from_bom"] is True

    def test_skips_empty_ref(self):
        board = _make_board(_make_fp(ref=""))
        result = get_footprints(board)
        assert result == []

    def test_skips_ref_star(self):
        board = _make_board(_make_fp(ref="REF**"))
        result = get_footprints(board)
        assert result == []

    def test_skips_tilde_ref(self):
        board = _make_board(_make_fp(ref="~R1"))
        result = get_footprints(board)
        assert result == []

    def test_multiple_footprints(self):
        board = _make_board(
            _make_fp(ref="R1"),
            _make_fp(ref="C1"),
            _make_fp(ref="Q1"),
        )
        result = get_footprints(board)
        refs = [e["ref"] for e in result]
        assert set(refs) == {"R1", "C1", "Q1"}

    def test_board_exception_returns_empty(self):
        board = MagicMock()
        board.get_footprints.side_effect = RuntimeError("no board")
        result = get_footprints(board)
        assert result == []


# ---------------------------------------------------------------------------
# get_bounding_box
# ---------------------------------------------------------------------------


class TestGetBoundingBox:
    def test_uses_bounding_box_attribute(self):
        fp = MagicMock()
        fp.bounding_box.width = 10_000_000  # 10 mm
        fp.bounding_box.height = 5_000_000  # 5 mm
        result = get_bounding_box(fp)
        assert result["w"] == pytest.approx(10.0)
        assert result["h"] == pytest.approx(5.0)

    def test_falls_back_to_default_when_bbox_unavailable(self):
        fp = MagicMock()
        fp.bounding_box = None
        fp.definition.pads = []
        result = get_bounding_box(fp)
        assert result == {"w": 5.0, "h": 5.0}

    def test_default_on_exception(self):
        fp = MagicMock()
        fp.bounding_box = None
        fp.definition.pads.side_effect = Exception("unavailable")
        result = get_bounding_box(fp)
        assert result == {"w": 5.0, "h": 5.0}

    def test_returns_dict_with_w_and_h(self):
        fp = MagicMock()
        fp.bounding_box.width = 8_000_000
        fp.bounding_box.height = 3_000_000
        result = get_bounding_box(fp)
        assert "w" in result
        assert "h" in result

    def test_handles_negative_dimensions(self):
        # KiCad can return negative width/height depending on coordinate system
        fp = MagicMock()
        fp.bounding_box.width = -10_000_000
        fp.bounding_box.height = -5_000_000
        result = get_bounding_box(fp)
        assert result["w"] == pytest.approx(10.0)
        assert result["h"] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# get_footprint_bbox_center_offset
# ---------------------------------------------------------------------------


def _make_bbox_center(center_x_nm, center_y_nm):
    """Return a mock bounding box whose .center() is at the given nm coords."""
    bb = MagicMock()
    bb.center.return_value = MagicMock(x=center_x_nm, y=center_y_nm)
    return bb


def _make_fp_with_bbox(
    pos_x_nm=10_000_000,
    pos_y_nm=20_000_000,
    rotation_rad=0.0,
    bbox_center_x_nm=None,
    bbox_center_y_nm=None,
):
    """Build mocks for both board and fp used by get_footprint_bbox_center_offset."""
    fp = MagicMock()
    fp.position.x = pos_x_nm
    fp.position.y = pos_y_nm
    fp.orientation.to_radians.return_value = rotation_rad

    board = MagicMock()
    if bbox_center_x_nm is None:
        board.get_item_bounding_box.return_value = None
    else:
        board.get_item_bounding_box.return_value = _make_bbox_center(
            bbox_center_x_nm, bbox_center_y_nm
        )
    return board, fp


class TestGetFootprintBboxCenterOffset:
    def test_returns_none_when_bbox_unavailable(self):
        board, fp = _make_fp_with_bbox()
        assert get_footprint_bbox_center_offset(board, fp) is None

    def test_zero_rotation_identity(self):
        # Bbox center is 3 mm right and 4 mm down from footprint origin (no rotation).
        # Un-rotation of a zero-rotation vector is a no-op → local == board offset.
        board, fp = _make_fp_with_bbox(
            pos_x_nm=10_000_000,
            pos_y_nm=20_000_000,
            rotation_rad=0.0,
            bbox_center_x_nm=13_000_000,  # 3 mm right
            bbox_center_y_nm=24_000_000,  # 4 mm down
        )
        cx, cy = get_footprint_bbox_center_offset(board, fp)
        assert cx == pytest.approx(3.0)
        assert cy == pytest.approx(4.0)

    def test_symmetric_footprint_returns_zero(self):
        # If bbox center coincides with fp origin, offset is (0, 0).
        board, fp = _make_fp_with_bbox(
            pos_x_nm=10_000_000,
            pos_y_nm=20_000_000,
            rotation_rad=math.pi / 4,
            bbox_center_x_nm=10_000_000,
            bbox_center_y_nm=20_000_000,
        )
        cx, cy = get_footprint_bbox_center_offset(board, fp)
        assert cx == pytest.approx(0.0)
        assert cy == pytest.approx(0.0)

    def test_90_degree_rotation_unrotates_correctly(self):
        # Regression test for the -rot vs +rot bug.
        #
        # Setup: footprint at (0,0), rotated 90° CCW (π/2 rad in KiCad convention).
        # The bbox center is displaced +5 mm in the X direction in board (world) space.
        # In board space that offset vector is (dx=5, dy=0).
        #
        # KiCad CCW rotation in Y-down: R(90°) maps local (1,0) → (0,-1).
        # So a local (0, -5) in footprint space maps to board (+5, 0).
        # Un-rotating (5, 0) by 90° should give back (0, -5) in local space.
        #
        # With the WRONG formula (using -rot):
        #   cx_local = 5*cos(-π/2) - 0*sin(-π/2) = 5*0 - 0*(-1) = 0  ← looks right
        #   cy_local = 5*sin(-π/2) + 0*cos(-π/2) = 5*(-1) + 0 = -5   ← also right
        # That happens to be correct for this vector, so we also test (0, 5):
        #
        # Board offset (dx=0, dy=5):  local Y maps to world X for 90° CCW rotation.
        # R(90°) maps local (5, 0) → board (0, 5).  (local x → board y for KiCad CCW in Y-down)
        # Un-rotating (0, 5) by 90° should give (5, 0).
        #
        # With the WRONG formula (using -rot):
        #   cx_local = 0*cos(-π/2) - 5*sin(-π/2) = 0 - 5*(-1) = +5  ← correct
        #   cy_local = 0*sin(-π/2) + 5*cos(-π/2) = 0 + 0 = 0         ← correct
        #
        # Neither pure-axis test caught the bug.  Use a diagonal offset instead.
        # Board offset (dx=3, dy=4) with rotation=90°:
        # Un-rotation with CORRECT formula (+rot):
        #   cx_local = 3*cos(π/2) - 4*sin(π/2) = 3*0 - 4*1 = -4
        #   cy_local = 3*sin(π/2) + 4*cos(π/2) = 3*1 + 4*0 = +3
        # Un-rotation with WRONG formula (-rot):
        #   cx_local = 3*cos(-π/2) - 4*sin(-π/2) = 3*0 - 4*(-1) = +4  ← WRONG sign
        #   cy_local = 3*sin(-π/2) + 4*cos(-π/2) = 3*(-1) + 4*0 = -3  ← WRONG sign
        board, fp = _make_fp_with_bbox(
            pos_x_nm=0,
            pos_y_nm=0,
            rotation_rad=math.pi / 2,
            bbox_center_x_nm=3_000_000,  # 3 mm in board X
            bbox_center_y_nm=4_000_000,  # 4 mm in board Y
        )
        cx, cy = get_footprint_bbox_center_offset(board, fp)
        assert cx == pytest.approx(-4.0), "un-rotation cx wrong — check -rot vs +rot"
        assert cy == pytest.approx(3.0), "un-rotation cy wrong — check -rot vs +rot"

    def test_180_degree_rotation(self):
        # 180° rotation: R(π) maps (dx, dy) → (-dx, -dy) in local space.
        board, fp = _make_fp_with_bbox(
            pos_x_nm=0,
            pos_y_nm=0,
            rotation_rad=math.pi,
            bbox_center_x_nm=3_000_000,
            bbox_center_y_nm=4_000_000,
        )
        cx, cy = get_footprint_bbox_center_offset(board, fp)
        assert cx == pytest.approx(-3.0)
        assert cy == pytest.approx(-4.0)

    def test_exception_returns_none(self):
        board = MagicMock()
        board.get_item_bounding_box.side_effect = RuntimeError("board error")
        fp = MagicMock()
        assert get_footprint_bbox_center_offset(board, fp) is None
