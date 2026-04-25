"""Tests for kicad_pedal_common.ipc_watchdog."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from kicad_pedal_common.ipc_watchdog import start_kicad_watchdog, wait_for_kicad

# ---------------------------------------------------------------------------
# wait_for_kicad
# ---------------------------------------------------------------------------


class TestWaitForKicad:
    def test_returns_true_when_ping_succeeds_immediately(self):
        kicad = MagicMock()
        kicad.ping.return_value = None
        assert wait_for_kicad(kicad, timeout_s=1.0) is True

    def test_returns_false_when_ping_always_raises_oserror(self):
        kicad = MagicMock()
        kicad.ping.side_effect = OSError("no socket")
        # Use a very short timeout so the test doesn't take 8 s
        assert wait_for_kicad(kicad, timeout_s=0.05) is False

    def test_returns_true_after_transient_failures(self):
        """Ping fails once then succeeds — should return True."""
        kicad = MagicMock()
        call_count = [0]

        def _ping():
            call_count[0] += 1
            if call_count[0] < 2:
                raise OSError("not yet")

        kicad.ping.side_effect = _ping
        assert wait_for_kicad(kicad, timeout_s=1.0) is True

    def test_ping_called_at_least_once(self):
        kicad = MagicMock()
        kicad.ping.return_value = None
        wait_for_kicad(kicad, timeout_s=1.0)
        kicad.ping.assert_called()


# ---------------------------------------------------------------------------
# start_kicad_watchdog
# ---------------------------------------------------------------------------


class TestStartKicadWatchdog:
    def test_returns_daemon_thread(self):
        kicad = MagicMock()
        kicad.ping.return_value = None
        on_exit = MagicMock()
        thread = start_kicad_watchdog(kicad, on_exit=on_exit, poll_interval_s=9999)
        assert isinstance(thread, threading.Thread)
        assert thread.daemon is True
        # Clean up: nothing to do — thread will block on sleep, process exits

    def test_calls_on_exit_when_kicad_disconnects(self):
        """on_exit must be called when ping raises ConnectionRefusedError."""
        kicad = MagicMock()
        kicad.ping.side_effect = ConnectionRefusedError("gone")
        on_exit_called = threading.Event()
        on_exit = lambda: on_exit_called.set()  # noqa: E731

        start_kicad_watchdog(kicad, on_exit=on_exit, poll_interval_s=0.01)
        assert on_exit_called.wait(timeout=2.0), "on_exit was not called within 2 s"

    def test_calls_on_exit_for_file_not_found(self):
        """on_exit must be called when ping raises FileNotFoundError (socket gone)."""
        kicad = MagicMock()
        kicad.ping.side_effect = FileNotFoundError("socket removed")
        on_exit_called = threading.Event()
        on_exit = lambda: on_exit_called.set()  # noqa: E731

        start_kicad_watchdog(kicad, on_exit=on_exit, poll_interval_s=0.01)
        assert on_exit_called.wait(timeout=2.0), "on_exit was not called within 2 s"

    def test_calls_on_exit_for_kipy_connection_error(self):
        """on_exit must be called when ping raises kipy.errors.ConnectionError.

        kipy.errors.ConnectionError is NOT a subclass of OSError — it must be
        caught explicitly or the watchdog silently ignores the disconnect.
        """

        # Create a fake KiPyConnectionError that is NOT an OSError subclass,
        # mirroring the real kipy.errors.ConnectionError hierarchy.
        class FakeKiPyConnectionError(Exception):
            pass

        kicad = MagicMock()
        kicad.ping.side_effect = FakeKiPyConnectionError("kipy socket gone")
        on_exit_called = threading.Event()

        # Patch _kipy_disconnect_exceptions to return our fake class.
        import kicad_pedal_common.ipc_watchdog as _wd

        original = _wd._kipy_disconnect_exceptions

        def _patched():
            return (FakeKiPyConnectionError,)

        _wd._kipy_disconnect_exceptions = _patched
        try:
            start_kicad_watchdog(
                kicad,
                on_exit=lambda: on_exit_called.set(),
                poll_interval_s=0.01,
            )
            assert on_exit_called.wait(timeout=2.0), (
                "on_exit was not called — kipy.errors.ConnectionError not in fatal list"
            )
        finally:
            _wd._kipy_disconnect_exceptions = original

    def test_does_not_call_on_exit_for_transient_errors(self):
        """Generic exceptions (not disconnect errors) must not trigger on_exit."""
        kicad = MagicMock()
        # First call: generic error; second call: success
        call_count = [0]

        def _ping():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("transient")
            # Subsequent calls succeed — watchdog keeps running

        kicad.ping.side_effect = _ping
        on_exit = MagicMock()

        start_kicad_watchdog(kicad, on_exit=on_exit, poll_interval_s=0.01)
        # Give the thread a couple of cycles
        time.sleep(0.1)
        on_exit.assert_not_called()

    def test_on_exit_called_only_once(self):
        """Even with repeated disconnect errors, on_exit is called exactly once."""
        kicad = MagicMock()
        kicad.ping.side_effect = ConnectionRefusedError("gone")
        call_count = [0]

        def _on_exit():
            call_count[0] += 1

        start_kicad_watchdog(kicad, on_exit=_on_exit, poll_interval_s=0.01)
        time.sleep(0.15)  # enough for multiple poll cycles
        assert call_count[0] == 1, "on_exit must be called exactly once"

    def test_custom_thread_name(self):
        kicad = MagicMock()
        kicad.ping.return_value = None
        on_exit = MagicMock()
        thread = start_kicad_watchdog(
            kicad, on_exit=on_exit, poll_interval_s=9999, name="my-watchdog"
        )
        assert thread.name == "my-watchdog"
