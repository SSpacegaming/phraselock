"""Monitor enumeration and selection for the lock overlay.

The Windows calls live in list_monitors(); everything else is plain Python so
it can be unit-tested without Windows or a display.
"""

PRIMARY = "primary"
ALL = "all"


def list_monitors():
    """Return connected monitors, ordered left-to-right then top-to-bottom.

    Each item: {"device", "x", "y", "w", "h", "primary"}.
    "device" is the Windows display name (for example r"\\\\.\\DISPLAY2").
    Returns [] if enumeration fails (callers then keep the old behaviour).
    """
    try:
        import win32api
        out = []
        for hmon, _hdc, _rect in win32api.EnumDisplayMonitors(None, None):
            info = win32api.GetMonitorInfo(hmon)
            left, top, right, bottom = info["Monitor"]
            out.append({
                "device": info.get("Device", ""),
                "x": left, "y": top,
                "w": right - left, "h": bottom - top,
                "primary": bool(info.get("Flags", 0) & 1),  # MONITORINFOF_PRIMARY
            })
        out.sort(key=lambda m: (m["x"], m["y"]))
        return out
    except Exception:
        return []


def resolve_monitor(choice, monitors=None):
    """Pick the monitor for the config value *choice*.

    choice: "primary" (default) or a device name stored by the settings panel.
    Falls back to the primary monitor when the chosen one is no longer
    connected, and to None when no monitor information is available at all
    (callers then use the old single-screen behaviour).
    """
    if monitors is None:
        monitors = list_monitors()
    if not monitors:
        return None
    primary = next((m for m in monitors if m["primary"]), monitors[0])
    choice = (choice or PRIMARY).strip()
    if choice == PRIMARY:
        return primary
    return next((m for m in monitors if m["device"] == choice), primary)


def choices_from_cfg(cfg):
    """Return the list of chosen screens from a config dict.

    New key: "lock_screens" (list of "primary" / "all" / device names).
    Old key: "lock_screen" (single string) is still understood.
    """
    raw = cfg.get("lock_screens")
    if raw is None:
        raw = cfg.get("lock_screen", PRIMARY)
    if isinstance(raw, str):
        raw = [raw]
    out = [str(c).strip() for c in (raw or []) if str(c).strip()]
    return out or [PRIMARY]


def resolve_lock_monitors(choices, monitors=None):
    """Return (panel_monitor, cover_monitors) for the chosen screens.

    "all" selects every connected monitor. Choices that are no longer
    connected are skipped; if nothing is left the primary screen is used.
    The phrase panel goes on the primary screen when it is selected,
    otherwise on the left-most selected screen; the others get cover windows.
    Returns (None, []) when no monitor information is available.
    """
    if monitors is None:
        monitors = list_monitors()
    if not monitors:
        return None, []
    primary = next((m for m in monitors if m["primary"]), monitors[0])
    if isinstance(choices, str):
        choices = [choices]
    choices = [str(c).strip() for c in (choices or [])] or [PRIMARY]

    if ALL in choices:
        picked = list(monitors)
    else:
        picked = []
        for c in choices:
            if c == PRIMARY:
                m = primary
            else:
                m = next((x for x in monitors if x["device"] == c), None)
            if m is not None and m not in picked:
                picked.append(m)
        if not picked:
            picked = [primary]

    picked.sort(key=lambda m: (m["x"], m["y"]))
    panel = primary if primary in picked else picked[0]
    return panel, [m for m in picked if m is not panel]


def monitors_signature(monitors=None):
    """Hashable snapshot of the layout, to detect plug/unplug/rearrange."""
    if monitors is None:
        monitors = list_monitors()
    return tuple((m["device"], m["x"], m["y"], m["w"], m["h"], m["primary"]) for m in monitors)


def monitor_label(m, number):
    """Human label such as 'Screen 2 - 1920x1080 (primary)'."""
    tag = " (primary)" if m["primary"] else ""
    return f"Screen {number} - {m['w']}x{m['h']}{tag}"
