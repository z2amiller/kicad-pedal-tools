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
    """Modal dialog with live scrolling log, pulsing progress bar, and copy-to-clipboard.

    Designed for use with a background worker thread:

        dlg = LogDialog(parent)
        thread = threading.Thread(target=worker, args=(dlg.append_log,), daemon=True)
        thread.start()
        dlg.ShowModal()   # runs the wx event loop; CallAfter callbacks fire here
        dlg.Destroy()

    Call ``mark_done(success)`` from the worker thread (via wx.CallAfter) to stop
    the progress pulse and enable the Close button when work is complete.
    """

    def __init__(self, parent, title: str = "Manifest Export Log") -> None:
        super().__init__(
            parent,
            title=title,
            size=(620, 440),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        self._buffer = LogBuffer()
        self._done = False

        # Status label
        self._status_label = wx.StaticText(self, label="Building manifest…")
        font = self._status_label.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        self._status_label.SetFont(font)

        # Pulsing progress gauge
        self._gauge = wx.Gauge(self, range=100, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)

        # Pulse timer — advances the gauge while the worker runs
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda e: self._gauge.Pulse(), self._timer)
        self._timer.Start(80)

        # Log output
        self._log_ctrl = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL,
        )
        self._log_ctrl.SetFont(
            wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        )

        # Buttons — Close disabled until work is done
        self._copy_btn = wx.Button(self, label="Copy to Clipboard")
        self._close_btn = wx.Button(self, wx.ID_CLOSE, label="Close")
        self._close_btn.Disable()

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(self._copy_btn, 0, wx.RIGHT, 8)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._close_btn, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._status_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        sizer.Add(self._gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        sizer.Add(self._log_ctrl, 1, wx.EXPAND | wx.ALL, 8)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetSizer(sizer)

        self._copy_btn.Bind(wx.EVT_BUTTON, self._on_copy)
        self._close_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        # Allow closing via window X only after work is done
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def append_log(self, message: str) -> None:
        """Append a line to the log. Thread-safe — callable from any thread."""
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

    def mark_done(self, success: bool = True) -> None:
        """Call from the worker thread (via wx.CallAfter) when export is complete."""
        wx.CallAfter(self._on_done, success)

    def _on_done(self, success: bool) -> None:
        self._done = True
        self._timer.Stop()
        self._gauge.SetValue(100 if success else 0)
        self._status_label.SetLabel("Done." if success else "Export failed — see log for details.")
        self._close_btn.Enable()
        self._close_btn.SetFocus()

    def _on_close(self, event: wx.CloseEvent) -> None:
        if self._done:
            self.EndModal(wx.ID_CLOSE)
        else:
            # Veto the close while the worker is still running
            event.Veto()

    def _on_copy(self, event: Optional[wx.Event]) -> None:
        text = self.get_log_text()
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()

    def get_log_text(self) -> str:
        """Return all logged text as a single string."""
        return self._buffer.get_text()
