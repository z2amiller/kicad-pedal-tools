"""IPC plugin entry point for KiCad 9+.

Reads KICAD_API_SOCKET and KICAD_API_TOKEN from the environment, connects
to the running KiCad instance via kipy, then exports a .manifest.zip.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

# kicad_pedal_common is vendored alongside this plugin (PCM bundle adds it to
# sys.path via the plugin_dir prepend below), so the import resolves at
# runtime even without an editable install.
_watchdog_available = False
try:
    from kicad_pedal_common.ipc_watchdog import start_kicad_watchdog

    _watchdog_available = True
except ImportError:
    logger.debug("kicad_pedal_common not available; KiCad watchdog disabled")


def main() -> int:
    logging.basicConfig(level=logging.INFO)

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    # KiCad may or may not add lib/ automatically; insert it defensively.
    lib_dir = os.path.join(plugin_dir, "lib")
    if os.path.isdir(lib_dir) and lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)

    socket_path = os.getenv("KICAD_API_SOCKET") or os.getenv("KICAD_IPC_SOCKET")
    token = os.getenv("KICAD_API_TOKEN")

    if not socket_path:
        logger.error("KICAD_API_SOCKET not set — requires KiCad 9+ with IPC support.")
        return 1

    try:
        from kipy import KiCad

        kicad = KiCad(socket_path=socket_path, kicad_token=token)
        board = kicad.get_board()
        logger.info("Connected: board=%s", board.name)
    except Exception:
        logger.exception("Failed to connect to KiCad IPC")
        return 1

    try:
        import wx
    except Exception:
        logger.exception("Cannot import wx")
        return 1

    app = wx.GetApp() or wx.App(False)

    # Resolve the .kicad_pcb path from the kipy board object.
    board_path = _get_board_path(board)
    if not board_path:
        wx.MessageBox(
            "Cannot determine board file path.\nSave the project first.",
            "Manifest Creator",
            wx.OK | wx.ICON_ERROR,
        )
        return 1

    # Ask user where to save the manifest zip.
    default_name = os.path.splitext(os.path.basename(board_path))[0] + ".manifest.zip"
    default_dir = os.path.dirname(board_path)
    with wx.FileDialog(
        None,
        "Save manifest as…",
        defaultDir=default_dir,
        defaultFile=default_name,
        wildcard="Manifest ZIP (*.manifest.zip)|*.manifest.zip",
        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
    ) as file_dlg:
        if file_dlg.ShowModal() != wx.ID_OK:
            return 0
        output_path = file_dlg.GetPath()

    from manifest_creator.log_dialog import LogDialog
    from manifest_creator.log_writer import LogWriter
    from manifest_creator.packager import create_manifest_zip

    # kicad-cli path comes from the KiCad process if available.
    kicad_cli = getattr(kicad, "kicad_cli_path", None) or None

    log_lines = []

    def _log(msg: str) -> None:
        log_lines.append(msg)

    try:
        with LogWriter(output_path) as writer:

            def _combined(msg: str) -> None:
                _log(msg)
                writer(msg)

            create_manifest_zip(
                board=board,
                board_path=board_path,
                output_path=output_path,
                version="1.0.0",
                kicad_cli=kicad_cli,
                log=_combined,
            )
    except Exception as exc:
        log_lines.append("ERROR: {}".format(exc))
        logger.exception("create_manifest_zip failed")

    log_dlg = LogDialog(None, title="Manifest Export Log")
    for line in log_lines:
        log_dlg._append_and_scroll(line)

    if _watchdog_available:
        start_kicad_watchdog(
            kicad,
            on_exit=lambda: wx.CallAfter(log_dlg.EndModal, wx.ID_CANCEL),
        )

    log_dlg.ShowModal()
    log_dlg.Destroy()

    return 0


def _get_board_path(board) -> str:
    """Return the absolute path to the board .kicad_pcb file.

    kipy board.name may be a bare filename; resolve via the project path
    if needed (same approach as kicad-build-doc-plugin).
    """
    name = board.name
    if name and os.path.isabs(name) and os.path.exists(name):
        return name
    try:
        project_dir = board.get_project().path
        if project_dir:
            candidate = os.path.join(project_dir, os.path.basename(name))
            if os.path.exists(candidate):
                return candidate
    except Exception:
        pass
    # Last resort: check current working directory
    if name:
        cwd_candidate = os.path.join(os.getcwd(), os.path.basename(name))
        if os.path.exists(cwd_candidate):
            return cwd_candidate
    return ""


if __name__ == "__main__":
    sys.exit(main())
