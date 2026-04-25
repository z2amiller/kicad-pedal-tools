"""IPC watchdog: monitor KiCad liveness and shut down plugin on disconnect.

Usage::

    from kicad_pedal_common.ipc_watchdog import start_kicad_watchdog, wait_for_kicad

    # Block until KiCad is reachable (or timeout)
    if not wait_for_kicad(kicad, timeout_s=8.0):
        logger.error("Cannot connect to KiCad")
        return 1

    # Start background thread that calls on_exit() if KiCad disappears
    start_kicad_watchdog(kicad, on_exit=lambda: dlg.EndModal(wx.ID_CANCEL))

Both functions are Python 3.9-compatible and do not require wx or kipy at
import time — imports happen lazily inside the functions.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _kipy_transient_exceptions() -> tuple:
    """Return a tuple of kipy connection-error types for use in ``except``.

    Falls back to an empty tuple if kipy is unavailable or the error classes
    are not real exception types (e.g. stubbed out in a test environment).
    """
    try:
        from kipy.errors import ApiError
        from kipy.errors import ConnectionError as KiPyConnectionError

        # Validate that we got actual exception classes, not mocks
        if not (isinstance(ApiError, type) and isinstance(KiPyConnectionError, type)):
            return ()
        return (ApiError, KiPyConnectionError)
    except (ImportError, AttributeError):
        return ()


def _kipy_disconnect_exceptions() -> tuple:
    """Return exception types that indicate KiCad has terminated (not transient).

    ``kipy.errors.ConnectionError`` is the primary signal that the socket is
    gone — it is NOT a subclass of Python's ``OSError`` or
    ``ConnectionRefusedError``, so it must be caught explicitly.
    """
    try:
        from kipy.errors import ConnectionError as KiPyConnectionError

        if isinstance(KiPyConnectionError, type):
            return (KiPyConnectionError,)
    except (ImportError, AttributeError):
        pass
    return ()


def wait_for_kicad(kicad: object, timeout_s: float = 8.0) -> bool:
    """Ping *kicad* repeatedly until it responds or *timeout_s* elapses.

    Returns True if KiCad is reachable, False if the timeout expired.

    *kicad* must expose a ``ping()`` method (a ``kipy.KiCad`` instance).
    ``kipy.errors.ApiError``, ``kipy.errors.ConnectionError``, and ``OSError``
    are treated as transient failures and retried every 200 ms.
    """
    kipy_errors = _kipy_transient_exceptions()
    retryable = kipy_errors + (OSError,)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            kicad.ping()  # type: ignore[union-attr]
            return True
        except retryable:
            time.sleep(0.2)

    # One final attempt after the loop
    try:
        kicad.ping()  # type: ignore[union-attr]
        return True
    except Exception:
        return False


def start_kicad_watchdog(
    kicad: object,
    on_exit: Callable[[], None],
    poll_interval_s: float = 3.0,
    name: Optional[str] = None,
) -> threading.Thread:
    """Start a daemon thread that polls KiCad and calls *on_exit* on disconnect.

    The thread exits after calling *on_exit* once.  It is a daemon thread so
    it will not prevent the process from exiting normally.

    Args:
        kicad: A ``kipy.KiCad`` instance (or any object with a ``ping()``
            method that raises on disconnect).
        on_exit: Zero-argument callable invoked when KiCad is unreachable.
            Typically a ``wx.CallAfter`` wrapper, e.g.
            ``lambda: wx.CallAfter(dlg.EndModal, wx.ID_CANCEL)``.
        poll_interval_s: Seconds between each liveness check (default 3.0).
        name: Optional thread name for debugging.

    Returns:
        The started :class:`threading.Thread`.
    """

    # Build the fatal-disconnect exception tuple once, outside the loop.
    # kipy.errors.ConnectionError is the primary signal; OSError subtypes
    # (FileNotFoundError, ConnectionRefusedError) cover pynng-level failures
    # where the OS error escapes before kipy wraps it.
    fatal = _kipy_disconnect_exceptions() + (
        ConnectionRefusedError,
        FileNotFoundError,
        OSError,
    )

    def _watch() -> None:
        while True:
            time.sleep(poll_interval_s)
            try:
                kicad.ping()  # type: ignore[union-attr]
            except fatal:
                logger.info("KiCad IPC disconnected — calling on_exit")
                on_exit()
                return
            except Exception:
                # Transient or concurrent error (e.g. ApiError, TimeoutError
                # while a board query is in flight); keep watching.
                pass

    thread = threading.Thread(target=_watch, daemon=True, name=name or "kicad-watchdog")
    thread.start()
    return thread
