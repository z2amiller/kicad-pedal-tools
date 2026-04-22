"""Integration tests for BuildDocGenerator with a mock BoardAdapter."""

import os
from unittest.mock import MagicMock, patch

import pytest
from kicad_pedal_common.board_adapter import FootprintData, KipyBoardAdapter
from pypdf import PdfReader

from build_doc_generator import BuildDocGenerator, GeneratorParams
from panel_config import EnclosureConfig, PanelConfig

# ── Mock adapter fixture ──────────────────────────────────────────────────────


def _make_fp_data(ref, value):
    return FootprintData(
        ref=ref,
        value=value,
        footprint_id="Device:Generic",
        layer="F",
        pos_x=0.0,
        pos_y=0.0,
        rotation=0.0,
        dnp=False,
        exclude_from_bom=False,
        fields={},
        pad_count=3,
    )


def _make_adapter(tmp_path):
    """Build a KipyBoardAdapter wrapping a mock kipy board."""
    board = MagicMock()
    board.name = str(tmp_path / "test.kicad_pcb")
    board.get_project.return_value.path = str(tmp_path)
    board.get_footprints.return_value = []
    board.get_shapes.return_value = []

    adapter = KipyBoardAdapter(board)
    # Patch get_footprints to return FootprintData objects directly
    adapter.get_footprints = lambda: [_make_fp_data("R1", "10k"), _make_fp_data("C1", "100nF")]
    adapter.get_board_path = lambda: str(tmp_path / "test.kicad_pcb")
    adapter.get_board_bounding_box = lambda: None
    return adapter


def _make_params(tmp_path, **flags):
    return GeneratorParams(
        project_name="Test Project",
        author="Tester",
        revision="1.0",
        output_path=str(tmp_path / "out.pdf"),
        sch_path="",
        include_cover=flags.get("include_cover", False),
        include_bom=flags.get("include_bom", False),
        include_enclosure=flags.get("include_enclosure", False),
        include_tayda=flags.get("include_tayda", False),
        include_sch=flags.get("include_sch", False),
    )


def _fake_tayda_pdf(
    holes, project_name, author, page_num, total_pages, out_path, log=None, enclosure_label=None
):
    """Write a minimal single-page PDF for the Tayda manifest."""
    from reportlab.pdfgen import canvas as rl_canvas

    c = rl_canvas.Canvas(out_path)
    c.drawString(50, 750, "Tayda placeholder")
    c.showPage()
    c.save()
    return out_path


def _fake_enclosure_pdf(
    adapter, config, project_name, author, total_pages, page_num, out_path, log=None
):
    """Write a minimal single-page PDF so the generator can merge it."""
    from reportlab.pdfgen import canvas as rl_canvas

    c = rl_canvas.Canvas(out_path)
    c.drawString(50, 750, "Enclosure placeholder")
    c.showPage()
    c.save()
    return []


@pytest.mark.parametrize(
    "flags,expected_pages",
    [
        ({"include_cover": True}, 1),
        ({"include_bom": True}, 1),
        ({"include_cover": True, "include_bom": True}, 2),
        ({"include_cover": True, "include_bom": True, "include_enclosure": True}, 3),
        ({"include_enclosure": True}, 1),
        ({"include_enclosure": True, "include_tayda": True}, 2),
        ({"include_cover": True, "include_enclosure": True, "include_tayda": True}, 3),
        # include_tayda without include_enclosure produces no tayda page
        ({"include_cover": True, "include_tayda": True}, 1),
    ],
)
def test_generate_page_count(flags, expected_pages, tmp_path):
    adapter = _make_adapter(tmp_path)
    params = _make_params(tmp_path, **flags)

    with (
        patch("board_image.export_board_pdf", return_value=None),
        patch("build_doc_generator.board_size_mm", return_value=None),
        patch("build_doc_generator.generate_enclosure_pdf", side_effect=_fake_enclosure_pdf),
        patch("build_doc_generator.generate_tayda_manifest_pdf", side_effect=_fake_tayda_pdf),
        patch(
            "build_doc_generator.load_panel_config",
            return_value=PanelConfig(
                enclosure=EnclosureConfig(width=62, height=117), footprints={}, fixed_holes=[]
            ),
        ),
    ):
        gen = BuildDocGenerator(adapter, params)
        gen.generate()

    out = params.output_path
    assert os.path.exists(out)
    assert len(PdfReader(out).pages) == expected_pages


def test_generate_raises_when_no_sections(tmp_path):
    adapter = _make_adapter(tmp_path)
    params = _make_params(tmp_path)  # all flags False

    gen = BuildDocGenerator(adapter, params)
    with pytest.raises(RuntimeError, match="No pages"):
        gen.generate()


def test_output_pdf_exists(tmp_path):
    adapter = _make_adapter(tmp_path)
    params = _make_params(tmp_path, include_bom=True)

    with (
        patch("board_image.export_board_pdf", return_value=None),
        patch("build_doc_generator.board_size_mm", return_value=None),
    ):
        BuildDocGenerator(adapter, params).generate()

    assert os.path.exists(params.output_path)
