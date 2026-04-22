from kicad_pedal_common.board_adapter import FootprintData

from footprint_utils import (
    Controls,
    extract_controls,
    friendly_footprint_type,
    get_field,
    ref_sort_key,
)


def test_ref_sort_key_numeric_order():
    assert ref_sort_key("R10") > ref_sort_key("R9")


def test_ref_sort_key_prefix_order():
    assert ref_sort_key("C1") < ref_sort_key("R1")


def test_ref_sort_key_no_number():
    assert ref_sort_key("U") == ("U", 0)


def test_ref_sort_key_mixed_case():
    assert ref_sort_key("rv1") == ("RV", 1)


def test_friendly_type_resistor():
    assert friendly_footprint_type("R1", "") == "Resistor, 1/4W"


def test_friendly_type_capacitor():
    assert friendly_footprint_type("C10", "") == "Capacitor"


def test_friendly_type_pot():
    assert friendly_footprint_type("RV2", "") == "Potentiometer"


def test_friendly_type_unknown_uses_fp_name():
    assert friendly_footprint_type("XY1", "MyFootprint") == "MyFootprint"


def test_friendly_type_unknown_no_fp_name():
    assert friendly_footprint_type("XY1", "") == "Component"


def _make_fp_data(fields_dict=None, ref="U1", fp_id="Lib:Part", pad_count=3, value="val"):
    return FootprintData(
        ref=ref,
        value=value,
        footprint_id=fp_id,
        layer="F",
        pos_x=0,
        pos_y=0,
        rotation=0,
        dnp=False,
        exclude_from_bom=False,
        fields=fields_dict or {},
        pad_count=pad_count,
    )


class MockAdapter:
    def __init__(self, fps):
        self._fps = fps

    def get_footprints(self):
        return self._fps


def test_get_field_found():
    fp = _make_fp_data(fields_dict={"control": "Volume"})
    assert get_field(fp, "Control") == "Volume"


def test_get_field_found_case_insensitive():
    fp = _make_fp_data(fields_dict={"control": "Level"})
    assert get_field(fp, "Control") == "Level"


def test_get_field_missing():
    fp = _make_fp_data(fields_dict={})
    assert get_field(fp, "Control") == ""


def test_get_field_wrong_name():
    fp = _make_fp_data(fields_dict={"datasheet": "http://example.com"})
    assert get_field(fp, "Control") == ""


def test_get_field_non_field_item_skipped():
    # With FootprintData, there's no longer a "non-field item" concept
    # This test becomes: absent key returns ""
    fp = _make_fp_data(fields_dict={})
    assert get_field(fp, "Control") == ""


# ── extract_controls ──────────────────────────────────────────────────────────


def _make_fp_with_control(ref, value, control, fp_id="Lib:Part", pad_count=3):
    fields = {"control": control} if control else {}
    return FootprintData(
        ref=ref,
        value=value,
        footprint_id=fp_id,
        layer="F",
        pos_x=0,
        pos_y=0,
        rotation=0,
        dnp=False,
        exclude_from_bom=False,
        fields=fields,
        pad_count=pad_count,
    )


def _make_board_ec(fps):
    return MockAdapter(fps)


def test_extract_controls_empty_board():
    result = extract_controls(_make_board_ec([]), set())
    assert result == Controls(external=[], internal=[])


def test_extract_controls_no_control_field():
    fp = _make_fp_data(ref="R1", fields_dict={})
    result = extract_controls(_make_board_ec([fp]), set())
    assert result == Controls(external=[], internal=[])


def test_extract_controls_external_vs_internal():
    ext_fp = _make_fp_with_control("RV1", "B100K", "Volume", "Panel:Alpha9mm")
    int_fp = _make_fp_with_control("RV2", "B10K", "Tone", "Lib:Trim")
    external_ids = {"Panel:Alpha9mm"}
    result = extract_controls(_make_board_ec([ext_fp, int_fp]), external_ids)
    assert len(result.external) == 1
    assert result.external[0].label == "Volume"
    assert len(result.internal) == 1
    assert result.internal[0].label == "Tone"


def test_extract_controls_deduplicates_labels():
    fps = [
        _make_fp_with_control("RV1", "B100K", "Volume"),
        _make_fp_with_control("RV2", "B100K", "Volume"),  # duplicate label
    ]
    result = extract_controls(_make_board_ec(fps), set())
    assert len(result.internal) == 1


def test_extract_controls_excludes_leds_and_diodes():
    fps = [
        _make_fp_with_control("D1", "1N4148", "Clip"),
        _make_fp_with_control("LED1", "Red", "Indicator"),
    ]
    result = extract_controls(_make_board_ec(fps), set())
    assert result == Controls(external=[], internal=[])


def test_extract_controls_excludes_led_smd_library():
    fp = _make_fp_with_control("U5", "LED", "Status", fp_id="LED_SMD:LED_0805_2012Metric")
    result = extract_controls(_make_board_ec([fp]), set())
    assert result == Controls(external=[], internal=[])


def test_extract_controls_excludes_test_points_from_internal():
    fp = _make_fp_with_control("TP1", "TestPoint", "Signal")
    result = extract_controls(_make_board_ec([fp]), set())
    assert result == Controls(external=[], internal=[])


def test_extract_controls_excludes_single_pad_from_internal():
    fp = _make_fp_with_control("RV1", "B100K", "Volume", pad_count=0)
    result = extract_controls(_make_board_ec([fp]), set())
    assert result == Controls(external=[], internal=[])


def test_extract_controls_keeps_multi_pad_internal():
    fp = _make_fp_with_control("RV1", "B100K", "Volume", pad_count=3)
    result = extract_controls(_make_board_ec([fp]), set())
    assert len(result.internal) == 1


def test_extract_controls_sorted_by_ref():
    fps = [
        _make_fp_with_control("RV10", "B100K", "Reverb"),
        _make_fp_with_control("RV2", "B100K", "Delay"),
        _make_fp_with_control("RV1", "B100K", "Volume"),
    ]
    result = extract_controls(_make_board_ec(fps), set())
    labels = [c.label for c in result.internal]
    assert labels == ["Volume", "Delay", "Reverb"]
