"""Tests for kicad_pedal_common.bom."""

from kicad_pedal_common.bom import (
    BOM_GROUP_ORDER,
    CAPACITORS,
    DIODES,
    OTHER,
    RESISTORS,
    TRANSISTORS,
    bom_group,
    humanized_value_key,
    sort_bom,
)

# ---------------------------------------------------------------------------
# bom_group
# ---------------------------------------------------------------------------


class TestBomGroup:
    def test_resistor_r1(self):
        assert bom_group("R1") == RESISTORS

    def test_resistor_r10(self):
        assert bom_group("R10") == RESISTORS

    def test_resistor_r_uppercase(self):
        assert bom_group("R100") == RESISTORS

    def test_potentiometer_rv1_is_other(self):
        # RV* must NOT match RESISTORS — it's a potentiometer
        assert bom_group("RV1") == OTHER

    def test_potentiometer_rv10_is_other(self):
        assert bom_group("RV10") == OTHER

    def test_diode_d1(self):
        assert bom_group("D1") == DIODES

    def test_diode_d10(self):
        assert bom_group("D10") == DIODES

    def test_transistor_q1(self):
        assert bom_group("Q1") == TRANSISTORS

    def test_capacitor_c1(self):
        assert bom_group("C1") == CAPACITORS

    def test_capacitor_cp1(self):
        # CP* (polarized cap) must match CAPACITORS
        assert bom_group("CP1") == CAPACITORS

    def test_capacitor_cp10(self):
        assert bom_group("CP10") == CAPACITORS

    def test_led_is_other(self):
        assert bom_group("LED1") == OTHER

    def test_switch_is_other(self):
        assert bom_group("SW1") == OTHER

    def test_jack_is_other(self):
        assert bom_group("J1") == OTHER

    def test_ic_is_other(self):
        assert bom_group("U1") == OTHER

    def test_empty_is_other(self):
        assert bom_group("") == OTHER


# ---------------------------------------------------------------------------
# humanized_value_key
# ---------------------------------------------------------------------------


