"""Configuration loading/saving, defaults, and scheduling helpers."""

import os
import sys
import json
import unicodedata
from datetime import datetime

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", "."), "PhraseLock")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
LOG_PATH = os.path.join(CONFIG_DIR, "phraselock.log")
STATS_PATH = os.path.join(CONFIG_DIR, "stats.json")
STREAK_PATH = os.path.join(CONFIG_DIR, "streak.json")
MEDIA_CACHE_DIR = os.path.join(CONFIG_DIR, "media_cache")

# Entry point used to relaunch PhraseLock with --lock / --focus-session.
ENTRY_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phrase_lock.py")


def self_command(*args):
    """Return (command, cwd) that starts PhraseLock again with extra arguments.

    Packaged build: PhraseLock.exe itself. From source: python phrase_lock.py.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, *args], os.path.dirname(sys.executable)
    return [sys.executable, ENTRY_SCRIPT, *args], os.path.dirname(ENTRY_SCRIPT)


DEFAULT_CONFIG = {
    "enabled": True,
    "phrases": ["My name is XXX, I wish to access my PC"],
    "phrases_file": "",
    "title": "Conditional unlock",
    "background_image": "",
    "panel_color": "#1a1a2e",
    "panel_opacity": 100,
    "required_repeats": 1,
    "reset_on_error": True,
    "disable_paste": False,
    "case_insensitive": False,
    "min_delay_seconds": 0,
    "play_sound": False,
    "schedule_enabled": False,
    "schedule_days": [0, 1, 2, 3, 4, 5, 6],
    "schedule_start": "00:00",
    "schedule_end": "23:59",
    "emergency_password_salt": "",
    "emergency_password_hash": "",
    "emergency_password_iterations": 210000,
    "auto_protection": False,
    "daily_goal": 1,
    "xp": 0,
    "difficulty": "all",
    "difficulty_weighting": True,
    "max_attempts": 0,
    "lockout_seconds": 15,
    "strict_mode": False,
    "theme": "Cyber Red",
    "font_family": "Consolas",
    "ui_scale": 100,
    "scanlines": True,
    "glow_effect": True,
    "glitch_effect": False,
    "sound_on_error": False,
    "success_sound": "",
    "error_sound": "",
    "sound_volume": 70,
    "focus_session_enabled": False,
    "focus_session_minutes": 45,
    "focus_block_apps": [],
    "idle_lock_enabled": False,
    "idle_lock_minutes": 30,
    "manual_lock_hotkey": "",
}


def log(message):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            from datetime import datetime as _dt
            f.write(f"[{_dt.now().isoformat(timespec='seconds')}] {message}\n")
    except Exception:
        pass


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update(cfg)
        phrases = merged.get("phrases") or []
        phrases = [p for p in phrases if isinstance(p, str) and p.strip()]
        if not phrases:
            legacy = cfg.get("phrase")
            if isinstance(legacy, str) and legacy.strip():
                phrases = [legacy.strip()]
            else:
                phrases = list(DEFAULT_CONFIG["phrases"])
        merged["phrases"] = phrases
        return merged
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def within_schedule(cfg, now=None):
    """Return whether *now* (default: datetime.now()) is inside the schedule.

    Handles overnight windows across midnight, including the previous day's
    selection (e.g. Monday 23:00 -> Tuesday 01:00).
    """
    if not cfg.get("schedule_enabled"):
        return True
    days = set(cfg.get("schedule_days") or list(range(7)))
    if now is None:
        now = datetime.now()
    start_raw = cfg.get("schedule_start") or "00:00"
    end_raw = cfg.get("schedule_end") or "23:59"
    try:
        start_t = datetime.strptime(start_raw, "%H:%M").time()
        end_t = datetime.strptime(end_raw, "%H:%M").time()
    except Exception:
        return True

    now_t = now.time()
    if start_t <= end_t:
        return now.weekday() in days and start_t <= now_t <= end_t

    if now_t >= start_t:
        return now.weekday() in days
    if now_t <= end_t:
        return ((now.weekday() - 1) % 7) in days
    return False


def _normalize(text, case_insensitive):
    text = text.strip()
    if case_insensitive:
        text = text.lower()
        text = "".join(
            c for c in unicodedata.normalize("NFKD", text)
            if not unicodedata.combining(c)
        )
    return text


def _contrast_colors(panel_color):
    try:
        h = panel_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    except Exception:
        luminance = 0.0
    if luminance > 0.6:
        return {"primary": "#111111", "secondary": "#444444"}
    return {"primary": "white", "secondary": "#aaaaaa"}


def _blend_hex(foreground, background="#111111", alpha=1.0):
    try:
        fg = foreground.lstrip("#")
        bg = background.lstrip("#")
        if len(fg) == 3: fg = "".join(c * 2 for c in fg)
        if len(bg) == 3: bg = "".join(c * 2 for c in bg)
        fr, fg_, fb = (int(fg[i:i+2], 16) for i in (0, 2, 4))
        br, bg_, bb = (int(bg[i:i+2], 16) for i in (0, 2, 4))
        a = max(0.0, min(1.0, float(alpha)))
        r = round(fr * a + br * (1 - a))
        g = round(fg_ * a + bg_ * (1 - a))
        b = round(fb * a + bb * (1 - a))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return background