from kicad_pedal_common.board_adapter import FootprintData

from bom_pages import collect_bom


def _make_fp_data(
    ref,
    value,
    control="",
    excluded_bom=False,
    dnp=False,
    fp_id="Generic:Generic",
    description="",
):
    fields = {}
    if control:
        fields["control"] = control
    return FootprintData(
        ref=ref,
        value=value,
        footprint_id=fp_id,
        layer="F",
        pos_x=0.0,
        pos_y=0.0,
        rotation=0.0,
        dnp=dnp,
        exclude_from_bom=excluded_bom,
        description=description,
        fields=fields,
        pad_count=3,
    )


def test_excludes_dnp():
    bom = collect_bom([_make_fp_data("R1", "10k", dnp=True)])
    assert bom == []


def test_excludes_excluded_from_bom():
    bom = collect_bom([_make_fp_data("R1", "10k", excluded_bom=True)])
    assert bom == []


def test_controls_always_included_despite_exclusion_flags():
    fp = _make_fp_data("RV1", "B100K", control="Volume", excluded_bom=True)
    bom = collect_bom([fp])
    rows = [r for r in bom if not r.get("separator")]
    assert len(rows) == 1
    assert rows[0]["ref"] == "Volume"
    assert rows[0]["is_control"] is True


def test_controls_sort_after_parts():
    fps = [
        _make_fp_data("RV1", "B100K", control="Volume"),
        _make_fp_data("R1", "10k"),
    ]
    bom = collect_bom(fps)
    non_sep = [r for r in bom if not r.get("separator")]
    assert non_sep[0]["ref"] == "R1"
    assert non_sep[1]["ref"] == "Volume"


def test_separator_inserted_between_parts_and_controls():
    fps = [_make_fp_data("R1", "10k"), _make_fp_data("RV1", "B100K", control="Volume")]
    bom = collect_bom(fps)
    assert any(r.get("separator") for r in bom)


def test_no_separator_when_only_controls():
    fps = [_make_fp_data("RV1", "B100K", control="Volume")]
    bom = collect_bom(fps)
    assert not any(r.get("separator") for r in bom)


def test_no_separator_when_no_controls():
    fps = [_make_fp_data("R1", "10k"), _make_fp_data("C1", "100nF")]
    bom = collect_bom(fps)
    assert not any(r.get("separator") for r in bom)


def test_numeric_sort_order():
    fps = [_make_fp_data(f"R{i}", "10k") for i in [10, 2, 1]]
    bom = collect_bom(fps)
    refs = [r["ref"] for r in bom]
    assert refs == ["R1", "R2", "R10"]


def test_skips_placeholder_refs():
    fps = [
        _make_fp_data("REF**", "val"),
        _make_fp_data("~1", "val"),
        _make_fp_data("R1", "10k"),
    ]
    bom = collect_bom(fps)
    assert len(bom) == 1
    assert bom[0]["ref"] == "R1"
