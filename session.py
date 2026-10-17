"""Windows session monitoring, idle-lock, focus session, watchdog startup."""

import os
import sys
import time
import ctypes
import subprocess
import threading
import traceback
import tkinter as tk

import win32con
import win32gui
import win32ts
import win32api
import win32event
import winerror 

from config import load_config, log, within_schedule, self_command
from overlay import _overlay_is_running, _standby

WM_WTSSESSION_CHANGE = getattr(win32con, "WM_WTSSESSION_CHANGE", 0x02B1)
WTS_SESSION_LOCK = getattr(win32con, "WTS_SESSION_LOCK", 0x7)
WTS_SESSION_UNLOCK = getattr(win32con, "WTS_SESSION_UNLOCK", 0x8)

OVERLAY_MUTEX_NAME = "Local\\PhraseLockOverlay"
MONITOR_MUTEX_NAME = "Local\\PhraseLockMonitor"

_unlock_launch_guard = threading.Lock()
_last_unlock_launch = 0.0
_held_mutexes = []


def acquire_single_instance(name):
    try:
        handle = win32event.CreateMutex(None, False, name)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            return False
        _held_mutexes.append(handle)
        return True
    except Exception:
        log("Single-instance check failed:\n" + traceback.format_exc())
        return True


def _start_idle_monitor(cfg):
    if not cfg.get("idle_lock_enabled", False):
        return
    minutes = max(1, int(cfg.get("idle_lock_minutes", 30) or 30))
    threshold = minutes * 60 * 1000

    def worker():
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        while True:
            try:
                info = LASTINPUTINFO()
                info.cbSize = ctypes.sizeof(LASTINPUTINFO)
                if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                    tick = ctypes.c_uint32(ctypes.windll.kernel32.GetTickCount()).value
                    idle = (tick - info.dwTime) & 0xFFFFFFFF
                    if idle >= threshold and load_config().get("enabled", True) and not _overlay_is_running():
                        ctypes.windll.user32.LockWorkStation()
                        time.sleep(60)
                time.sleep(5)
            except Exception:
                log("Idle monitor error:\n" + traceback.format_exc())
                time.sleep(10)

    threading.Thread(target=worker, name="PhraseLockIdleMonitor", daemon=True).start()


def show_focus_session(cfg):
    minutes = max(1, int(cfg.get("focus_session_minutes", 45) or 45))
    blocked = [os.path.basename(str(x)).lower()
               for x in (cfg.get("focus_block_apps") or []) if str(x).strip()]
    root = tk.Tk()
    root.title("PhraseLock // FOCUS SESSION")
    root.geometry("460x230+40+40")
    root.configure(bg="#07070b")
    accent = {"Cyber Red": "#ff1744", "Neon Pink": "#ff2aa3",
              "Cyber Blue": "#2979ff", "Matrix": "#00e676",
              "Dark Purple": "#9c27ff", "Blackout": "#eeeeee"}.get(
        cfg.get("theme", "Cyber Red"), "#ff1744")
    tk.Label(root, text="// FOCUS SESSION", font=("Consolas", 12, "bold"),
             fg=accent, bg="#07070b").pack(anchor="w", padx=20, pady=(18, 3))
    tk.Label(root, text="DISCIPLINE WINDOW ACTIVE", font=("Consolas", 9),
             fg="#888894", bg="#07070b").pack(anchor="w", padx=20)
    remaining = minutes * 60
    timer = tk.StringVar()
    status = tk.StringVar(value=f"APP GUARD: {len(blocked)} process(es)"
                            if blocked else "APP GUARD: OFF")
    tk.Label(root, textvariable=timer, font=("Consolas", 32, "bold"),
             fg="#f7f7fb", bg="#07070b").pack(pady=10)
    tk.Label(root, textvariable=status, font=("Consolas", 8),
             fg="#777785", bg="#07070b").pack()
    bar = tk.Canvas(root, height=4, bg="#17171e", highlightthickness=0)
    bar.pack(fill="x", padx=20, pady=(12, 0))
    start = time.monotonic()

    def guard_apps():
        if not blocked:
            return
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if (proc.info.get("name") or "").lower() in blocked and proc.pid != os.getpid():
                        proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception:
            pass

    def tick():
        nonlocal remaining
        elapsed = int(time.monotonic() - start)
        remaining = max(0, minutes * 60 - elapsed)
        timer.set(f"{remaining // 60:02d}:{remaining % 60:02d}")
        width = 420 * remaining / (minutes * 60) if minutes else 0
        bar.delete("all")
        bar.create_rectangle(0, 0, width, 4, fill=accent, outline="")
        guard_apps()
        if remaining > 0:
            root.after(1000, tick)
        else:
            timer.set("00:00")
            root.after(1500, root.destroy)

    tick()
    root.mainloop()


