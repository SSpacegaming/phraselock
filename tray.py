"""System-tray status icon for the PhraseLock monitor.

The icon lives in the Windows notification area (the "hidden icons" overflow
included). It is shown as long as the monitor process is alive, so its
presence tells you PhraseLock is running. It is the application's own icon
(icon.ico / icon.png); a small badge in the corner shows the state:

    no badge     - running and active
    yellow badge - running, but outside the configured schedule
    grey badge   - running, but disabled in the settings

Everything here is best-effort: if pystray is missing or the tray cannot be
created, the monitor keeps working without an icon.

Settings window guard
---------------------
The settings process calls `mark_settings_open()` at startup. The tray's
"Open settings" button checks `settings_is_open()` and does nothing (except a
small notification) when a settings window already exists, no matter whether
it was started from the exe or from the tray. Opening the exe by hand still
opens as many windows as you like.
"""

import os
import subprocess
import sys
import threading

from PIL import Image, ImageDraw

from config import load_config, within_schedule, log
from appicon import load_tray_image

POLL_SECONDS = 5

# state -> (tooltip, badge colour or None for "no badge")
STATES = {
    "active": ("PhraseLock - running", None),
    "idle": ("PhraseLock - running (outside schedule)", (241, 196, 15, 255)),
    "disabled": ("PhraseLock - disabled", (149, 165, 166, 255)),
}

SETTINGS_MUTEX = "Local\\PhraseLockSettingsOpen"
_SYNCHRONIZE = 0x00100000
_settings_handle = None   # kept alive for the whole life of the settings process
_last_settings_proc = None


# --------------------------------------------------------------------------
# Settings "already open" detection
# --------------------------------------------------------------------------

def mark_settings_open():
    """Call once at the start of a settings process. Released automatically
    by Windows when the process exits (even if it crashes)."""
    global _settings_handle
    try:
        import ctypes
        _settings_handle = ctypes.windll.kernel32.CreateMutexW(None, False, SETTINGS_MUTEX)
    except Exception:
        log("Could not create settings marker mutex.")


def settings_is_open():
    """True if any settings process is currently running."""
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.OpenMutexW(_SYNCHRONIZE, False, SETTINGS_MUTEX)
        if handle:
            k32.CloseHandle(handle)
            return True
    except Exception:
        pass
    return False


# --------------------------------------------------------------------------
# Icon drawing
# --------------------------------------------------------------------------

def _fallback_icon(size=64):
    """Plain padlock, only used when icon.ico / icon.png cannot be found."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64.0

    def box(x0, y0, x1, y1):
        return [x0 * s, y0 * s, x1 * s, y1 * s]

    d.arc(box(16, 6, 48, 40), 180, 360, fill=(230, 230, 235, 255), width=max(2, int(6 * s)))
    d.rounded_rectangle(box(10, 26, 54, 58), radius=int(7 * s), fill=(52, 61, 80, 255),
                        outline=(230, 230, 235, 255), width=max(1, int(2 * s)))
    d.ellipse(box(28, 36, 36, 44), fill=(230, 230, 235, 255))
    d.rectangle(box(30.5, 42, 33.5, 50), fill=(230, 230, 235, 255))
    return img


def make_icon(badge_color=None, size=64):
    """The application icon, with a small coloured badge in the bottom-right
    corner when `badge_color` is given."""
    img = load_tray_image(size) or _fallback_icon(size)
    if badge_color:
        d = ImageDraw.Draw(img)
        r = int(size * 0.2)
        cx, cy = size - r - 1, size - r - 1
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=badge_color,
                  outline=(20, 20, 20, 255), width=max(1, size // 32))
    return img


def current_state():
    try:
        cfg = load_config()
        if not cfg.get("enabled", True):
            return "disabled"
        if not within_schedule(cfg):
            return "idle"
    except Exception:
        pass
    return "active"


# --------------------------------------------------------------------------
# Opening the settings window from the tray
# --------------------------------------------------------------------------

def _child_env():
    """Environment for a child launched from a PyInstaller one-file exe.

    A one-file exe unpacks itself into a temporary _MEI folder and tells any
    child process (through environment variables) to reuse that folder. When
    the monitor starts the same exe again, the child must NOT reuse it, or it
    dies with "Failed to start embedded python interpreter!". Resetting the
    environment makes the child extract its own copy like a normal launch.
    """
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env.pop("_MEIPASS2", None)
    return env


def _open_settings(icon=None, item=None):
    global _last_settings_proc
    try:
        # Already running (started from the exe or from a previous click)?
        proc = _last_settings_proc
        if (proc is not None and proc.poll() is None) or settings_is_open():
            log("Settings already open; not starting another one.")
            try:
                if icon is not None:
                    icon.notify("The settings window is already open.", "PhraseLock")
            except Exception:
                pass
            return

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--settings"]
        else:
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phrase_lock.py")
            cmd = [sys.executable, script, "--settings"]
        _last_settings_proc = subprocess.Popen(
            cmd, creationflags=flags, env=_child_env(), close_fds=True)
    except Exception:
        import traceback
        log("Could not open settings from tray icon:\n" + traceback.format_exc())


def start_tray():
    """Start the tray icon in the background. Returns the icon, or None."""
    try:
        import pystray
    except ImportError:
        log("pystray not installed; tray icon disabled.")
        return None

    try:
        state = {"name": current_state()}

        def status_text(item):
            return STATES[state["name"]][0]

        menu = pystray.Menu(
            pystray.MenuItem(status_text, None, enabled=False),
            pystray.MenuItem("Open settings", _open_settings, default=True),
        )
        text, color = STATES[state["name"]]
        icon = pystray.Icon("PhraseLock", make_icon(color), text, menu)

        stop = threading.Event()

        def refresh_loop():
            while not stop.wait(POLL_SECONDS):
                try:
                    new = current_state()
                    if new != state["name"]:
                        state["name"] = new
                        t, c = STATES[new]
                        icon.icon = make_icon(c)
                        icon.title = t
                        icon.update_menu()
                except Exception:
                    log("Tray refresh failed.")

        threading.Thread(target=refresh_loop, daemon=True).start()
        icon.run_detached()
        log("Tray icon started.")
        return icon
    except Exception:
        import traceback
        log("Tray icon failed to start:\n" + traceback.format_exc())
        return None
