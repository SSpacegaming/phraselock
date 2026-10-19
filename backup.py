"""Export / import of PhraseLock settings and statistics.

Use it to back up your setup or to move it to a new PC. Everything lives in
one JSON file:

    {
      "format": "phraselock-backup",
      "version": 1,
      "exported_at": "2026-10-19T12:00:00",
      "includes_password": true,
      "config": {...},   # settings (config.json)
      "stats":  [...],   # unlock history (stats.json)
      "streak": {...}    # streak, daily goal and XP (streak.json)
    }

Importing never trusts the file blindly: unknown keys are dropped, values
with the wrong type are ignored and numbers are clamped to the same ranges
the Settings window allows. Nothing is written until the whole file has been
validated, and the files being replaced are first copied to ``*.bak``.

The core functions have no UI dependency (so they can be unit-tested); the
``*_dialog`` helpers at the bottom are what the Settings window calls.
"""

import json
import os
import re
import shutil
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from config import CONFIG_PATH, STATS_PATH, STREAK_PATH, DEFAULT_CONFIG, save_json, log

BACKUP_FORMAT = "phraselock-backup"
BACKUP_VERSION = 1
MAX_BACKUP_BYTES = 5 * 1024 * 1024
MAX_STATS_ENTRIES = 500  # same cap as stats.record_stat

PASSWORD_KEYS = (
    "emergency_password_salt",
    "emergency_password_hash",
    "emergency_password_iterations",
)
# Settings that point at files/URLs; a backup can't carry the files themselves.
PATH_KEYS = ("phrases_file", "background_image", "success_sound", "error_sound")

# Same limits as the Settings window.
INT_RANGES = {
    "panel_opacity": (10, 100),
    "required_repeats": (1, 20),
    "min_delay_seconds": (0, 60),
    "daily_goal": (1, 50),
    "max_attempts": (0, 100),
    "lockout_seconds": (1, 300),
    "ui_scale": (75, 150),
    "sound_volume": (0, 100),
    "focus_session_minutes": (1, 240),
    "idle_lock_minutes": (1, 240),
    "xp": (0, 10 ** 12),
    "emergency_password_iterations": (1, 10_000_000),
}

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
HEX_RE = re.compile(r"^[0-9a-fA-F]*$")


class BackupError(Exception):
    """A problem with a backup file, worded for the end user."""


@dataclass
class Backup:
    """A validated backup, ready to be applied."""
    exported_at: str = ""
    config: dict = field(default_factory=dict)
    stats: Optional[list] = None      # None = the file has no stats section
    streak: Optional[dict] = None     # None = the file has no streak section
    warnings: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def _color_ok(text):
    text = (text or "").strip()
    if not text:
        return False
    try:
        from PIL import ImageColor
        ImageColor.getrgb(text)
        return True
    except ImportError:
        return bool(HEX_COLOR_RE.match(text))
    except ValueError:
        return False


def default_backup_name():
    return f"phraselock-backup-{date.today().isoformat()}.json"


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------

def build_backup(config, include_password=True, stats_path=None, streak_path=None):
    """Return the backup as a dict. *config* is the settings dict to save."""
    stats_path = stats_path or STATS_PATH
    streak_path = streak_path or STREAK_PATH

    cfg = {k: v for k, v in config.items() if k in DEFAULT_CONFIG}
    if not include_password:
        for key in PASSWORD_KEYS:
            cfg.pop(key, None)

    stats = _read_json(stats_path, [])
    stats = [s for s in stats if isinstance(s, dict)] if isinstance(stats, list) else []
    streak = _read_json(streak_path, {})
    if not isinstance(streak, dict):
        streak = {}

    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "includes_password": bool(include_password),
        "config": cfg,
        "stats": stats,
        "streak": streak,
    }