def _launch_lock_after_unlock(delay=0.2):
    def worker():
        global _last_unlock_launch
        time.sleep(delay)
        with _unlock_launch_guard:
            now = time.monotonic()
            if now - _last_unlock_launch < 3.0:
                log("Duplicate unlock trigger ignored.")
                return
            _last_unlock_launch = now
        if _overlay_is_running():
            log("Overlay already running; not starting another one.")
            return
        cfg = load_config()
        in_schedule = within_schedule(cfg)
        log(f"Unlock follow-up. enabled={cfg.get('enabled', True)} in_schedule={in_schedule}")
        if not cfg.get("enabled", True) or not in_schedule:
            return
        if _standby["ready"].is_set() and not _standby["active"].is_set():
            _standby["trigger"].set()
            log("Triggered the pre-built standby overlay.")
            return
        # Slow path: the standby overlay is still being (re)built (just after
        # start-up or a settings save). Show a separate overlay process rather
        # than leaving the PC unlocked.
        command, cwd = self_command("--lock")
        try:
            subprocess.Popen(command, cwd=cwd,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             close_fds=True)
            log("Standby not ready; started a separate lock overlay process.")
        except Exception:
            log("Could not start lock overlay process:\n" + traceback.format_exc())

    threading.Thread(target=worker, name="PhraseLockUnlockLauncher", daemon=True).start()


def _workstation_is_locked():
    user32 = ctypes.windll.user32
    user32.OpenInputDesktop.restype = ctypes.c_void_p
    user32.GetUserObjectInformationW.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
    ]
    user32.GetUserObjectInformationW.restype = ctypes.c_int
    UOI_NAME = 2
    DESKTOP_READOBJECTS = 0x0001
    handle = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
    if not handle:
        return False
    try:
        size = ctypes.c_uint32(256)
        buf = ctypes.create_unicode_buffer(256)
        if not user32.GetUserObjectInformationW(handle, UOI_NAME, buf, size.value,
                                                ctypes.byref(size)):
            return False
        return buf.value.strip().lower() == "winlogon"
    finally:
        user32.CloseDesktop(handle)


def _poll_session_state():
    was_locked = False
    locked_streak = 0
    while True:
        try:
            locked = _workstation_is_locked()
            locked_streak = locked_streak + 1 if locked else 0
            if locked_streak >= 2 and not was_locked:
                was_locked = True
                log("Workstation lock detected by desktop-state fallback.")
            elif not locked and was_locked:
                was_locked = False
                log("Workstation unlock detected by desktop-state fallback.")
                _launch_lock_after_unlock(0.2)
        except Exception as exc:
            log(f"Workstation-state fallback error: {exc}")
        time.sleep(0.25)


def watch_session_events():
    def wndproc(hwnd, msg, wparam, lparam):
        try:
            if msg == WM_WTSSESSION_CHANGE:
                log(f"WM_WTSSESSION_CHANGE received, wparam={wparam}")
                if wparam == WTS_SESSION_LOCK:
                    log("Session locked.")
                elif wparam == WTS_SESSION_UNLOCK:
                    log("Session unlock notification received; waiting for desktop.")
                    _launch_lock_after_unlock(0.2)
        except Exception:
            log("ERROR in wndproc:\n" + traceback.format_exc())
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = wndproc
    wc.lpszClassName = "PhraseLockHiddenWindow"
    wc.hInstance = win32api.GetModuleHandle(None)
    try:
        class_atom = win32gui.RegisterClass(wc)
    except Exception:
        class_atom = wc.lpszClassName
        log("RegisterClass failed (probably already registered), continuing.")

    hwnd = win32gui.CreateWindow(
        class_atom, "PhraseLockHiddenWindow", 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None
    )
    log(f"Hidden window created, hwnd={hwnd}")
    ok = win32ts.WTSRegisterSessionNotification(hwnd, win32ts.NOTIFY_FOR_THIS_SESSION)
    log(f"WTSRegisterSessionNotification -> {ok}")

    threading.Thread(target=_poll_session_state,
                     name="PhraseLockSessionPoller", daemon=True).start()
    win32gui.PumpMessages()


def start_watchdog():
    if not getattr(sys, "frozen", False):
        return
    if "--watchdog-child" in sys.argv:
        return
    cfg = load_config()
    if not cfg.get("auto_protection", False):
        return
    watchdog = sys.executable
    try:
        subprocess.Popen([watchdog, "--watchdog", sys.executable],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                         close_fds=True)
        log("Watchdog started.")
    except Exception:
        log("Could not start watchdog:\n" + traceback.format_exc())