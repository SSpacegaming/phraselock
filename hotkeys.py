"""Global hotkey text ("Ctrl+Alt+P") <-> Windows RegisterHotKey values (no Windows needed)."""

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODIFIERS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "windows": MOD_WIN, "super": MOD_WIN,
}

_NAMED_KEYS = {
    "space": 0x20, "pause": 0x13, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
}


def _key_code(name):
    name = name.lower()
    if len(name) == 1 and "a" <= name <= "z":
        return ord(name.upper())
    if len(name) == 1 and "0" <= name <= "9":
        return ord(name)
    if name.startswith("f") and name[1:].isdigit() and 1 <= int(name[1:]) <= 24:
        return 0x70 + int(name[1:]) - 1          # F1 = 0x70
    return _NAMED_KEYS.get(name)


def parse_hotkey(text):
    """Return (modifiers, virtual_key) for text like "Ctrl+Alt+P", or None.

    A usable hotkey has exactly one key and at least one of Ctrl, Alt or Win
    (Shift alone is not enough, so a plain typing key can never be taken over).
    """
    parts = [p.strip() for p in str(text or "").replace(" ", "").split("+") if p.strip()]
    if len(parts) < 2:
        return None
    mods = 0
    key = None
    for part in parts:
        mod = _MODIFIERS.get(part.lower())
        if mod:
            mods |= mod
        elif key is None:
            key = _key_code(part)
            if key is None:
                return None
        else:
            return None
    if key is None or not mods & (MOD_CONTROL | MOD_ALT | MOD_WIN):
        return None
    return mods, key


def normalize_hotkey(text):
    """Canonical spelling ("ctrl + alt+p" -> "Ctrl+Alt+P"), or "" when it is not usable."""
    parsed = parse_hotkey(text)
    if not parsed:
        return ""
    mods, key = parsed
    names = []
    for flag, label in ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win")):
        if mods & flag:
            names.append(label)
    key_name = None
    for name, code in _NAMED_KEYS.items():
        if code == key:
            key_name = {"pageup": "PageUp", "pagedown": "PageDown"}.get(name, name.capitalize())
    if key_name is None:
        if 0x70 <= key <= 0x87:
            key_name = f"F{key - 0x70 + 1}"
        else:
            key_name = chr(key)
    return "+".join(names + [key_name])
