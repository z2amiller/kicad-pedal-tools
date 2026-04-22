"""Write log messages to a file alongside the output zip."""

from __future__ import annotations

import datetime
import pathlib


class LogWriter:
    """Writes log lines to a file; compatible with the packager log= callback."""

    def __init__(self, output_path: str) -> None:
        p = pathlib.Path(output_path)
        log_path = p.parent / (p.name.split(".")[0] + ".log")
        self._file = open(str(log_path), "w", encoding="utf-8")
        self._write(
            "=== Manifest export log: {} ===".format(
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )

    def _write(self, line: str) -> None:
        self._file.write(line + "\n")
        self._file.flush()

    def __call__(self, message: str) -> None:
        """Callable interface — pass as log= to create_manifest_zip."""
        self._write(message)

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "LogWriter":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
