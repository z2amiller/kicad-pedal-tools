"""Tests for LogBuffer (pure-Python) and LogWriter."""

from __future__ import annotations

from manifest_creator.log_dialog import LogBuffer
from manifest_creator.log_writer import LogWriter


class TestLogBuffer:
    def test_empty_initially(self):
        buf = LogBuffer()
        assert buf.get_text() == ""

    def test_append_single(self):
        buf = LogBuffer()
        buf.append("hello")
        assert "hello" in buf.get_text()

    def test_append_warning_line(self):
        buf = LogBuffer()
        buf.append("WARNING: some issue")
        assert "WARNING:" in buf.get_text()

    def test_append_error_line(self):
        buf = LogBuffer()
        buf.append("ERROR: something failed")
        assert "ERROR:" in buf.get_text()

    def test_multiple_lines(self):
        buf = LogBuffer()
        buf.append("line one")
        buf.append("line two")
        text = buf.get_text()
        assert "line one" in text
        assert "line two" in text

    def test_multiple_lines_joined_by_newline(self):
        buf = LogBuffer()
        buf.append("alpha")
        buf.append("beta")
        buf.append("gamma")
        text = buf.get_text()
        assert "alpha" in text
        assert "beta" in text
        assert "gamma" in text


class TestLogWriter:
    def test_writes_to_log_file(self, tmp_path):
        zip_path = str(tmp_path / "test.manifest.zip")
        with LogWriter(zip_path) as writer:
            writer("first message")
            writer("second message")

        log_path = tmp_path / "test.log"
        assert log_path.exists()
        content = log_path.read_text()
        assert "first message" in content
        assert "second message" in content

    def test_callable_interface(self, tmp_path):
        zip_path = str(tmp_path / "out.manifest.zip")
        writer = LogWriter(zip_path)
        writer("test message")
        writer.close()

        log_path = tmp_path / "out.log"
        assert "test message" in log_path.read_text()

    def test_context_manager(self, tmp_path):
        zip_path = str(tmp_path / "ctx.manifest.zip")
        with LogWriter(zip_path) as writer:
            writer("ctx message")
        log_path = tmp_path / "ctx.log"
        assert log_path.exists()

    def test_header_written_at_creation(self, tmp_path):
        zip_path = str(tmp_path / "header.manifest.zip")
        with LogWriter(zip_path):
            pass
        content = (tmp_path / "header.log").read_text()
        assert "Manifest export log" in content

    def test_log_file_extension_is_log(self, tmp_path):
        zip_path = str(tmp_path / "some.manifest.zip")
        with LogWriter(zip_path) as writer:
            writer("msg")
        assert (tmp_path / "some.log").exists()

    def test_context_manager_closes_file(self, tmp_path):
        zip_path = str(tmp_path / "close.manifest.zip")
        with LogWriter(zip_path) as writer:
            writer("before close")
        content = (tmp_path / "close.log").read_text()
        assert "before close" in content
