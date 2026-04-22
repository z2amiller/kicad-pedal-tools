"""Scrolling log dialog for manifest export progress."""

from __future__ import annotations

from typing import List, Optional

import wx


class LogBuffer:
    """Pure-Python log buffer with no wx dependency — testable without KiCad."""

    def __init__(self) -> None:
        self._lines: List[str] = []

    def append(self, message: str) -> None:
        self._lines.append(message)

    def get_text(self) -> str:
        return "\n".join(self._lines)


class LogDialog(wx.Dialog):
    """Modal dialog with scrolling log output and copy-to-clipboard."""

    def __init__(self, parent, title: str = "Manifest Export Log") -> None:
        super().__init__(
            parent,
            title=title,
            size=(600, 400),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        self._buffer = LogBuffer()

        self._log_ctrl = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL,
        )
        self._log_ctrl.SetFont(
            wx.Font(
                9,
                wx.FONTFAMILY_TELETYPE,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )

        copy_btn = wx.Button(self, label="Copy to Clipboard")
        close_btn = wx.Button(self, wx.ID_CLOSE, label="Close")

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(copy_btn, 0, wx.RIGHT, 8)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(close_btn, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._log_ctrl, 1, wx.EXPAND | wx.ALL, 8)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetSizer(sizer)

        copy_btn.Bind(wx.EVT_BUTTON, self._on_copy)
        close_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        self.Bind(wx.EVT_CLOSE, lambda e: self.EndModal(wx.ID_CLOSE))

    def append_log(self, message: str) -> None:
        """Append a line to the log (thread-safe via wx.CallAfter)."""
        wx.CallAfter(self._append_and_scroll, message)

    def _append_and_scroll(self, message: str) -> None:
        self._buffer.append(message)
        self._log_ctrl.AppendText(message + "\n")

    def append_warning(self, message: str) -> None:
        """Append a WARNING-prefixed line."""
        self.append_log("WARNING: " + message)

    def append_error(self, message: str) -> None:
        """Append an ERROR-prefixed line."""
        self.append_log("ERROR: " + message)

    def _on_copy(self, event: Optional[wx.Event]) -> None:
        text = self.get_log_text()
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()

    def get_log_text(self) -> str:
        """Return all logged text as a single string."""
        return self._buffer.get_text()
