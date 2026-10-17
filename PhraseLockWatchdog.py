"""
PhraseLockWatchdog - optional companion process.

Usage:
    PhraseLockWatchdog.exe PhraseLock.exe

It restarts PhraseLock if the main process disappears. This is a deterrent/
continuity feature, not a security mechanism. Disable Auto-protection in
PhraseLock settings before uninstalling PhraseLock.
"""

import os
import sys
import time
import subprocess

import psutil


def log(message):
    try:
        appdata = os.environ.get("APPDATA", ".")
        path = os.path.join(appdata, "PhraseLock", "phraselock.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("[Watchdog] " + message + "\n")
    except Exception:
        pass


def is_running(exe_path):
    target = os.path.normcase(os.path.abspath(exe_path))
    for p in psutil.process_iter(["exe", "cmdline"]):
        try:
            exe = p.info.get("exe")
            args = p.info.get("cmdline") or []
            if exe and os.path.normcase(os.path.abspath(exe)) == target and "--monitor" in args:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass
    return False


def main():
    if len(sys.argv) < 3:
        return
    target = os.path.abspath(sys.argv[2])
    if not os.path.isfile(target):
        log("Target executable not found: " + target)
        return

    log("Watchdog started for " + target)
    while True:
        time.sleep(2)
        # If the target was intentionally disabled, the watchdog should stop.
        # Settings writes auto_protection=False; the watcher checks config.
        try:
            import json
            cfg_path = os.path.join(os.environ.get("APPDATA", "."), "PhraseLock", "config.json")
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if not cfg.get("auto_protection", False):
                log("Auto-protection disabled; watchdog exiting.")
                return
        except Exception:
            # If config is temporarily unreadable, keep watching.
            pass

        if not is_running(target):
            log("PhraseLock process disappeared; restarting it.")
            try:
                subprocess.Popen(
                    [target, "--monitor"],
                    cwd=os.path.dirname(target),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                time.sleep(3)
            except Exception as e:
                log("Restart failed: " + repr(e))


if __name__ == "__main__":
    main()