def export_backup(path, config, include_password=True, stats_path=None, streak_path=None):
    """Write the backup to *path*. Returns the backup dict that was written."""
    data = build_backup(config, include_password, stats_path, streak_path)
    save_json(path, data)
    return data


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def sanitize_config(raw):
    """Return (clean_settings, warnings). Only known, well-typed keys survive."""
    warnings = []
    clean = {}
    if not isinstance(raw, dict):
        return clean, warnings

    for key, value in raw.items():
        if key not in DEFAULT_CONFIG:
            continue  # unknown/removed setting: ignore silently
        default = DEFAULT_CONFIG[key]

        def reject(why="invalid value"):
            warnings.append(f"Setting '{key}' ignored ({why}).")

        if isinstance(default, bool):
            if not isinstance(value, bool):
                reject()
                continue
        elif isinstance(default, int):
            if not _is_int(value):
                reject()
                continue
            lo, hi = INT_RANGES.get(key, (None, None))
            if lo is not None:
                value = max(lo, min(hi, value))
        elif isinstance(default, str):
            if not isinstance(value, str):
                reject()
                continue
        elif isinstance(default, list):
            if not isinstance(value, list):
                reject()
                continue
            if key == "schedule_days":
                if not value or not all(_is_int(d) and 0 <= d <= 6 for d in value):
                    reject("expected day numbers 0-6")
                    continue
                value = sorted(set(value))
            else:  # phrases, focus_block_apps
                if not all(isinstance(x, str) for x in value):
                    reject("expected a list of text")
                    continue
                value = [x.strip() for x in value if x.strip()]
                if key == "phrases" and not value:
                    reject("no usable phrase")
                    continue

        if key in ("schedule_start", "schedule_end") and not TIME_RE.match(value.strip()):
            reject("expected HH:MM")
            continue
        if key == "panel_color" and not _color_ok(value):
            reject("unknown colour")
            continue
        if key in ("emergency_password_salt", "emergency_password_hash") and not HEX_RE.match(value):
            reject("not a valid hash")
            continue

        clean[key] = value

    # The salt, hash and iteration count only work together. If the backup
    # carries an incomplete set, drop all of it and keep the current password.
    salt = clean.get("emergency_password_salt")
    digest = clean.get("emergency_password_hash")
    if any(key in clean for key in PASSWORD_KEYS):
        complete = salt is not None and digest is not None and bool(salt) == bool(digest)
        if not complete:
            for key in PASSWORD_KEYS:
                clean.pop(key, None)
            warnings.append("Emergency password ignored (incomplete data); your current one is kept.")
        elif digest and "emergency_password_iterations" not in clean:
            # Older configs relied on the default count when none was stored.
            clean["emergency_password_iterations"] = DEFAULT_CONFIG["emergency_password_iterations"]

    for key in PATH_KEYS:
        value = clean.get(key, "")
        if value and not value.lower().startswith(("http://", "https://")) and not os.path.exists(value):
            warnings.append(f"File not found on this PC for '{key}': {value}")

    return clean, warnings


def _clean_stat(entry):
    """Return a safe copy of one unlock record, or None if it is unusable."""
    if not isinstance(entry, dict):
        return None
    stamp = entry.get("timestamp")
    if not isinstance(stamp, str):
        return None
    try:
        datetime.fromisoformat(stamp)
    except ValueError:
        return None
    out = {"timestamp": stamp}
    for key in ("rounds", "duration_seconds"):
        if key in entry:
            if not _is_number(entry[key]):
                return None
            out[key] = entry[key]
    for key in ("first_try", "emergency"):
        out[key] = bool(entry.get(key, False))
    for key in ("wpm", "accuracy"):
        if _is_number(entry.get(key)):
            out[key] = entry[key]
    return out


def sanitize_stats(raw):
    if not isinstance(raw, list):
        return [], []
    cleaned = [c for c in (_clean_stat(e) for e in raw) if c is not None]
    warnings = []
    dropped = len(raw) - len(cleaned)
    if dropped:
        warnings.append(f"{dropped} unreadable unlock record(s) skipped.")
    return cleaned[-MAX_STATS_ENTRIES:], warnings


def sanitize_streak(raw):
    if not isinstance(raw, dict):
        return {}, []
    clean, warnings = {}, []
    for key in ("current_streak", "best_streak", "goal_progress", "xp"):
        if key in raw:
            if _is_int(raw[key]):
                clean[key] = max(0, raw[key])
            else:
                warnings.append(f"Progress value '{key}' ignored.")
    for key in ("last_qualifying_day", "goal_date"):
        if key in raw:
            value = raw[key]
            if value is None and key == "last_qualifying_day":
                clean[key] = None
                continue
            try:
                date.fromisoformat(value)
                clean[key] = value
            except (TypeError, ValueError):
                warnings.append(f"Progress value '{key}' ignored.")
    return clean, warnings


# --------------------------------------------------------------------------
# import
# --------------------------------------------------------------------------

def load_backup(path):
    """Read and validate *path*. Writes nothing. Raises BackupError."""
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise BackupError(f"Cannot open the file: {exc}") from exc
    if size > MAX_BACKUP_BYTES:
        raise BackupError("This file is too large to be a PhraseLock backup.")
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:  # ValueError covers bad JSON/encoding
        raise BackupError(f"This file is not a readable backup: {exc}") from exc

    if not isinstance(data, dict) or data.get("format") != BACKUP_FORMAT:
        raise BackupError("This file is not a PhraseLock backup.")
    version = data.get("version")
    if not _is_int(version) or version < 1:
        raise BackupError("The backup has no valid version number.")
    if version > BACKUP_VERSION:
        raise BackupError(
            "This backup was made by a newer version of PhraseLock. "
            "Update PhraseLock and try again."
        )

    backup = Backup(exported_at=str(data.get("exported_at", "")))
    if "config" in data:
        backup.config, w = sanitize_config(data["config"])
        backup.warnings += w
    if "stats" in data:
        backup.stats, w = sanitize_stats(data["stats"])
        backup.warnings += w
    if "streak" in data:
        backup.streak, w = sanitize_streak(data["streak"])
        backup.warnings += w

    if not backup.config and backup.stats is None and backup.streak is None:
        raise BackupError("This backup contains no settings or statistics.")
    return backup


