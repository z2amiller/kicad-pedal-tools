"""Tests for manifest_creator.svg_export."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from manifest_creator.svg_export import DEFAULT_LAYERS, export_all_layers


class TestExportAllLayers:
    def test_calls_export_layer_svg_for_each_default_layer(self, tmp_path):
        with (
            patch("manifest_creator.svg_export.find_kicad_cli", return_value="/usr/bin/kicad-cli"),
            patch("manifest_creator.svg_export.export_layer_svg") as mock_export,
        ):
            export_all_layers(
                board_path="/fake/board.kicad_pcb",
                output_dir=str(tmp_path),
            )

        assert mock_export.call_count == len(DEFAULT_LAYERS)
        called_layers = [c.args[1] for c in mock_export.call_args_list]
        # All default logical names should appear in calls
        from kicad_pedal_common.plotting import LAYER_MAP

        for logical in DEFAULT_LAYERS:
            assert LAYER_MAP[logical] in called_layers

    def test_returned_dict_has_right_keys_and_values(self, tmp_path):
        with (
            patch("manifest_creator.svg_export.find_kicad_cli", return_value="/usr/bin/kicad-cli"),
            patch("manifest_creator.svg_export.export_layer_svg"),
        ):
            result = export_all_layers(
                board_path="/fake/board.kicad_pcb",
                output_dir=str(tmp_path),
            )

        assert set(result.keys()) == set(DEFAULT_LAYERS)
        for logical_name, rel_path in result.items():
            assert rel_path == "svg/{}.svg".format(logical_name)

    def test_raises_runtime_error_when_kicad_cli_not_found(self, tmp_path):
        with patch("manifest_creator.svg_export.find_kicad_cli", return_value=None):
            with pytest.raises(RuntimeError, match="kicad-cli not found"):
                export_all_layers(
                    board_path="/fake/board.kicad_pcb",
                    output_dir=str(tmp_path),
                )

    def test_explicit_kicad_cli_skips_find(self, tmp_path):
        with (
            patch("manifest_creator.svg_export.find_kicad_cli") as mock_find,
            patch("manifest_creator.svg_export.export_layer_svg"),
        ):
            export_all_layers(
                board_path="/fake/board.kicad_pcb",
                output_dir=str(tmp_path),
                kicad_cli="/custom/kicad-cli",
            )

        mock_find.assert_not_called()

    def test_custom_layer_subset(self, tmp_path):
        custom_layers = ["edge_cuts", "f_silks"]
        with (
            patch("manifest_creator.svg_export.find_kicad_cli", return_value="/usr/bin/kicad-cli"),
            patch("manifest_creator.svg_export.export_layer_svg") as mock_export,
        ):
            result = export_all_layers(
                board_path="/fake/board.kicad_pcb",
                output_dir=str(tmp_path),
                layers=custom_layers,
            )

        assert set(result.keys()) == set(custom_layers)
        assert mock_export.call_count == 2

    def test_svg_subdir_is_created(self, tmp_path):
        with (
            patch("manifest_creator.svg_export.find_kicad_cli", return_value="/usr/bin/kicad-cli"),
            patch("manifest_creator.svg_export.export_layer_svg"),
        ):
            export_all_layers(
                board_path="/fake/board.kicad_pcb",
                output_dir=str(tmp_path),
            )

        assert (tmp_path / "svg").is_dir()
