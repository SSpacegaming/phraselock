"""PhraseLock entry point.

Public names are re-exported so settings.py and other callers keep working
unchanged (`phrase_lock.CONFIG_DIR`, `phrase_lock.load_config`, etc.).
"""

import os
import sys

from config import (
    CONFIG_DIR, CONFIG_PATH, LOG_PATH, STATS_PATH, STREAK_PATH,
    MEDIA_CACHE_DIR, DEFAULT_CONFIG,
    log, load_config, save_json, within_schedule, _normalize,
    _contrast_colors, _blend_hex,
)
from stats import (
    record_stat, get_progress, add_progress, get_xp_level, badges_for,
    update_streak, get_streak, set_emergency_password, verify_emergency_password,
    compute_wpm, compute_accuracy, weekly_series,
)
from media import (
    _is_http_url, _remote_media_cache, play_audio,
    MAX_IMAGE_BYTES, MAX_AUDIO_BYTES,
)
from overlay import (
    show_overlay, start_standby_overlay,
    _overlay_is_running, _try_acquire_overlay_mutex, _standby,
    OVERLAY_MUTEX_NAME,
)
from phrases import (
    load_external_phrases, get_phrases,
    pick_phrase, remember_last_phrase, get_last_phrase,  # <-- new
)
from session import (
    MONITOR_MUTEX_NAME, acquire_single_instance,
    _start_idle_monitor, show_focus_session, _launch_lock_after_unlock,
    _workstation_is_locked, _poll_session_state, watch_session_events,
    start_watchdog,
)


def _phrase_items_for_overlay(cfg):
    return get_phrases(cfg)


def _run_monitor():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not acquire_single_instance(MONITOR_MUTEX_NAME):
        log("PhraseLock monitor is already running; exiting duplicate.")
        raise SystemExit
    log("=== PhraseLock monitor started ===")
    try:
        cfg = load_config()
        _start_idle_monitor(cfg)
        start_standby_overlay(_phrase_items_for_overlay)
        start_watchdog()
        watch_session_events()
    except Exception:
        import traceback
        log("FATAL ERROR:\n" + traceback.format_exc())


if __name__ == "__main__":
    if "--settings" in sys.argv:
        import settings
        settings.main()
        raise SystemExit
    if "--monitor" in sys.argv:
        _run_monitor()
        raise SystemExit
    if "--watchdog" in sys.argv:
        from PhraseLockWatchdog import main as watchdog_main
        watchdog_main()
        raise SystemExit
    if "--preview" in sys.argv:
        show_overlay(load_config(), _phrase_items_for_overlay(load_config()),
                     record_stats=False, preview=True)
        raise SystemExit
    if "--focus-session" in sys.argv:
        show_focus_session(load_config())
        raise SystemExit
    if "--test-audio" in sys.argv:
        try:
            idx = sys.argv.index("--test-audio")
            value = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
            play_audio(value)
            import time
            time.sleep(30)
        except Exception:
            log("Audio test failed:\n")
        raise SystemExit
    if "--lock" in sys.argv:
        if not acquire_single_instance(OVERLAY_MUTEX_NAME):
            log("Another lock overlay is already open; exiting this one.")
            raise SystemExit
        cfg = load_config()
        if cfg.get("enabled", True) and within_schedule(cfg):
            show_overlay(cfg, _phrase_items_for_overlay(cfg),
                         record_stats=True, preview=False)
        raise SystemExit

    # No arguments: open the control panel. The background monitor uses --monitor.
    import settings
    settings.main()
