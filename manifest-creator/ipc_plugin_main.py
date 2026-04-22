"""IPC plugin entry point for KiCad 9+.

Reads KICAD_API_SOCKET and KICAD_API_TOKEN from the environment, connects
to the running KiCad instance via kipy, then exports a .manifest.zip.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

_PLUGIN_ID = "com.github.z2amiller.manifest-creator"


def main() -> int:
    logging.basicConfig(level=logging.INFO)

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

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

    app = wx.GetApp() or wx.App(False)  # noqa: F841

    from kicad_pedal_common.plugin_utils import PluginInstanceLock

    lock = PluginInstanceLock(_PLUGIN_ID)
    if not lock.acquire():
        wx.MessageBox(
            "Manifest Creator is already running.\n"
            "Close the existing window before opening a new one.",
            "Already Running",
            wx.OK | wx.ICON_INFORMATION,
        )
        return 0

    try:
        return _run(board, kicad)
    except Exception:
        logger.exception("Manifest Creator crashed")
        try:
            wx.MessageBox(
                "Manifest Creator encountered an unexpected error.\n"
                "Check the KiCad scripting console for details.",
                "Manifest Creator Error",
                wx.OK | wx.ICON_ERROR,
            )
        except Exception:
            pass
        return 1
    finally:
        lock.release()


def _run(board, kicad) -> int:
    import threading
    import wx

    from kicad_pedal_common.plugin_utils import get_board_path

    board_path = get_board_path(board)
    if not board_path:
        wx.MessageBox(
            "Cannot determine board file path.\nSave the project first.",
            "Manifest Creator",
            wx.OK | wx.ICON_ERROR,
        )
        return 1

    default_name = os.path.splitext(os.path.basename(board_path))[0] + ".manifest.zip"
    default_dir = os.path.dirname(board_path)
    with wx.FileDialog(
        None,
        "Save manifest as…",
        defaultDir=default_dir,
        defaultFile=default_name,
        wildcard="Manifest ZIP (*.zip)|*.zip",
        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
    ) as file_dlg:
        if file_dlg.ShowModal() != wx.ID_OK:
            return 0
        output_path = file_dlg.GetPath()

    if not output_path.endswith(".manifest.zip"):
        base = output_path
        if base.endswith(".zip"):
            base = base[:-4]
        output_path = base + ".manifest.zip"

    # kicad-cli path: prefer the one reported by the KiCad process.
    kicad_cli = getattr(kicad, "kicad_cli_path", None) or None

    from manifest_creator.log_dialog import LogDialog
    from manifest_creator.log_writer import LogWriter
    from manifest_creator.packager import create_manifest_zip

    log_dlg = LogDialog(None, title="Manifest Export")

    def _worker() -> None:
        """Run the export on a background thread so the UI stays responsive."""
        success = True
        try:
            with LogWriter(output_path) as writer:

                def _log(msg: str) -> None:
                    log_dlg.append_log(msg)
                    writer(msg)

                create_manifest_zip(
                    board=board,
                    board_path=board_path,
                    output_path=output_path,
                    version="1.0.0",
                    kicad_cli=kicad_cli,
                    log=_log,
                )
        except Exception as exc:
            log_dlg.append_log("ERROR: {}".format(exc))
            logger.exception("create_manifest_zip failed")
            success = False

        log_dlg.mark_done(success)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    log_dlg.ShowModal()   # runs wx event loop; CallAfter callbacks fire here
    log_dlg.Destroy()

    return 0


if __name__ == "__main__":
    sys.exit(main())
