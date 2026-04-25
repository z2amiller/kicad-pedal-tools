"""Tests for KiCadIPCManager and SerializedBoardAdapter."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from kicad_pedal_common.board_adapter import BoardAdapter, FootprintData
from kicad_pedal_common.ipc_manager import KiCadIPCManager, SerializedBoardAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(**kwargs) -> KiCadIPCManager:
    """Return a manager with a no-op ping_fn."""
    return KiCadIPCManager(ping_fn=lambda: None, **kwargs)


def _make_fp(**kwargs) -> FootprintData:
    defaults = dict(
        ref="R1",
        value="10k",
        footprint_id="Device:R",
        layer="F",
        pos_x=0.0,
        pos_y=0.0,
        rotation=0.0,
        dnp=False,
        exclude_from_bom=False,
        fields={},
        pad_count=2,
    )
    defaults.update(kwargs)
    return FootprintData(**defaults)


# ---------------------------------------------------------------------------
# KiCadIPCManager
# ---------------------------------------------------------------------------


class TestKiCadIPCManager:
    def test_submit_returns_result(self):
        mgr = _make_manager()
        result = mgr.submit(lambda: 42)
        assert result == 42
        mgr.shutdown()

    def test_submit_propagates_exception_after_retries(self):
        calls = []

        def _fail():
            calls.append(1)
            raise ValueError("boom")

        mgr = KiCadIPCManager(
            ping_fn=lambda: None,
            max_retries=2,
            retry_delay_s=0.0,
        )
        with pytest.raises(ValueError, match="boom"):
            mgr.submit(_fail)
        assert len(calls) == 2  # tried twice
        mgr.shutdown()

    def test_submit_retries_then_succeeds(self):
        call_count = [0]

        def _flaky():
            call_count[0] += 1
            if call_count[0] < 3:
                raise OSError("transient")
            return "ok"

        mgr = KiCadIPCManager(
            ping_fn=lambda: None,
            max_retries=3,
            retry_delay_s=0.0,
        )
        result = mgr.submit(_flaky)
        assert result == "ok"
        assert call_count[0] == 3
        mgr.shutdown()

    def test_submit_passes_args(self):
        mgr = _make_manager()
        result = mgr.submit(lambda x, y: x + y, 3, 4)
        assert result == 7
        mgr.shutdown()

    def test_submit_timeout_raises(self):
        mgr = KiCadIPCManager(
            ping_fn=lambda: None,
            call_timeout_s=0.1,
        )
        evt = threading.Event()

        def _block():
            evt.wait(5)  # blocks until test ends

        with pytest.raises(TimeoutError):
            mgr.submit(_block)
        evt.set()
        mgr.shutdown()

    def test_serializes_concurrent_calls(self):
        """Calls from multiple threads must be executed sequentially."""
        order = []
        lock = threading.Lock()

        def _task(n):
            with lock:
                order.append(("start", n))
            time.sleep(0.01)
            with lock:
                order.append(("end", n))
            return n

        mgr = _make_manager()
        results = []
        errors = []

        def _submit(n):
            try:
                results.append(mgr.submit(_task, n))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_submit, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        mgr.shutdown()

        assert not errors
        assert sorted(results) == list(range(5))

        # No two tasks overlap: every "start N" should be immediately followed
        # by "end N" before the next "start".
        for i in range(0, len(order) - 1, 2):
            tag, n = order[i]
            assert tag == "start"
            assert order[i + 1] == ("end", n)

    def test_ping_calls_ping_fn(self):
        calls = []
        mgr = KiCadIPCManager(ping_fn=lambda: calls.append(1))
        mgr.ping()
        assert len(calls) == 1
        mgr.shutdown()

    def test_ping_no_op_when_ping_fn_is_none(self):
        mgr = KiCadIPCManager(ping_fn=None)
        mgr.ping()  # should not raise
        mgr.shutdown()

    def test_ping_does_not_retry_on_failure(self):
        """ping() must propagate immediately without retrying — a failed ping
        means KiCad is dead, and retry delays slow disconnect detection."""
        call_count = [0]

        def _dead_ping():
            call_count[0] += 1
            raise ConnectionRefusedError("socket gone")

        mgr = KiCadIPCManager(
            ping_fn=_dead_ping,
            max_retries=3,  # board ops retry 3×; ping must override to 1
            retry_delay_s=1.0,  # if retry happened, test would be very slow
        )
        with pytest.raises(ConnectionRefusedError):
            mgr.ping()

        assert call_count[0] == 1, "ping() must not retry"
        mgr.shutdown()

    def test_submit_retries_override(self):
        """_retries kwarg overrides instance max_retries for a single call."""
        call_count = [0]

        def _fail():
            call_count[0] += 1
            raise ValueError("nope")

        mgr = KiCadIPCManager(ping_fn=None, max_retries=5, retry_delay_s=0.0)
        with pytest.raises(ValueError):
            mgr.submit(_fail, _retries=2)
        assert call_count[0] == 2
        mgr.shutdown()

    def test_shutdown_stops_worker(self):
        mgr = _make_manager()
        mgr.shutdown()
        # After shutdown, the worker thread should stop (daemon, so process won't
        # hang, but we can verify the thread is no longer alive shortly after).
        mgr._thread.join(timeout=1.0)
        assert not mgr._thread.is_alive()


# ---------------------------------------------------------------------------
# SerializedBoardAdapter
# ---------------------------------------------------------------------------


class TestSerializedBoardAdapter:
    def _make_adapter(self):
        inner = MagicMock(spec=BoardAdapter)
        inner.get_footprints.return_value = []
        inner.get_item_bounding_box.return_value = None
        inner.get_drill_holes.return_value = []
        inner.get_board_bounding_box.return_value = None
        inner.get_board_path.return_value = "/tmp/test.kicad_pcb"
        inner.get_pad_centroid_offset.return_value = (0.0, 0.0)
        mgr = _make_manager()
        return SerializedBoardAdapter(inner, mgr), inner, mgr

    def test_get_footprints_delegates(self):
        adapter, inner, mgr = self._make_adapter()
        inner.get_footprints.return_value = [_make_fp()]
        result = adapter.get_footprints()
        assert len(result) == 1
        inner.get_footprints.assert_called_once()
        mgr.shutdown()

    def test_get_board_bounding_box_delegates(self):
        adapter, inner, mgr = self._make_adapter()
        inner.get_board_bounding_box.return_value = (0.0, 100.0, 0.0, 80.0)
        result = adapter.get_board_bounding_box()
        assert result == (0.0, 100.0, 0.0, 80.0)
        mgr.shutdown()

    def test_get_board_path_bypasses_manager(self):
        """get_board_path is pure-data and must NOT go through the queue."""
        inner = MagicMock(spec=BoardAdapter)
        inner.get_board_path.return_value = "/my/board.kicad_pcb"

        # Use a manager whose worker is already shut down — if get_board_path
        # tried to submit to the queue, submit() would time out.
        mgr = KiCadIPCManager(ping_fn=None, call_timeout_s=0.1)
        mgr.shutdown()
        mgr._thread.join(timeout=1.0)

        adapter = SerializedBoardAdapter(inner, mgr)
        result = adapter.get_board_path()
        assert result == "/my/board.kicad_pcb"

    def test_get_pad_centroid_offset_bypasses_manager(self):
        """get_pad_centroid_offset is pure-data and must NOT go through the queue."""
        inner = MagicMock(spec=BoardAdapter)
        inner.get_pad_centroid_offset.return_value = (1.5, -0.5)

        mgr = KiCadIPCManager(ping_fn=None, call_timeout_s=0.1)
        mgr.shutdown()
        mgr._thread.join(timeout=1.0)

        adapter = SerializedBoardAdapter(inner, mgr)
        fp = _make_fp()
        result = adapter.get_pad_centroid_offset(fp)
        assert result == (1.5, -0.5)

    def test_ipc_exception_propagates(self):
        adapter, inner, mgr = self._make_adapter()
        inner.get_footprints.side_effect = RuntimeError("ipc dead")

        mgr2 = KiCadIPCManager(ping_fn=None, max_retries=1, retry_delay_s=0.0)
        adapter2 = SerializedBoardAdapter(inner, mgr2)
        with pytest.raises(RuntimeError, match="ipc dead"):
            adapter2.get_footprints()
        mgr.shutdown()
        mgr2.shutdown()
