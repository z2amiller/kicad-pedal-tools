"""KiCadIPCManager — serializes all kipy IPC calls through a single worker thread.

Background
----------
kipy's ``KiCadClient`` uses a pynng ``Req0`` socket.  The NNG ``REQ0``
protocol allows only one in-flight request at a time; concurrent calls from
multiple threads produce ``NNG_ESTATE`` errors or silent data corruption.
KiCad itself also processes all API requests on its UI thread, so there is no
throughput benefit to concurrent connections.  The recommended architecture
(per the KiCad IPC API docs) is a single connection with sequential requests
and caller-side retry.

This module provides two classes:

``KiCadIPCManager``
    Owns a single background worker thread.  Any callable submitted via
    :meth:`submit` runs on that thread — serializing all IPC traffic — with
    automatic retry + exponential backoff on transient errors.

``SerializedBoardAdapter``
    A :class:`~kicad_pedal_common.board_adapter.BoardAdapter` wrapper that
    delegates every IPC-touching method through a ``KiCadIPCManager``.
    Pure-data accessors (``get_board_path``, ``get_pad_centroid_offset``) are
    passed straight through without queuing.

Python 3.9 compatible.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, List, Optional, Tuple

from kicad_pedal_common.board_adapter import BoardAdapter, BBoxCenter, FootprintData

logger = logging.getLogger(__name__)

_SENTINEL = object()  # signals the worker to stop


class KiCadIPCManager:
    """Serialize kipy IPC calls through a dedicated worker thread.

    Args:
        ping_fn: Zero-argument callable that pings KiCad (typically
            ``kicad.ping`` where *kicad* is a ``kipy.KiCad`` instance).
            Used by :meth:`ping` so the watchdog can route its liveness
            checks through the same serialized channel.
        max_retries: Number of attempts before propagating an exception.
        retry_delay_s: Seconds to wait between retry attempts.
        call_timeout_s: Maximum seconds to wait for a queued call to
            complete before raising :class:`TimeoutError`.

    Example::

        manager = KiCadIPCManager(ping_fn=kicad.ping)
        adapter = SerializedBoardAdapter(KipyBoardAdapter(board), manager)

        start_kicad_watchdog(manager, on_exit=lambda: wx.CallAfter(dlg.EndModal, wx.ID_CANCEL))
        dlg = BuildDocDialog(None, board, adapter=adapter)
        dlg.ShowModal()
        manager.shutdown()
    """

    def __init__(
        self,
        ping_fn: Optional[Callable[[], None]] = None,
        max_retries: int = 3,
        retry_delay_s: float = 0.4,
        call_timeout_s: float = 30.0,
    ) -> None:
        self._ping_fn = ping_fn
        self._max_retries = max_retries
        self._retry_delay = retry_delay_s
        self._call_timeout = call_timeout_s
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._worker, name="kicad-ipc", daemon=True
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        fn: Callable,
        *args: Any,
        _retries: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        """Execute ``fn(*args, **kwargs)`` on the IPC thread and return the result.

        Retries up to *max_retries* times (or *_retries* if given) on any
        exception, with *retry_delay_s* between attempts.  Blocks the calling
        thread until the call completes or *call_timeout_s* elapses.

        Args:
            fn: Callable to execute on the IPC worker thread.
            *args: Positional arguments forwarded to *fn*.
            _retries: Override the instance-level *max_retries* for this call
                only.  Pass ``1`` to execute exactly once without retrying.
            **kwargs: Keyword arguments forwarded to *fn*.

        Raises:
            TimeoutError: If the worker does not respond within the timeout.
            Exception: The last exception raised by *fn* after all retries.
        """
        retries = _retries if _retries is not None else self._max_retries
        evt = threading.Event()
        holder: List[Any] = [None, None, retries]  # [result, exception, retries]
        self._queue.put((fn, args, kwargs, evt, holder))
        if not evt.wait(self._call_timeout):
            raise TimeoutError(
                f"KiCad IPC call timed out after {self._call_timeout:.0f}s"
            )
        exc = holder[1]
        if exc is not None:
            raise exc
        return holder[0]

    def ping(self) -> None:
        """Ping KiCad — safe to call from any thread (routed through the queue).

        Uses a single attempt (no retry) so that a dead socket is detected
        quickly without the 400 ms × N retry delay.

        This is intentionally compatible with the *kicad* argument expected by
        :func:`~kicad_pedal_common.ipc_watchdog.start_kicad_watchdog`, so you
        can pass the manager directly as the first argument.
        """
        if self._ping_fn is None:
            return
        self.submit(self._ping_fn, _retries=1)

    def shutdown(self) -> None:
        """Stop the worker thread.  Call this when the plugin is closing."""
        self._queue.put(_SENTINEL)

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                logger.debug("kicad-ipc worker shutting down")
                return

            fn, args, kwargs, evt, holder = item
            max_retries = holder[2]  # per-call override set by submit()
            last_exc: Optional[Exception] = None

            for attempt in range(max_retries):
                try:
                    holder[0] = fn(*args, **kwargs)
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries - 1:
                        logger.debug(
                            "IPC call %s failed (attempt %d/%d): %s — retrying",
                            getattr(fn, "__name__", repr(fn)),
                            attempt + 1,
                            max_retries,
                            exc,
                        )
                        time.sleep(self._retry_delay)
                    else:
                        logger.warning(
                            "IPC call %s failed after %d attempts: %s",
                            getattr(fn, "__name__", repr(fn)),
                            max_retries,
                            exc,
                        )

            if last_exc is not None:
                holder[1] = last_exc

            evt.set()


class SerializedBoardAdapter(BoardAdapter):
    """A :class:`BoardAdapter` that routes IPC-touching calls through a manager.

    Methods that make kipy/IPC calls are submitted to the
    :class:`KiCadIPCManager` worker thread.  Pure-data accessors
    (``get_board_path``, ``get_pad_centroid_offset``) operate on already-
    fetched in-memory objects and bypass the queue entirely.

    Args:
        inner: The underlying :class:`BoardAdapter` (e.g. ``KipyBoardAdapter``).
        manager: The :class:`KiCadIPCManager` that owns the IPC worker thread.
    """

    def __init__(self, inner: BoardAdapter, manager: KiCadIPCManager) -> None:
        self._inner = inner
        self._mgr = manager

    # IPC-touching — routed through manager

    def get_footprints(self) -> list:
        return self._mgr.submit(self._inner.get_footprints)

    def get_item_bounding_box(
        self, fp_data: FootprintData
    ) -> Optional[BBoxCenter]:
        return self._mgr.submit(self._inner.get_item_bounding_box, fp_data)

    def get_drill_holes(self) -> list:
        return self._mgr.submit(self._inner.get_drill_holes)

    def get_board_bounding_box(self) -> Optional[Tuple[float, float, float, float]]:
        return self._mgr.submit(self._inner.get_board_bounding_box)

    # Pure-data — bypass queue

    def get_board_path(self) -> str:
        return self._inner.get_board_path()

    def get_pad_centroid_offset(
        self, fp_data: FootprintData
    ) -> Tuple[float, float]:
        # Accesses already-fetched protobuf fields — no live IPC call.
        return self._inner.get_pad_centroid_offset(fp_data)
