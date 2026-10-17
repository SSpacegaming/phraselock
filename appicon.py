"""Shared application icon helpers (settings window + system tray).

Looks for icon.ico / icon.png in, in this order:
  1. the PyInstaller bundle folder (sys._MEIPASS) - needs --add-data in bat.bat
  2. the folder of the running exe (frozen) or of this script
  3. the current working directory

All functions are best-effort and never raise: if no icon file is found the
callers fall back to their own default.
"""

import os
import sys


def _search_dirs():
    dirs = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(meipass)
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(os.path.abspath(sys.executable)))
    dirs.append(os.path.dirname(os.path.abspath(__file__)))
    dirs.append(os.getcwd())
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def find_icon(name):
    """Return the full path of `name` (e.g. 'icon.ico') or None."""
    for d in _search_dirs():
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def set_app_user_model_id(app_id="PhraseLock.App"):
    """Make Windows group the taskbar button under our own identity (and
    icon) instead of the generic Python one. Harmless when frozen."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def apply_window_icon(root):
    """Give a Tk window (and every dialog opened from it) the PhraseLock icon
    instead of the default Tk feather. Call right after `root = tk.Tk()`."""
    set_app_user_model_id()
    ico = find_icon("icon.ico")
    if ico:
        try:
            root.iconbitmap(default=ico)
            return True
        except Exception:
            pass
    png = find_icon("icon.png")
    if png:
        try:
            import tkinter as tk
            img = tk.PhotoImage(file=png)
            root.iconphoto(True, img)
            root._phraselock_icon_ref = img  # keep a reference alive
            return True
        except Exception:
            pass
    return False


def load_tray_image(size=64):
    """Return the app icon as a square RGBA PIL image, or None."""
    try:
        from PIL import Image
    except Exception:
        return None
    for name in ("icon.png", "icon.ico"):
        path = find_icon(name)
        if not path:
            continue
        try:
            img = Image.open(path)
            if name.endswith(".ico"):
                # pick the biggest frame of the .ico
                sizes = sorted(img.info.get("sizes", []) or [img.size])
                if sizes:
                    img.size = sizes[-1]
                    img.load()
            img = img.convert("RGBA")
            if img.size != (size, size):
                img = img.resize((size, size), Image.LANCZOS)
            return img
        except Exception:
            continue
    return None