def apply_backup(backup, config_path=None, stats_path=None, streak_path=None):
    """Replace the current settings/stats with *backup*.

    Settings missing from the backup (for example the emergency password
    when it was exported without it) keep their current value. The files
    being replaced are copied to ``<name>.<timestamp>.bak`` first.
    Returns the list of ``.bak`` files created.
    """
    config_path = config_path or CONFIG_PATH
    stats_path = stats_path or STATS_PATH
    streak_path = streak_path or STREAK_PATH

    current = _read_json(config_path, {})
    if not isinstance(current, dict):
        current = {}

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    saved = []
    try:
        for path in (config_path, stats_path, streak_path):
            if os.path.exists(path):
                dest = f"{path}.{stamp}.bak"
                shutil.copy2(path, dest)
                saved.append(dest)

        if backup.stats is not None:
            save_json(stats_path, backup.stats)
        if backup.streak is not None:
            save_json(streak_path, backup.streak)
        if backup.config:
            save_json(config_path, {**current, **backup.config})
    except OSError as exc:
        hint = f" Your previous files were kept as: {', '.join(saved)}." if saved else ""
        raise BackupError(f"Could not write the imported data: {exc}.{hint}") from exc
    return saved


def describe(backup):
    """Short multi-line summary shown before the import is confirmed."""
    lines = []
    if backup.exported_at:
        lines.append(f"Backup made on: {backup.exported_at.replace('T', ' ')}")
    lines.append(f"Settings: {len(backup.config)} value(s)")
    if backup.stats is not None:
        lines.append(f"Unlock records: {len(backup.stats)}")
    if backup.streak is not None:
        lines.append(
            f"Streak / XP: streak {backup.streak.get('current_streak', 0)}, "
            f"XP {backup.streak.get('xp', 0)}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Settings-window dialogs
# --------------------------------------------------------------------------

def export_dialog(parent, get_config, validate=None):
    """Ask where to save, then export. Returns True on success.

    *get_config* returns the settings dict to export (the current window
    state); *validate*, if given, returns None or (tab_key, message).
    """
    from tkinter import filedialog, messagebox

    if validate:
        problem = validate()
        if problem:
            messagebox.showerror("Cannot export", problem[1], parent=parent)
            return False

    path = filedialog.asksaveasfilename(
        parent=parent,
        title="Export settings and stats",
        defaultextension=".json",
        initialfile=default_backup_name(),
        filetypes=[("PhraseLock backup", "*.json"), ("All files", "*.*")],
    )
    if not path:
        return False

    include_password = messagebox.askyesnocancel(
        "Export settings and stats",
        "Include the emergency password in the backup?\n\n"
        "Yes: best for moving to another PC of yours (it is stored as a salted hash).\n"
        "No: choose this if you plan to share the file.",
        parent=parent,
    )
    if include_password is None:
        return False

    try:
        data = export_backup(path, get_config(), include_password=include_password)
    except Exception as exc:
        log("Export failed:\n" + traceback.format_exc())
        messagebox.showerror("Export failed", f"Could not write the backup:\n{exc}", parent=parent)
        return False

    messagebox.showinfo(
        "Export complete",
        f"Saved {len(data['config'])} settings and {len(data['stats'])} unlock records to:\n{path}\n\n"
        "Keep this file private. On the new PC, open Settings and use IMPORT.",
        parent=parent,
    )
    return True


def import_dialog(parent):
    """Pick a backup, confirm, apply. Returns True if something was imported.

    The caller should close and reopen the Settings window afterwards,
    because its fields still show the old values.
    """
    from tkinter import filedialog, messagebox

    path = filedialog.askopenfilename(
        parent=parent,
        title="Import settings and stats",
        filetypes=[("PhraseLock backup", "*.json"), ("All files", "*.*")],
    )
    if not path:
        return False

    try:
        backup = load_backup(path)
    except BackupError as exc:
        messagebox.showerror("Import failed", str(exc), parent=parent)
        return False

    if not messagebox.askyesno(
        "Import settings and stats",
        f"{describe(backup)}\n\n"
        "This replaces your current settings and statistics (the current files are kept "
        "as .bak copies) and discards unsaved changes in this window. "
        "Only import backups you trust.\n\nImport now?",
        parent=parent,
    ):
        return False

    try:
        apply_backup(backup)
    except BackupError as exc:
        messagebox.showerror("Import failed", str(exc), parent=parent)
        return False

    message = "Import complete. The Settings window will now close; reopen it to see the imported values."
    if backup.warnings:
        shown = backup.warnings[:8]
        extra = len(backup.warnings) - len(shown)
        message += "\n\nNotes:\n- " + "\n- ".join(shown)
        if extra > 0:
            message += f"\n- ...and {extra} more"
    messagebox.showinfo("Import complete", message, parent=parent)
    return True
