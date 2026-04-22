"""Stub KiCad-only modules so plugin code can be imported outside KiCad.

Mocks wx, kipy, and pcbnew at import time so tests run in CI without
a KiCad installation.
"""

import sys
from unittest.mock import MagicMock

# wx is only available inside KiCad's bundled Python environment.
sys.modules.setdefault("wx", MagicMock())

# pcbnew is only available inside KiCad's bundled Python environment.
sys.modules.setdefault("pcbnew", MagicMock())

# kipy is only available inside KiCad's IPC environment.
_kipy = MagicMock()
sys.modules.setdefault("kipy", _kipy)
sys.modules.setdefault("kipy.board", _kipy.board)
sys.modules.setdefault("kipy.proto", _kipy.proto)
sys.modules.setdefault("kipy.proto.common", _kipy.proto.common)
sys.modules.setdefault("kipy.proto.common.v1", _kipy.proto.common.v1)

# Ensure the plugin root is on sys.path so imports resolve.
import os  # noqa: E402

plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if plugin_root not in sys.path:
    sys.path.insert(0, plugin_root)
