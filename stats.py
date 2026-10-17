"""Streaks, XP, badges, statistics and emergency password hashing."""

import os
import json
import time
import hashlib
import hmac
import secrets
import traceback
from datetime import datetime, date, timedelta

from config import CONFIG_DIR, LOG_PATH, STATS_PATH, STREAK_PATH, save_json, log

# --------------------------------------------------------------------------
# Typing metrics
# --------------------------------------------------------------------------
def compute_wpm(chars_typed, elapsed_seconds):
    """Standard WPM: (characters / 5) / minutes. Returns 0 for bad input."""
    try:
        chars_typed = int(chars_typed)
        elapsed = float(elapsed_seconds)
    except (TypeError, ValueError):
        return 0.0
    if chars_typed <= 0 or elapsed <= 0:
        return 0.0
    return round((chars_typed / 5.0) / (elapsed / 60.0), 1)


def compute_accuracy(correct_rounds, total_rounds):
    if total_rounds <= 0:
        return 0.0
    return round(100.0 * correct_rounds / total_rounds, 1)


def record_stat(rounds, duration_seconds, first_try=True, emergency=False,
                chars_typed=0, correct_rounds=None, submissions=None):
    """Write a stat entry.

    Backwards-compatible: callers that don't pass the new kwargs get the old
    behavior (no WPM/accuracy fields written).

    accuracy = correct submissions / all submissions. `submissions` counts
    every Enter/click including typos; without it the round count is used.
    """
    try:
        try:
            with open(STATS_PATH, "r", encoding="utf-8") as f:
                stats = json.load(f)
            if not isinstance(stats, list):
                stats = []
        except Exception:
            stats = []
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "rounds": rounds,
            "duration_seconds": round(duration_seconds, 1),
            "first_try": bool(first_try),
            "emergency": bool(emergency),
        }
        if chars_typed and duration_seconds:
            entry["wpm"] = compute_wpm(chars_typed, duration_seconds)
        total_submissions = submissions if submissions else rounds
        if correct_rounds is not None and total_submissions:
            entry["accuracy"] = compute_accuracy(correct_rounds, total_submissions)
        stats.append(entry)
        save_json(STATS_PATH, stats[-500:])
    except Exception:
        log("Could not write stats:\n" + traceback.format_exc())


def weekly_series(stats, days=7, today=None):
    """Return one bucket per day, oldest first.

    Each bucket: {"date": "YYYY-MM-DD", "label": "Mon",
                  "total": N, "first_try": N, "wpm": float|None,
                  "accuracy": float|None}
    """
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    buckets = {}
    for i in range(days):
        d = start + timedelta(days=i)
        iso = d.isoformat()
        buckets[iso] = {
            "date": iso,
            "label": d.strftime("%a"),
            "total": 0,
            "first_try": 0,
            "wpm_sum": 0.0,
            "wpm_n": 0,
            "acc_sum": 0.0,
            "acc_n": 0,
        }
    for s in stats:
        ts = s.get("timestamp", "")[:10]
        if ts not in buckets:
            continue
        b = buckets[ts]
        b["total"] += 1
        if s.get("first_try") and not s.get("emergency"):
            b["first_try"] += 1
        if isinstance(s.get("wpm"), (int, float)):
            b["wpm_sum"] += float(s["wpm"])
            b["wpm_n"] += 1
        if isinstance(s.get("accuracy"), (int, float)):
            b["acc_sum"] += float(s["accuracy"])
            b["acc_n"] += 1
    out = []
    for iso in sorted(buckets):
        b = buckets[iso]
        out.append({
            "date": b["date"],
            "label": b["label"],
            "total": b["total"],
            "first_try": b["first_try"],
            "wpm": round(b["wpm_sum"] / b["wpm_n"], 1) if b["wpm_n"] else None,
            "accuracy": round(b["acc_sum"] / b["acc_n"], 1) if b["acc_n"] else None,
        })
    return out


def get_progress():
    try:
        with open(STREAK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    today = date.today().isoformat()
    if data.get("goal_date") != today:
        data["goal_date"] = today
        data["goal_progress"] = 0
    return data


def add_progress(xp_gain=0, successful=False):
    data = get_progress()
    if successful:
        data["goal_progress"] = int(data.get("goal_progress", 0)) + 1
    data["xp"] = int(data.get("xp", 0)) + int(xp_gain)
    data["goal_date"] = date.today().isoformat()
    save_json(STREAK_PATH, data)
    return data


def get_xp_level(xp):
    xp = max(0, int(xp))
    level = 1
    need = 100
    while xp >= need:
        xp -= need
        level += 1
        need = 100 + ((level - 1) * 50)
    return level, xp, need


def badges_for(stats, streak, best):
    total = len(stats)
    perfect = sum(1 for x in stats if x.get("first_try") and not x.get("emergency"))
    badges = []
    for threshold, name in ((1, "FIRST BLOOD"), (7, "7 DAY STREAK"),
                            (30, "30 DAY STREAK"), (100, "100 PERFECT"),
                            (500, "500 UNLOCKS")):
        if "STREAK" in name:
            ok = streak >= threshold
        elif "PERFECT" in name:
            ok = perfect >= threshold
        else:
            ok = total >= threshold
        if ok:
            badges.append(name)
    return badges


def _read_streak_data():
    default = {"current_streak": 0, "best_streak": 0, "last_qualifying_day": None}
    try:
        with open(STREAK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return default
    return data if isinstance(data, dict) else default


def update_streak(first_try, today=None):
    """Update daily streak. A qualifying day = a successful session with no
    incorrect submission. *today* is injectable for tests (ISO date string)."""
    today = today or date.today().isoformat()
    try:
        data = _read_streak_data()
        if first_try:
            last = data.get("last_qualifying_day")
            if last == today:
                return data.get("current_streak", 0)
            yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
            if last == yesterday:
                data["current_streak"] = int(data.get("current_streak", 0)) + 1
            else:
                data["current_streak"] = 1
            data["last_qualifying_day"] = today
            data["best_streak"] = max(
                int(data.get("best_streak", 0)),
                int(data.get("current_streak", 0)),
            )
            save_json(STREAK_PATH, data)
        return int(data.get("current_streak", 0))
    except Exception:
        log("Could not update streak:\n" + traceback.format_exc())
        return 0


def get_streak(today=None):
    try:
        data = _read_streak_data()
        current = int(data.get("current_streak", 0))
        last = data.get("last_qualifying_day")
        today = today or date.today().isoformat()
        if last:
            days = (date.fromisoformat(today) - date.fromisoformat(last)).days
            if days > 1:
                current = 0
        return current, int(data.get("best_streak", 0))
    except Exception:
        return 0, 0


def set_emergency_password(password, iterations=210000):
    password = password or ""
    if not password:
        return {"emergency_password_salt": "", "emergency_password_hash": ""}
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {
        "emergency_password_salt": salt.hex(),
        "emergency_password_hash": digest.hex(),
        "emergency_password_iterations": iterations,
    }


def verify_emergency_password(cfg, password):
    salt_hex = cfg.get("emergency_password_salt", "")
    expected_hex = cfg.get("emergency_password_hash", "")
    if not salt_hex or not expected_hex:
        return False
    try:
        iterations = int(cfg.get("emergency_password_iterations", 210000))
        digest = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode("utf-8"),
            bytes.fromhex(salt_hex), iterations
        )
        return hmac.compare_digest(digest.hex(), expected_hex)
    except Exception:
        return False