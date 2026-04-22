"""Helpers for working with FootprintData objects from BoardAdapter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

_WEBVIEW_AVAILABLE: Optional[bool] = None


def check_webview() -> bool:
    """Return True if wx.html2 WebView is available (cached after first call)."""
    global _WEBVIEW_AVAILABLE
    if _WEBVIEW_AVAILABLE is None:
        try:
            import wx.html2  # noqa: F401

            _WEBVIEW_AVAILABLE = True
        except Exception:
            _WEBVIEW_AVAILABLE = False
    return _WEBVIEW_AVAILABLE


@dataclass
class ControlEntry:
    ref: str
    label: str
    value: str


@dataclass
class Controls:
    external: List[ControlEntry]
    internal: List[ControlEntry]


def safe_get_footprints(adapter, log: Optional[Callable] = None) -> List:
    """Return adapter.get_footprints() as a list, or [] on error."""
    try:
        return list(adapter.get_footprints())
    except Exception as exc:
        if log:
            log(f"  Warning: could not retrieve footprints: {exc}")
        return []


def get_board_path(adapter) -> str:
    """Return the full absolute path to the board .kicad_pcb file."""
    try:
        return adapter.get_board_path()
    except Exception:
        return ""


def get_field(fp_data, name: str) -> str:
    """Return the value of a footprint field by name (case-insensitive), or ''."""
    try:
        return fp_data.fields.get(name.lower(), "")
    except Exception:
        return ""


def get_fp_id(fp_data) -> str:
    """Return 'LibNickname:LibItemName' for a footprint."""
    try:
        return fp_data.footprint_id
    except Exception:
        return ""


def ref_sort_key(ref: str) -> Tuple[str, int]:
    """Sort key that orders references alphabetically by prefix then numerically."""
    m = re.match(r"([A-Za-z_]+)(\d*)", ref)
    prefix = m.group(1).upper() if m else ref
    num = int(m.group(2)) if m and m.group(2) else 0
    return (prefix, num)


def friendly_footprint_type(ref: str, fp_name: str) -> str:
    """Map a reference designator prefix to a human-friendly component type string."""
    prefix = re.match(r"[A-Za-z_]+", ref)
    p = prefix.group(0).upper() if prefix else ""
    mapping = {
        "R": "Resistor, 1/4W",
        "C": "Capacitor",
        "D": "Diode",
        "Q": "Transistor",
        "U": "IC",
        "IC": "IC",
        "L": "Inductor",
        "SW": "Switch",
        "RV": "Potentiometer",
        "J": "Connector / Jack",
        "LED": "LED",
        "T": "Transformer",
        "F": "Fuse",
        "FB": "Ferrite Bead",
        "X": "Crystal / Oscillator",
        "Y": "Crystal",
        "TP": "Test Point",
        "CLR": "Resistor, 1/4W",
        "TRIM": "Trimmer potentiometer",
    }
    return mapping.get(p, fp_name or "Component")


_EXCLUDE_ALL_RE = re.compile(r"^(D|LED)\d*$", re.IGNORECASE)
_EXCLUDE_INTERNAL_RE = re.compile(r"^(D|LED|TP)\d*$", re.IGNORECASE)

# Footprint library prefixes that indicate LED/diode indicators regardless of ref prefix.
# Catches SMD LEDs whose refs don't follow D*/LED* convention.
_LED_LIBRARY_RE = re.compile(r"^(LED_SMD|LED_THT|Diode_SMD|Diode_THT)", re.IGNORECASE)


def _is_led_footprint(fp_data) -> bool:
    try:
        library = fp_data.footprint_id.split(":")[0]
        return bool(_LED_LIBRARY_RE.match(library))
    except Exception:
        return False


def extract_controls(adapter, external_ids: set) -> Controls:
    """Return Controls with external and internal ControlEntry lists.

    External = footprint ID in external_ids; internal = everything else
    with a Control field.

    Global exclusions (external and internal): D*, LED* (diodes/LEDs).
    Internal-only additional exclusions: TP* (test points), single-pad
    footprints, and any footprint whose ref looks like an LED indicator.
    """
    external: List[ControlEntry] = []
    internal: List[ControlEntry] = []
    seen: set = set()

    for fp_data in safe_get_footprints(adapter):
        ref = fp_data.ref
        if ref.startswith("~") or ref in ("REF**", ""):
            continue
        if _EXCLUDE_ALL_RE.match(ref) or _is_led_footprint(fp_data):
            continue
        label = get_field(fp_data, "Control")
        if not label or label in seen:
            continue
        seen.add(label)

        entry = ControlEntry(ref=ref, label=label, value=fp_data.value)
        if fp_data.footprint_id in external_ids:
            external.append(entry)
        elif not _EXCLUDE_INTERNAL_RE.match(ref) and fp_data.pad_count > 1:
            internal.append(entry)

    external.sort(key=lambda c: ref_sort_key(c.ref))
    internal.sort(key=lambda c: ref_sort_key(c.ref))
    return Controls(external=external, internal=internal)