class TestHumanizedValueKey:
    def test_100k_lt_1m(self):
        assert humanized_value_key("100K") < humanized_value_key("1M")

    def test_4u7_lt_10u(self):
        assert humanized_value_key("4.7uF") < humanized_value_key("10uF")

    def test_900k_lt_1m(self):
        assert humanized_value_key("900K") < humanized_value_key("1M")

    def test_numeric_lt_non_numeric(self):
        # numeric values should sort before non-numeric (by is_numeric flag)
        key_num = humanized_value_key("100K")
        key_str = humanized_value_key("BC547")
        assert key_num[0] == 0  # is_numeric = 0
        assert key_str[0] == 1  # is_numeric = 1
        assert key_num < key_str

    def test_1k_lt_10k(self):
        assert humanized_value_key("1K") < humanized_value_key("10K")

    def test_100n_lt_1u(self):
        assert humanized_value_key("100n") < humanized_value_key("1u")

    def test_47p_lt_100p(self):
        assert humanized_value_key("47p") < humanized_value_key("100p")

    def test_non_numeric_sorts_lexically(self):
        # Two non-numeric values sort by original string
        key_a = humanized_value_key("BC547")
        key_b = humanized_value_key("BC558")
        assert key_a < key_b

    def test_original_string_preserved(self):
        key = humanized_value_key("4.7uF")
        assert key[2] == "4.7uF"

    def test_equal_values(self):
        assert humanized_value_key("10K") == humanized_value_key("10K")

    # SI prefix cross-boundary ordering (regression for manifest-13j)
    def test_pf_lt_nf(self):
        # pico < nano: 100pF must sort before 1nF
        assert humanized_value_key("100pF") < humanized_value_key("1nF")

    def test_nf_lt_uf(self):
        # nano < micro: 100nF must sort before 1uF
        assert humanized_value_key("100nF") < humanized_value_key("1uF")

    def test_pf_lt_uf(self):
        # pico < micro: 10pF must sort before 100uF
        assert humanized_value_key("10pF") < humanized_value_key("100uF")

    def test_uf_lt_mf(self):
        # micro < milli: 100uF must sort before 1mF (milli-farad)
        assert humanized_value_key("100uF") < humanized_value_key("1mF")

    def test_sorted_cap_list(self):
        # Full ascending order: 100pF, 1nF, 100nF, 1uF, 10uF, 100uF
        caps = ["10uF", "1nF", "100pF", "100uF", "100nF", "1uF"]
        assert sorted(caps, key=humanized_value_key) == [
            "100pF",
            "1nF",
            "100nF",
            "1uF",
            "10uF",
            "100uF",
        ]

    def test_r_suffix_ohms(self):
        # No suffix = bare ohms, kilo, mega ordering
        assert humanized_value_key("100R") < humanized_value_key("1k")
        assert humanized_value_key("1k") < humanized_value_key("1M")

    # Uppercase SI prefix variants — KiCad sometimes exports "100UF", "10PF"
    # These are the root cause of the manifest-13j bug.
    def test_uppercase_UF_lt_no_suffix(self):
        # "1UF" (uppercase U = micro) must be treated as 1e-6, not 1.0
        # Without the fix: 1UF -> (0, 1.0) which would sort AFTER 100PF -> (0, 100.0) is wrong
        # With the fix: 1UF -> (0, 1e-6), 100PF -> (0, 1e-10), so 100PF < 1UF (correct)
        assert humanized_value_key("100PF") < humanized_value_key("1UF")

    def test_uppercase_PF_lt_uppercase_NF(self):
        # P (pico) < N (nano) when uppercase
        assert humanized_value_key("100PF") < humanized_value_key("1NF")

    def test_uppercase_NF_lt_uppercase_UF(self):
        # N (nano) < U (micro) when uppercase
        assert humanized_value_key("100NF") < humanized_value_key("1UF")

    def test_uppercase_UF_gt_lowercase_pf(self):
        # Mixed case: "1UF" (micro) must sort after "100pF" (pico)
        assert humanized_value_key("100pF") < humanized_value_key("1UF")

    def test_sorted_cap_list_uppercase(self):
        # Uppercase SI suffix variants sort in same order as lowercase
        caps = ["10UF", "1NF", "100PF", "100UF", "100NF", "1UF"]
        assert sorted(caps, key=humanized_value_key) == [
            "100PF",
            "1NF",
            "100NF",
            "1UF",
            "10UF",
            "100UF",
        ]


# ---------------------------------------------------------------------------
# sort_bom
# ---------------------------------------------------------------------------


class TestSortBom:
    def _make_entries(self, refs):
        return [{"ref": r, "value": "10K"} for r in refs]

    def test_returns_new_list(self):
        entries = self._make_entries(["R1"])
        result = sort_bom(entries)
        assert result is not entries

    def test_group_order(self):
        entries = self._make_entries(["Q1", "D1", "C1", "R1", "SW1"])
        result = sort_bom(entries)
        refs = [e["ref"] for e in result]
        # R before D before Q before C before SW (OTHER)
        assert refs.index("R1") < refs.index("D1")
        assert refs.index("D1") < refs.index("Q1")
        assert refs.index("Q1") < refs.index("C1")
        assert refs.index("C1") < refs.index("SW1")

    def test_numeric_sort_within_group(self):
        entries = self._make_entries(["R10", "R2", "R1"])
        result = sort_bom(entries)
        refs = [e["ref"] for e in result]
        assert refs == ["R1", "R2", "R10"]

    def test_cp_in_capacitors(self):
        entries = self._make_entries(["CP1", "C1"])
        result = sort_bom(entries)
        refs = [e["ref"] for e in result]
        # Both should be in CAPACITORS group, sorted by ref
        assert "C1" in refs
        assert "CP1" in refs
        assert refs.index("C1") < refs.index("CP1")

    def test_rv_in_other(self):
        entries = self._make_entries(["R1", "RV1"])
        result = sort_bom(entries)
        refs = [e["ref"] for e in result]
        # R1 (RESISTORS) should come before RV1 (OTHER)
        assert refs.index("R1") < refs.index("RV1")

    def test_empty_list(self):
        assert sort_bom([]) == []

    def test_all_groups_present_in_bom_group_order(self):
        assert BOM_GROUP_ORDER == [RESISTORS, DIODES, TRANSISTORS, CAPACITORS, OTHER]
