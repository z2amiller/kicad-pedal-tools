"""Shared helpers for KiCad IPC plugins.

Python 3.9 compatible — no match/case, no |union syntax, no tomllib.
"""

from __future__ import annotations

import os
import tempfile


def get_board_path(board) -> str:
    """Return the absolute path to the board .kicad_pcb file.

    kipy's board.name may be a bare filename. If it isn't already an absolute
    path on disk, resolve it via board.get_project().path.
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
    if name:
        cwd_candidate = os.path.join(os.getcwd(), os.path.basename(name))
        if os.path.exists(cwd_candidate):
            return cwd_candidate
    return ""


class PluginInstanceLock:
    """PID-file-based single-instance guard for IPC plugins.

    Usage::

        lock = PluginInstanceLock("my-plugin")
        if not lock.acquire():
            # show "already running" message and return
            ...
        try:
            run_plugin()
        finally:
            lock.release()
    """

    def __init__(self, plugin_id: str) -> None:
        safe = plugin_id.replace("/", "_").replace(".", "_")
        self._path = os.path.join(tempfile.gettempdir(), "kicad-{}.lock".format(safe))

    def acquire(self) -> bool:
        """Return True if this process acquired the lock, False if already running."""
        if os.path.exists(self._path):
            try:
                with open(self._path) as fh:
                    pid = int(fh.read().strip())
                os.kill(pid, 0)  # signal 0 = existence check
                return False  # process alive
            except (ValueError, ProcessLookupError):
                pass  # stale lock — dead PID
            except PermissionError:
                return False  # alive, owned by another user
        try:
            with open(self._path, "w") as fh:
                fh.write(str(os.getpid()))
        except OSError:
            pass  # can't write lock; don't block
        return True

    def release(self) -> None:
        try:
            os.unlink(self._path)
        except OSError:
            pass

    def __enter__(self) -> "PluginInstanceLock":
        return self

    def __exit__(self, *_) -> None:  # type: ignore[override]
        self.release()
