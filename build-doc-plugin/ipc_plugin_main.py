"""IPC plugin entry point for KiCad 9+.

Reads KICAD_API_SOCKET and KICAD_API_TOKEN from environment variables,
connects to the running KiCad instance via kipy, then opens the build
document dialog.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile

logger = logging.getLogger(__name__)

_LOCK_FILE = os.path.join(tempfile.gettempdir(), "kicad-builddoc.lock")
_WX_APP = None


def _acquire_instance_lock() -> bool:
    """Return True if this is the only running instance.

    Uses a PID file. Stale locks (dead PID) are silently replaced.
    """
    if os.path.exists(_LOCK_FILE):
        try:
            with open(_LOCK_FILE) as fh:
                pid = int(fh.read().strip())
            os.kill(pid, 0)  # signal 0 = existence check, no signal sent
            return False  # process alive — another instance is running
        except (ValueError, ProcessLookupError):
            pass  # stale lock: bad PID or process gone
        except PermissionError:
            return False  # process alive but owned by another user
    try:
        with open(_LOCK_FILE, "w") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass  # can't write lock; don't block the user
    return True


def _release_instance_lock() -> None:
    try:
        os.unlink(_LOCK_FILE)
    except OSError:
        pass


def _ensure_wx_app():
    global _WX_APP
    try:
        import wx
    except Exception:
        logger.exception("Cannot import wx")
        return None, False
    app = wx.GetApp()
    if app is not None:
        return app, False
    _WX_APP = wx.App(None)
    return _WX_APP, True


def main() -> int:
    logging.basicConfig(level=logging.INFO)

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    socket_path = os.getenv("KICAD_API_SOCKET") or os.getenv("KICAD_IPC_SOCKET")
    token = os.getenv("KICAD_API_TOKEN")

    if not socket_path:
        logger.error("KICAD_API_SOCKET not set — this plugin requires KiCad 9+ with IPC support.")
        return 1

    try:
        from kipy import KiCad
        from kicad_pedal_common.ipc_watchdog import wait_for_kicad

        kicad = KiCad(socket_path=socket_path, kicad_token=token)

        if not wait_for_kicad(kicad):
            logger.error("Cannot connect to KiCad IPC at %s", socket_path)
            return 1

        board = kicad.get_board()
        logger.info("Connected: board=%s", board.name)

        from cli_utils import set_kicad_cli_path
        set_kicad_cli_path(getattr(kicad, "kicad_cli_path", None))
    except Exception:
        logger.exception("Failed to connect to KiCad IPC")
        return 1

    app, created_app = _ensure_wx_app()
    if app is None:
        return 1

    if not _acquire_instance_lock():
        import wx

        wx.MessageBox(
            "Build Document Generator is already running.\n"
            "Close the existing window before opening a new one.",
            "Already Running",
            wx.OK | wx.ICON_INFORMATION,
        )
        return 0

    manager = None
    try:
        import wx

        from build_doc_dialog import BuildDocDialog
        from kicad_pedal_common.board_adapter import KipyBoardAdapter
        from kicad_pedal_common.ipc_manager import KiCadIPCManager, SerializedBoardAdapter
        from kicad_pedal_common.ipc_watchdog import start_kicad_watchdog

        # All kipy calls go through a single worker thread — the pynng Req0
        # socket is not thread-safe and KiCad serializes requests on its UI
        # thread anyway, so there is no benefit to concurrent access.
        manager = KiCadIPCManager(ping_fn=kicad.ping)
        inner = KipyBoardAdapter(board)
        adapter = SerializedBoardAdapter(inner, manager)

        dlg = BuildDocDialog(None, board, adapter=adapter)

        # Watchdog calls manager.ping() which goes through the queue,
        # keeping all IPC traffic on the worker thread.
        start_kicad_watchdog(
            manager,
            on_exit=lambda: wx.CallAfter(dlg.EndModal, wx.ID_CANCEL),
            name="builddoc-watchdog",
        )

        dlg.ShowModal()
        dlg.Destroy()
    except Exception:
        logger.exception("Dialog error")
        return 1
    finally:
        _release_instance_lock()
        if manager is not None:
            manager.shutdown()

    if created_app:
        app.MainLoop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
