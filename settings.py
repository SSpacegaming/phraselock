"""
PhraseLock - Settings panel (tabbed).

Tabs: Phrases, Look, Rules, Protection, Stats.
The Save / Preview / LOCK NOW bar is always visible at the bottom.
"""

import os
import re
import json
import subprocess
import sys
import backup
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog, colorchooser
from datetime import datetime
from appicon import apply_window_icon

import phrase_lock
import monitors
import media
import hotkeys

CONFIG_DIR = phrase_lock.CONFIG_DIR
CONFIG_PATH = phrase_lock.CONFIG_PATH
STATS_PATH = phrase_lock.STATS_PATH
DEFAULT_CONFIG = phrase_lock.DEFAULT_CONFIG

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


# --------------------------------------------------------------------------
# helpers (no UI)
# --------------------------------------------------------------------------
def parse_hhmm(text):
    """'8:05' / '08:05' -> (8, 5); anything else -> None."""
    m = TIME_RE.match((text or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def fmt_hhmm(t):
    return f"{t[0]:02d}:{t[1]:02d}"


def color_ok(text):
    """Empty means 'use the default'. Otherwise the colour must be one the
    lock overlay can actually draw (it uses PIL.ImageColor)."""
    text = (text or "").strip()
    if not text:
        return True
    try:
        from PIL import ImageColor
        ImageColor.getrgb(text)
        return True
    except ImportError:
        return bool(HEX_COLOR_RE.match(text))
    except ValueError:
        return False


def num(var, default, lo=None, hi=None):
    """Read an IntVar safely: junk typed into a Spinbox must not crash Save."""
    try:
        value = int(var.get())
    except (tk.TclError, ValueError):
        value = default
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def load_config():
    return phrase_lock.load_config()


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    phrase_lock.save_json(CONFIG_PATH, cfg)


def get_startup_folder():
    return os.path.join(
        os.environ.get("APPDATA", "."),
        r"Microsoft\Windows\Start Menu\Programs\Startup"
    )


def startup_shortcut_path():
    return os.path.join(get_startup_folder(), "PhraseLock.lnk")


def is_startup_enabled():
    return os.path.exists(startup_shortcut_path())


def enable_startup(target_exe):
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(startup_shortcut_path())
    shortcut.TargetPath = target_exe
    shortcut.WorkingDirectory = os.path.dirname(target_exe)
    shortcut.IconLocation = target_exe
    shortcut.Save()


def disable_startup():
    path = startup_shortcut_path()
    if os.path.exists(path):
        os.remove(path)


def ensure_phrase_lock_monitor():
    """Make sure the background PhraseLock session monitor is running.

    Settings.exe and PhraseLock.exe are separate programs in the packaged build.
    Previously the Settings UI could be open while no monitor process existed,
    making Win+L appear to do nothing.
    """
    import subprocess, sys
    try:
        import psutil
    except ImportError:
        psutil = None

    script = os.path.abspath(phrase_lock.__file__)
    if getattr(sys, "frozen", False):
        target = sys.executable
        target_cmp = os.path.normcase(os.path.abspath(target))
        if psutil:
            for proc in psutil.process_iter(["exe", "cmdline"]):
                try:
                    exe = proc.info.get("exe")
                    args = proc.info.get("cmdline") or []
                    if exe and os.path.normcase(os.path.abspath(exe)) == target_cmp and "--monitor" in args:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    pass
        subprocess.Popen([target, "--monitor"], cwd=os.path.dirname(target), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True

    if psutil:
        script_cmp = os.path.normcase(os.path.abspath(script))
        for proc in psutil.process_iter(["cmdline"]):
            try:
                args = proc.info.get("cmdline") or []
                if args and any(os.path.normcase(os.path.abspath(str(a))) == script_cmp for a in args[:2]) and "--monitor" in args:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError):
                pass
    subprocess.Popen([sys.executable, script, "--monitor"], cwd=os.path.dirname(script), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return True


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
def main():
    cfg = load_config()
    if cfg.get("enabled", True):
        try:
            ensure_phrase_lock_monitor()
        except Exception:
            pass

    root = tk.Tk()
    apply_window_icon(root)
    root.title("PhraseLock - Settings")
    root.geometry("760x820")
    root.minsize(680, 560)

    # TechDom visual system: dark control-console aesthetic with sharp neon accents.
    UI_BG = "#050507"
    CARD_BG = "#0d0d12"
    CARD_ALT = "#14141b"
    TEXT = "#f7f7fb"
    MUTED = "#777785"
    ACCENT = "#ff1744"
    ACCENT_2 = "#b400ff"
    CYAN = "#00e5ff"
    INPUT_BG = "#08080c"
    BAD_BG = "#2a0b12"
    BORDER = "#272732"
    DANGER = "#ff1744"
    WARN = "#ffb86b"

    root.configure(bg=UI_BG)
    root.option_add("*Font", "{Bahnschrift} 10")
    root.option_add("*Background", UI_BG)
    root.option_add("*Foreground", TEXT)
    root.option_add("*Label.Background", UI_BG)
    root.option_add("*Label.Foreground", TEXT)
    root.option_add("*Frame.Background", UI_BG)
    root.option_add("*Button.Background", CARD_ALT)
    root.option_add("*Button.Foreground", TEXT)
    root.option_add("*Button.ActiveBackground", ACCENT)
    root.option_add("*Button.ActiveForeground", "white")
    root.option_add("*Button.Relief", "flat")
    root.option_add("*Button.BorderWidth", 0)
    root.option_add("*Entry.Background", INPUT_BG)
    root.option_add("*Entry.Foreground", TEXT)
    root.option_add("*Entry.InsertBackground", ACCENT)
    root.option_add("*Text.Background", INPUT_BG)
    root.option_add("*Text.Foreground", TEXT)
    root.option_add("*Checkbutton.Background", UI_BG)
    root.option_add("*Checkbutton.Foreground", TEXT)
    root.option_add("*Checkbutton.SelectColor", ACCENT)
    root.option_add("*Scale.Background", UI_BG)
    root.option_add("*Scale.TroughColor", BORDER)
    root.option_add("*Scale.Activebackground", ACCENT)

    # ttk (tabs + scrollbars) styled to match
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TNotebook", background=UI_BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=CARD_ALT, foreground=MUTED,
                    padding=(20, 9), font=("Consolas", 10, "bold"), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", CARD_BG), ("active", "#1b1b25")],
              foreground=[("selected", CYAN), ("active", TEXT)])
    style.configure("Vertical.TScrollbar", background=CARD_ALT, troughcolor=UI_BG,
                    bordercolor=UI_BG, lightcolor=CARD_ALT, darkcolor=CARD_ALT,
                    arrowcolor=MUTED)
    style.map("Vertical.TScrollbar", background=[("active", ACCENT)])

    # ---------------------------------------------------------------- header
    header = tk.Frame(root, bg=UI_BG, highlightthickness=1, highlightbackground=BORDER)
    header.pack(fill="x", padx=12, pady=(12, 6))
    tk.Label(header, text="// PHRASELOCK :: CONTROL NODE", font=("Consolas", 9, "bold"), fg=CYAN, bg=UI_BG).pack(anchor="w", padx=14, pady=(8, 0))
    tk.Label(header, text="TECHDOM / DISCIPLINE PROTOCOL", font=("Bahnschrift", 18, "bold"), fg=TEXT, bg=UI_BG).pack(anchor="w", padx=14, pady=(0, 8))

    # Master activation toggle: controls whether PhraseLock appears after a
    # Windows unlock. Preview/Settings stay usable while disabled.
    enabled_var = tk.BooleanVar(value=cfg.get("enabled", True))
    status_var = tk.StringVar()

    toggle_frame = tk.Frame(root, bg=CARD_BG, highlightthickness=1, highlightbackground=BORDER)
    toggle_frame.pack(fill="x", padx=12, pady=(0, 6), ipady=4)
    tk.Label(toggle_frame, text="SYSTEM STATUS", font=("Consolas", 9, "bold"), fg=MUTED, bg=CARD_BG).pack(side="left", padx=(14, 8))
    toggle_btn = tk.Button(toggle_frame, width=14, font=("Consolas", 10, "bold"),
                           relief="flat", bd=0, cursor="hand2", padx=10, pady=4)
    toggle_btn.pack(side="right", padx=12)
    tk.Label(toggle_frame, textvariable=status_var, font=("Consolas", 9), fg=TEXT, bg=CARD_BG).pack(side="left", padx=(4, 0))

    def refresh_enabled_ui():
        if enabled_var.get():
            status_var.set("PhraseLock is active on Windows unlock")
            toggle_btn.configure(text="●  ENABLED", bg="#19e68c", fg="#04110a", activebackground="#39ffab")
        else:
            status_var.set("PhraseLock is disabled on Windows unlock")
            toggle_btn.configure(text="○  DISABLED", bg="#2b2b35", fg="#ff6b81", activebackground="#3a3a46")

    def toggle_enabled():
        enabled_var.set(not enabled_var.get())
        refresh_enabled_ui()

    toggle_btn.configure(command=toggle_enabled)
    refresh_enabled_ui()

    # Footer is packed BEFORE the notebook so it always keeps its space.
    footer = tk.Frame(root, bg=CARD_BG, highlightthickness=1, highlightbackground=BORDER)
    footer.pack(side="bottom", fill="x", padx=12, pady=(0, 12))

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    # ------------------------------------------------ scrollable tab plumbing
    tab_canvases = {}   # str(tab widget) -> its scroll canvas
    tab_by_key = {}     # "rules" -> tab widget

    def new_tab(key, title):
        outer = tk.Frame(notebook, bg=UI_BG)
        cv = tk.Canvas(outer, borderwidth=0, highlightthickness=0, bg=UI_BG, yscrollincrement=24)
        sb = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        inner = tk.Frame(cv, bg=UI_BG)
        win = cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        notebook.add(outer, text=title)
        tab_canvases[str(outer)] = cv
        tab_by_key[key] = outer
        return inner

    def on_mousewheel(event):
        """Wheel scrolls the page under the cursor (the visible tab)."""
        try:
            w = event.widget
            # A multi-line text box that can scroll itself keeps the wheel.
            if isinstance(w, tk.Text) and w.yview() != (0.0, 1.0):
                return
            cv = tab_canvases.get(notebook.select())
            if cv is None:
                return
            direction = -1 if event.delta > 0 else 1
            cv.yview_scroll(direction * max(1, abs(event.delta) // 120), "units")
        except tk.TclError:
            pass

    root.bind_all("<MouseWheel>", on_mousewheel)

    def pad(widget, **kw):
        widget.pack(anchor="w", padx=20, **kw)

    def heading(parent, text, color=ACCENT_2):
        tk.Label(parent, text=text, font=("Consolas", 12, "bold"), fg=color, bg=UI_BG).pack(anchor="w", padx=20, pady=(16, 5))

    def note(parent, text, color=MUTED, size=9):
        tk.Label(parent, text=text, font=("Consolas", size), fg=color, wraplength=620,
                 justify="left").pack(anchor="w", padx=20, pady=(0, 8))

    def style_entry(entry, ok):
        entry.configure(bg=INPUT_BG if ok else BAD_BG,
                        highlightthickness=1,
                        highlightbackground=BORDER if ok else DANGER,
                        highlightcolor=CYAN if ok else DANGER)

    # ======================================================================
    # TAB 1: PHRASES
    # ======================================================================
    t_phrases = new_tab("phrases", "  Phrases  ")

    title_var = tk.StringVar(value=cfg.get("title", DEFAULT_CONFIG["title"]))
    heading(t_phrases, "[01] DISPLAYED TITLE")
    pad(tk.Entry(t_phrases, textvariable=title_var, width=70), pady=(0, 6))

    heading(t_phrases, "[02] PHRASE PROTOCOL")
    note(t_phrases, "Use an external TXT/CSV/JSON file for easy editing/sharing, or keep phrases in the built-in list.")

    phrases_file_var = tk.StringVar(value=cfg.get("phrases_file", ""))
    file_frame = tk.Frame(t_phrases)
    file_frame.pack(anchor="w", padx=20, fill="x", pady=(0, 5))
    tk.Entry(file_frame, textvariable=phrases_file_var, width=54).pack(side="left")

    def choose_phrases_file():
        path = filedialog.askopenfilename(
            title="Choose phrase file",
            filetypes=[
                ("Phrase files", "*.txt *.csv *.json"),
                ("Text files", "*.txt"),
                ("CSV files", "*.csv"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if path:
            phrases_file_var.set(path)

    tk.Button(file_frame, text="Browse...", command=choose_phrases_file).pack(side="left", padx=(8, 0))
    pad(tk.Button(t_phrases, text="Disable external file (use built-in phrases)",
                  command=lambda: phrases_file_var.set("")), pady=(0, 10))

    pad(tk.Label(t_phrases, text="Built-in phrases (one per line):"))
    phrases_text = tk.Text(t_phrases, height=6, width=70)
    phrases_text.insert("1.0", "\n".join(cfg.get("phrases") or DEFAULT_CONFIG["phrases"]))
    pad(phrases_text, pady=(0, 10))

    difficulty_var = tk.StringVar(value=str(cfg.get("difficulty", "all")))
    pad(tk.Label(t_phrases, text="Phrase difficulty filter (needs a CSV/JSON file with a difficulty column):"), pady=(0, 3))
    pad(tk.OptionMenu(t_phrases, difficulty_var, "all", "easy", "normal", "hard", "extreme"), pady=(0, 16))

    # ======================================================================
    # TAB 2: LOOK (+ audio)
    # ======================================================================
    t_look = new_tab("look", "  Look  ")

    heading(t_look, "[01] THEME / HUD")
    theme_var = tk.StringVar(value=str(cfg.get("theme", "Cyber Red")))
    pad(tk.Label(t_look, text="Theme:"), pady=(0, 3))
    pad(tk.OptionMenu(t_look, theme_var, "Cyber Red", "Neon Pink", "Cyber Blue", "Matrix", "Dark Purple", "Blackout"), pady=(0, 8))
    font_var = tk.StringVar(value=str(cfg.get("font_family", "Consolas")))
    pad(tk.Label(t_look, text="Interface font:"), pady=(0, 3))
    pad(tk.OptionMenu(t_look, font_var, "Consolas", "Bahnschrift", "Segoe UI", "Courier New"), pady=(0, 8))
    ui_scale_var = tk.IntVar(value=max(75, min(150, int(cfg.get("ui_scale", 100) or 100))))
    scale_label_var = tk.StringVar(value=f"UI scale: {ui_scale_var.get()}%")
    pad(tk.Label(t_look, textvariable=scale_label_var), pady=(0, 3))
    pad(tk.Scale(t_look, from_=75, to=150, orient="horizontal", variable=ui_scale_var,
                 command=lambda v: scale_label_var.set(f"UI scale: {ui_scale_var.get()}%"),
                 length=260, showvalue=False), pady=(0, 8))
    scanlines_var = tk.BooleanVar(value=cfg.get("scanlines", True))
    glow_var = tk.BooleanVar(value=cfg.get("glow_effect", True))
    glitch_var = tk.BooleanVar(value=cfg.get("glitch_effect", False))
    pad(tk.Checkbutton(t_look, text="Scanline overlay", variable=scanlines_var))
    pad(tk.Checkbutton(t_look, text="Neon glow accents", variable=glow_var))
    pad(tk.Checkbutton(t_look, text="Glitch effect on errors", variable=glitch_var), pady=(0, 6))

    heading(t_look, "[02] BACKGROUND / PANEL")
    pad(tk.Label(t_look, text="Background images (optional - local files OR direct HTTP/HTTPS URLs):"))
    bg_list = list(media.background_sources(cfg))
    # Mirrors the list so that the autosave notices every change.
    bg_images_var = tk.StringVar(value="\n".join(bg_list))
    bg_frame = tk.Frame(t_look)
    bg_frame.pack(anchor="w", padx=20, pady=(0, 5), fill="x")
    bg_listbox = tk.Listbox(bg_frame, height=5, width=60, selectmode="extended", exportselection=False)
    bg_scroll = tk.Scrollbar(bg_frame, orient="vertical", command=bg_listbox.yview)
    bg_listbox.configure(yscrollcommand=bg_scroll.set)
    bg_listbox.pack(side="left")
    bg_scroll.pack(side="left", fill="y")

    def refresh_bg_list():
        bg_listbox.delete(0, "end")
        for item in bg_list:
            bg_listbox.insert("end", item)
        bg_images_var.set("\n".join(bg_list))

    def add_bg(items):
        changed = False
        for item in items:
            item = str(item).strip()
            if item and item not in bg_list:
                bg_list.append(item)
                changed = True
        if changed:
            refresh_bg_list()

    def choose_images():
        paths = filedialog.askopenfilenames(
            title="Choose background images",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")],
        )
        add_bg(paths)

    def add_image_url():
        url = simpledialog.askstring("Online background", "Paste a direct image URL (http:// or https://):", parent=root)
        if url and url.strip():
            add_bg([url.strip()])

    def remove_selected_images():
        for i in sorted(bg_listbox.curselection(), reverse=True):
            del bg_list[i]
        refresh_bg_list()

    def clear_images():
        bg_list.clear()
        refresh_bg_list()

    bg_buttons = tk.Frame(t_look)
    bg_buttons.pack(anchor="w", padx=20, pady=(0, 5))
    tk.Button(bg_buttons, text="Add files...", command=choose_images).pack(side="left")
    tk.Button(bg_buttons, text="Add URL...", command=add_image_url).pack(side="left", padx=(6, 0))
    tk.Button(bg_buttons, text="Remove selected", command=remove_selected_images).pack(side="left", padx=(6, 0))
    tk.Button(bg_buttons, text="Clear all (solid background)", command=clear_images).pack(side="left", padx=(6, 0))
    refresh_bg_list()
    note(t_look, "With several images, one is picked at random each time the lock appears "
                 "(never the same one twice in a row). For online media, use a direct file URL "
                 "(it must return the image itself, not a webpage).", size=8)
    pad(tk.Frame(t_look, height=6))
    bg_per_screen_var = tk.BooleanVar(value=bool(cfg.get("background_per_screen", False)))
    pad(tk.Checkbutton(t_look, text="Show a different random picture on each screen",
                       variable=bg_per_screen_var), pady=(0, 2))
    note(t_look, "Only matters when several screens are locked. Each screen gets its own picture "
                 "when there are enough images; otherwise some pictures are reused.", size=8)
    animate_gif_var = tk.BooleanVar(value=bool(cfg.get("animate_gif_backgrounds", True)))
    pad(tk.Checkbutton(t_look, text="Play animated GIF backgrounds",
                       variable=animate_gif_var), pady=(0, 2))
    note(t_look, "Add a .gif file or a direct .gif URL to the background list above. While the lock "
                 "is showing, the GIF plays on every locked screen. Turn this off to show only its "
                 "first frame (uses less CPU). Very large GIFs are shrunk or cut to save memory.", size=8)
    bg_mode_var = tk.StringVar(value=str(cfg.get("background_mode", "fill")).capitalize())
    pad(tk.Label(t_look, text="Image display mode (default for all screens):"), pady=(0, 3))
    pad(tk.OptionMenu(t_look, bg_mode_var, "Fill", "Fit", "Stretch", "Center", "Tile"), pady=(0, 4))
    note(t_look, "Fill: cover the screen, crop the overflow. Fit: whole image visible, bars around it. "
                 "Stretch: distorts. Center: original size. Tile: repeat.", size=8)
    # ---- lock screens (multi-monitor) ----
    connected = monitors.list_monitors()
    saved_screens = monitors.choices_from_cfg(cfg)
    primary_dev = next((m["device"] for m in connected if m["primary"]), None)
    all_saved = monitors.ALL in saved_screens
    panel_m, cover_ms = monitors.resolve_lock_monitors(saved_screens, connected)
    selected_now = {m["device"] for m in ([panel_m] if panel_m else []) + cover_ms}
    # Saved device names that are not plugged in right now are kept as-is, so an
    # unrelated autosave does not silently drop them.
    missing_saved = [c for c in saved_screens
                     if c not in (monitors.PRIMARY, monitors.ALL)
                     and c not in {m["device"] for m in connected}]

    pad(tk.Label(t_look, text="Show the lock on:"), pady=(0, 3))
    all_screens_var = tk.BooleanVar(value=all_saved and len(connected) > 0)
    screen_vars = {}
    screen_guard = {"busy": False}

    def on_all_toggled(*_):
        if screen_guard["busy"]:
            return
        screen_guard["busy"] = True
        try:
            if all_screens_var.get():
                for v in screen_vars.values():
                    v.set(True)
        finally:
            screen_guard["busy"] = False

    def on_screen_toggled(*_):
        if screen_guard["busy"]:
            return
        screen_guard["busy"] = True
        try:
            if not all(v.get() for v in screen_vars.values()):
                all_screens_var.set(False)
        finally:
            screen_guard["busy"] = False

    pad(tk.Checkbutton(t_look, text="All screens (includes monitors plugged in later)",
                       variable=all_screens_var), pady=(0, 2))
    saved_modes = cfg.get("screen_background_modes")
    saved_modes = saved_modes if isinstance(saved_modes, dict) else {}
    mode_vars = {}
    for n, m in enumerate(connected, start=1):
        v = tk.BooleanVar(value=m["device"] in selected_now)
        screen_vars[m["device"]] = v
        row = tk.Frame(t_look)
        row.pack(anchor="w", padx=20, pady=(0, 1))
        tk.Checkbutton(row, text=monitors.monitor_label(m, n), variable=v).pack(side="left")
        saved_mode = str(saved_modes.get(m["device"], "")).lower()
        mv = tk.StringVar(value=saved_mode.capitalize() if saved_mode in monitors.BACKGROUND_MODES else "Default")
        mode_vars[m["device"]] = mv
        tk.Label(row, text="   Image mode:").pack(side="left")
        tk.OptionMenu(row, mv, "Default", "Fill", "Fit", "Stretch", "Center", "Tile").pack(side="left")
    all_screens_var.trace_add("write", on_all_toggled)
    for v in screen_vars.values():
        v.trace_add("write", on_screen_toggled)

    def collect_screen_modes():
        # Modes saved for monitors that are not plugged in are kept untouched.
        out = {d: m for d, m in saved_modes.items() if d not in mode_vars}
        for device, var in mode_vars.items():
            mode = var.get().lower()
            if mode in monitors.BACKGROUND_MODES:
                out[device] = mode
        return out

    def collect_lock_screens():
        if connected and all_screens_var.get():
            return [monitors.ALL]
        picked = [d for d, v in screen_vars.items() if v.get()]
        if not picked and not missing_saved:
            return [monitors.PRIMARY]
        if picked == [primary_dev] and not missing_saved:
            return [monitors.PRIMARY]
        return picked + missing_saved

    note(t_look, "Tick one or several monitors. The phrase panel is shown on the primary screen "
                 "(or on the left-most ticked screen) and the other ticked screens show the "
                 "background. If a ticked monitor is unplugged it is skipped; if none is left, "
                 "the primary screen is used. \"Image mode\" sets how the background fits that screen "
                 "(Default = the global mode above).", size=8)
    pad(tk.Label(t_look, text="Text panel color:"))
    panel_color_var = tk.StringVar(value=cfg.get("panel_color", DEFAULT_CONFIG["panel_color"]))
    color_frame = tk.Frame(t_look)
    color_frame.pack(anchor="w", padx=20, pady=(0, 4), fill="x")
    color_entry = tk.Entry(color_frame, textvariable=panel_color_var, width=15)
    color_entry.pack(side="left")

    def choose_color():
        c = colorchooser.askcolor(color=panel_color_var.get() or "#1a1a2e")
        if c and c[1]:
            panel_color_var.set(c[1])

    tk.Button(color_frame, text="Choose...", command=choose_color).pack(side="left", padx=(8, 0))
    color_hint_var = tk.StringVar()
    color_hint = tk.Label(t_look, textvariable=color_hint_var, font=("Consolas", 8), fg=DANGER)
    pad(color_hint, pady=(0, 10))

    def validate_color(*_):
        ok = color_ok(panel_color_var.get())
        style_entry(color_entry, ok)
        color_hint_var.set("" if ok else "Unknown colour. Use a hex value like #1a1a2e or a colour name.")
        return ok

    panel_color_var.trace_add("write", validate_color)
    validate_color()

    panel_opacity_var = tk.IntVar(value=max(10, min(100, int(cfg.get("panel_opacity", 100) or 100))))
    opacity_label_var = tk.StringVar(value=f"Opacity: {panel_opacity_var.get()}%")
    opacity_frame = tk.Frame(t_look)
    opacity_frame.pack(anchor="w", padx=20, pady=(0, 10), fill="x")
    tk.Label(opacity_frame, textvariable=opacity_label_var).pack(side="left")
    tk.Scale(opacity_frame, from_=10, to=100, orient="horizontal", variable=panel_opacity_var,
             command=lambda v: opacity_label_var.set(f"Opacity: {panel_opacity_var.get()}%"),
             length=260, showvalue=False, resolution=1).pack(side="left", padx=(12, 0))

    heading(t_look, "[03] AUDIO")
    play_sound_var = tk.BooleanVar(value=cfg.get("play_sound", False))
    pad(tk.Checkbutton(t_look, text="Play a sound when successfully unlocked", variable=play_sound_var))
    sound_error_var = tk.BooleanVar(value=cfg.get("sound_on_error", False))
    pad(tk.Checkbutton(t_look, text="Play an error sound on a typo", variable=sound_error_var), pady=(0, 6))

    success_sound_var = tk.StringVar(value=cfg.get("success_sound", ""))
    error_sound_var = tk.StringVar(value=cfg.get("error_sound", ""))

    def choose_audio(var):
        path = filedialog.askopenfilename(title="Choose audio", filetypes=[("Audio files", "*.wav;*.mp3"), ("WAV files", "*.wav"), ("MP3 files", "*.mp3"), ("All files", "*.*")])
        if path:
            var.set(path)

    def test_audio(var):
        value = var.get().strip()
        if not value:
            messagebox.showwarning("PhraseLock Audio", "Choose an audio file or enter a direct WAV/MP3 URL first.", parent=root)
            return
        try:
            # Settings.exe must launch PhraseLock.exe for --test-audio when frozen.
            if getattr(sys, 'frozen', False):
                base = os.path.dirname(sys.executable)
                target = sys.executable
                command = [target, '--test-audio', value]
                cwd = base
            else:
                target = os.path.abspath(os.path.join(os.path.dirname(__file__), 'phrase_lock.py'))
                command = [sys.executable, target, '--test-audio', value]
                cwd = os.path.dirname(target)
            subprocess.Popen(command, cwd=cwd, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception as exc:
            messagebox.showerror("PhraseLock Audio", f"Could not start audio test:\n{exc}", parent=root)

    def set_audio_url(var, label):
        url = simpledialog.askstring(label, "Paste a direct WAV/MP3 URL (http:// or https://):", parent=root)
        if url and url.strip():
            var.set(url.strip())

    def sound_row(label, var, url_title, pady):
        row = tk.Frame(t_look)
        row.pack(anchor="w", padx=20, pady=pady, fill="x")
        tk.Label(row, text=label, width=14, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, width=30).pack(side="left", padx=6)
        tk.Button(row, text="Browse", command=lambda: choose_audio(var)).pack(side="left")
        tk.Button(row, text="URL...", command=lambda: set_audio_url(var, url_title)).pack(side="left", padx=(6, 0))
        tk.Button(row, text="TEST", command=lambda: test_audio(var)).pack(side="left", padx=(6, 0))

    sound_row("Success sound:", success_sound_var, "Online success sound", (5, 2))
    sound_row("Error sound:", error_sound_var, "Online error sound", (2, 6))
    note(t_look, "Local or direct WAV/MP3 URLs are supported. Remote audio is cached only when needed.", size=8)

    # ======================================================================
    # TAB 3: RULES
    # ======================================================================
    t_rules = new_tab("rules", "  Rules  ")

    heading(t_rules, "[01] CHALLENGE")
    repeats_var = tk.IntVar(value=cfg.get("required_repeats", 1))
    pad(tk.Label(t_rules, text="Number of rounds (each with a random sentence):"))
    pad(tk.Spinbox(t_rules, from_=1, to=20, textvariable=repeats_var, width=5), pady=(0, 8))
    reset_on_error_var = tk.BooleanVar(value=cfg.get("reset_on_error", True))
    pad(tk.Checkbutton(t_rules, text="Reset the counter to 0 on a typo", variable=reset_on_error_var))
    strict_mode_var = tk.BooleanVar(value=cfg.get("strict_mode", False))
    pad(tk.Checkbutton(t_rules, text="Strict Mode: any typo resets the whole challenge", variable=strict_mode_var))
    weighting_var = tk.BooleanVar(value=cfg.get("difficulty_weighting", True))
    pad(tk.Checkbutton(t_rules, text="Weight phrase selection by difficulty "
                                    "(easy=1, normal=2, hard=3, extreme=4)", variable=weighting_var), pady=(0, 6))
    heading(t_rules, "[02] INPUT CONTROL")
    disable_paste_var = tk.BooleanVar(value=cfg.get("disable_paste", False))
    pad(tk.Checkbutton(t_rules, text="Disable paste (force the sentence to be typed manually)", variable=disable_paste_var))
    case_insensitive_var = tk.BooleanVar(value=cfg.get("case_insensitive", False))
    pad(tk.Checkbutton(t_rules, text="Ignore case and accents when checking", variable=case_insensitive_var), pady=(0, 8))
    min_delay_var = tk.IntVar(value=cfg.get("min_delay_seconds", 0))
    pad(tk.Label(t_rules, text="Minimum delay before Submit is enabled (seconds):"))
    pad(tk.Spinbox(t_rules, from_=0, to=60, textvariable=min_delay_var, width=5), pady=(0, 6))

    heading(t_rules, "[03] CHALLENGE LIMITS")
    max_attempts_var = tk.IntVar(value=max(0, int(cfg.get("max_attempts", 0) or 0)))
    pad(tk.Label(t_rules, text="Maximum wrong attempts (0 = unlimited):"), pady=(0, 3))
    pad(tk.Spinbox(t_rules, from_=0, to=100, textvariable=max_attempts_var, width=5), pady=(0, 8))
    lockout_seconds_var = tk.IntVar(value=max(1, int(cfg.get("lockout_seconds", 15) or 15)))
    pad(tk.Label(t_rules, text="Retry lockout after reaching the limit (seconds):"), pady=(0, 3))
    pad(tk.Spinbox(t_rules, from_=1, to=300, textvariable=lockout_seconds_var, width=5), pady=(0, 6))

    heading(t_rules, "[04] DAILY GOAL")
    daily_goal_var = tk.IntVar(value=max(1, int(cfg.get("daily_goal", 1) or 1)))
    pad(tk.Label(t_rules, text="Daily successful-unlock goal:"), pady=(0, 3))
    pad(tk.Spinbox(t_rules, from_=1, to=50, textvariable=daily_goal_var, width=5), pady=(0, 6))

    heading(t_rules, "[05] SCHEDULE MATRIX")
    schedule_enabled_var = tk.BooleanVar(value=cfg.get("schedule_enabled", False))
    pad(tk.Checkbutton(t_rules, text="Only trigger the lock during specific days/hours", variable=schedule_enabled_var), pady=(0, 5))

    days_frame = tk.Frame(t_rules)
    days_frame.pack(anchor="w", padx=20, pady=(0, 8))
    configured_days = set(cfg.get("schedule_days") or list(range(7)))
    day_vars = []
    for i, label in enumerate(DAY_LABELS):
        v = tk.BooleanVar(value=i in configured_days)
        day_vars.append(v)
        tk.Checkbutton(days_frame, text=label, variable=v).grid(row=0, column=i, padx=4)

    time_frame = tk.Frame(t_rules)
    time_frame.pack(anchor="w", padx=20, pady=(0, 4))
    tk.Label(time_frame, text="From (HH:MM):").pack(side="left")
    schedule_start_var = tk.StringVar(value=cfg.get("schedule_start", "00:00"))
    start_entry = tk.Entry(time_frame, textvariable=schedule_start_var, width=7)
    start_entry.pack(side="left", padx=(5, 15))
    tk.Label(time_frame, text="To (HH:MM):").pack(side="left")
    schedule_end_var = tk.StringVar(value=cfg.get("schedule_end", "23:59"))
    end_entry = tk.Entry(time_frame, textvariable=schedule_end_var, width=7)
    end_entry.pack(side="left", padx=(5, 0))

    schedule_hint_var = tk.StringVar()
    schedule_hint = tk.Label(t_rules, textvariable=schedule_hint_var, font=("Consolas", 9), fg=MUTED,
                             wraplength=620, justify="left")
    pad(schedule_hint, pady=(0, 6))

    def validate_times(*_):
        """Live check of both time fields; returns ((h, m), (h, m)) or None parts."""
        s = parse_hhmm(schedule_start_var.get())
        e = parse_hhmm(schedule_end_var.get())
        style_entry(start_entry, s is not None)
        style_entry(end_entry, e is not None)
        if s is None or e is None:
            bad = []
            if s is None:
                bad.append("Start")
            if e is None:
                bad.append("End")
            schedule_hint_var.set(f"{' and '.join(bad)} time invalid. Use HH:MM from 00:00 to 23:59 (for example 08:30).")
            schedule_hint.configure(fg=DANGER)
        elif s == e:
            schedule_hint_var.set("Start and end are identical: the lock would only trigger at that exact minute.")
            schedule_hint.configure(fg=WARN)
        elif s > e:
            schedule_hint_var.set(f"Overnight window: {fmt_hhmm(s)} until {fmt_hhmm(e)} the next day.")
            schedule_hint.configure(fg=CYAN)
        else:
            schedule_hint_var.set(f"Active from {fmt_hhmm(s)} to {fmt_hhmm(e)}.")
            schedule_hint.configure(fg=MUTED)
        return s, e

    schedule_start_var.trace_add("write", validate_times)
    schedule_end_var.trace_add("write", validate_times)
    validate_times()

    heading(t_rules, "[06] FOCUS SESSION")
    focus_enabled_var = tk.BooleanVar(value=cfg.get("focus_session_enabled", False))
    pad(tk.Checkbutton(t_rules, text="Start a Focus Session after a successful unlock", variable=focus_enabled_var), pady=(0, 5))
    focus_minutes_var = tk.IntVar(value=max(1, int(cfg.get("focus_session_minutes", 45) or 45)))
    pad(tk.Label(t_rules, text="Focus Session duration (minutes):"), pady=(0, 3))
    pad(tk.Spinbox(t_rules, from_=1, to=240, textvariable=focus_minutes_var, width=5), pady=(0, 6))
    note(t_rules, "Optional apps to keep closed during a Focus Session (one .exe name per line):")
    blocked_apps_text = tk.Text(t_rules, height=3, width=70)
    blocked_apps_text.insert('1.0', '\n'.join(cfg.get('focus_block_apps') or []))
    pad(blocked_apps_text, pady=(0, 6))

    heading(t_rules, "[07] IDLE LOCK", DANGER)
    idle_enabled_var = tk.BooleanVar(value=cfg.get("idle_lock_enabled", False))
    pad(tk.Checkbutton(t_rules, text="Lock Windows automatically after inactivity", variable=idle_enabled_var), pady=(0, 5))
    idle_minutes_var = tk.IntVar(value=max(1, int(cfg.get("idle_lock_minutes", 30) or 30)))
    pad(tk.Label(t_rules, text="Idle time before Windows Lock (minutes):"), pady=(0, 3))
    pad(tk.Spinbox(t_rules, from_=1, to=240, textvariable=idle_minutes_var, width=5), pady=(0, 16))

    # ======================================================================
    # TAB 4: PROTECTION
    # ======================================================================
    t_prot = new_tab("protection", "  Protection  ")

    heading(t_prot, "[01] EMERGENCY OVERRIDE", DANGER)
    note(t_prot, "This password is stored only as a salted hash. It immediately unlocks PhraseLock without typing the phrase. "
                 "Set one BEFORE enabling Strict Mode or auto-protection.")

    emergency_status = "configured" if cfg.get("emergency_password_hash") else "not configured"
    emergency_status_var = tk.StringVar(value=f"Emergency password: {emergency_status}")
    pad(tk.Label(t_prot, textvariable=emergency_status_var, font=("Consolas", 9)))

    pw_frame = tk.Frame(t_prot)
    pw_frame.pack(anchor="w", padx=20, pady=(5, 5))
    tk.Label(pw_frame, text="New password:", width=14, anchor="w").pack(side="left")
    emergency_pw_var = tk.StringVar()
    tk.Entry(pw_frame, textvariable=emergency_pw_var, show="*", width=25).pack(side="left", padx=8)

    pw2_frame = tk.Frame(t_prot)
    pw2_frame.pack(anchor="w", padx=20, pady=(0, 5))
    tk.Label(pw2_frame, text="Confirm:", width=14, anchor="w").pack(side="left")
    emergency_pw2_var = tk.StringVar()
    tk.Entry(pw2_frame, textvariable=emergency_pw2_var, show="*", width=25).pack(side="left", padx=8)

    clear_pw_var = tk.BooleanVar(value=False)
    pad(tk.Checkbutton(t_prot, text="Remove the emergency password on Save", variable=clear_pw_var, font=("Consolas", 9)))

    heading(t_prot, "[02] WATCHDOG / AUTO-PROTECTION", DANGER)
    note(t_prot, "If enabled, a background watchdog restarts the protection monitor if it disappears. "
                 "Use with caution: disable this option before uninstalling PhraseLock.", color=WARN)
    auto_protection_var = tk.BooleanVar(value=cfg.get("auto_protection", False))
    pad(tk.Checkbutton(t_prot, text="Restart PhraseLock if its process is terminated", variable=auto_protection_var), pady=(0, 6))

    heading(t_prot, "[03] PAUSE / PANIC", DANGER)
    note(t_prot, "Pause PhraseLock for a while WITHOUT typing the phrase or the emergency password. "
                 "From the tray icon: right-click > Pause PhraseLock. With a hotkey: press it once to "
                 "pause (even while the lock screen is showing) and again to resume. While paused "
                 "nothing locks, not even after a Windows lock. It works only while PhraseLock is running.",
         color=WARN)
    pause_hotkey_var = tk.StringVar(value=str(cfg.get("pause_hotkey", "") or ""))
    pad(tk.Label(t_prot, text="Pause hotkey (e.g. Ctrl+Alt+P; empty = no hotkey):"), pady=(0, 3))
    pad(tk.Entry(t_prot, textvariable=pause_hotkey_var, width=24), pady=(0, 3))
    note(t_prot, "Needs Ctrl, Alt or Win plus one key (letter, digit, F1-F24, Space...). If another "
                 "program already uses the combination, PhraseLock logs it and the hotkey stays off.", size=8)
    pause_minutes_var = tk.IntVar(value=max(1, int(cfg.get("pause_minutes", 15) or 15)))
    pad(tk.Label(t_prot, text="Hotkey pause duration (minutes):"), pady=(0, 3))
    pad(tk.Spinbox(t_prot, from_=1, to=240, textvariable=pause_minutes_var, width=5), pady=(0, 6))

    heading(t_prot, "[04] BOOT SEQUENCE")
    startup_status_var = tk.StringVar(
        value="Currently: enabled at logon" if is_startup_enabled() else "Currently: not enabled at logon"
    )
    pad(tk.Label(t_prot, textvariable=startup_status_var, font=("Consolas", 9), fg=MUTED))

    startup_btn_frame = tk.Frame(t_prot)
    startup_btn_frame.pack(anchor="w", padx=20, pady=(5, 16))

    def on_enable_startup():
        exe_path = filedialog.askopenfilename(
            title="Select PhraseLock.exe", filetypes=[("Executable", "*.exe")]
        )
        if not exe_path:
            return
        try:
            enable_startup(exe_path)
            startup_status_var.set("Currently: enabled at logon")
            messagebox.showinfo("Startup", "PhraseLock will now launch automatically at logon.")
        except Exception as e:
            messagebox.showerror("Startup", f"Could not create the startup shortcut:\n{e}")

    def on_disable_startup():
        try:
            disable_startup()
            startup_status_var.set("Currently: not enabled at logon")
            messagebox.showinfo("Startup", "Auto-start removed.")
        except Exception as e:
            messagebox.showerror("Startup", f"Could not remove the startup shortcut:\n{e}")

    tk.Button(startup_btn_frame, text="Enable at startup...", command=on_enable_startup).pack(side="left")
    tk.Button(startup_btn_frame, text="Disable at startup", command=on_disable_startup).pack(side="left", padx=(10, 0))

    # ======================================================================
    # TAB 5: STATS (rebuilt every time the tab is opened)
    # ======================================================================
    t_stats = tk.Frame(notebook, bg=UI_BG)
    notebook.add(t_stats, text="  Stats  ")
    tab_by_key["stats"] = t_stats
    stats_holder = tk.Frame(t_stats, bg=UI_BG)
    stats_holder.pack(fill="both", expand=True, padx=16, pady=12)

    def refresh_stats():
        for child in stats_holder.winfo_children():
            child.destroy()
        try:
            with open(STATS_PATH, "r", encoding="utf-8") as f:
                stats = json.load(f)
            if not isinstance(stats, list):
                stats = []
        except Exception:
            stats = []
        stats = [s for s in stats if isinstance(s, dict)]

        current, best = phrase_lock.get_streak()
        progress = phrase_lock.get_progress()
        level, level_xp, level_need = phrase_lock.get_xp_level(progress.get("xp", 0))
        badges = phrase_lock.badges_for(stats, current, best)
        total = len(stats)
        total_time = sum(float(s.get("duration_seconds", 0) or 0) for s in stats)
        first_try_count = sum(1 for s in stats if s.get("first_try") and not s.get("emergency"))
        emergency_count = sum(1 for s in stats if s.get("emergency"))
        wpm_values = [s["wpm"] for s in stats if isinstance(s.get("wpm"), (int, float))]
        avg_wpm = f"{sum(wpm_values) / len(wpm_values):.0f}" if wpm_values else "-"

        cards = tk.Frame(stats_holder, bg=UI_BG)
        cards.pack(fill="x")

        def card(col, label, value):
            box = tk.Frame(cards, bg=CARD_BG, highlightthickness=1, highlightbackground=BORDER)
            box.grid(row=0, column=col, padx=(0 if col == 0 else 8, 0), sticky="nsew")
            cards.grid_columnconfigure(col, weight=1, uniform="card")
            tk.Label(box, text=str(value), font=("Bahnschrift", 20, "bold"), fg=CYAN, bg=CARD_BG).pack(pady=(10, 0))
            tk.Label(box, text=label, font=("Consolas", 8), fg=MUTED, bg=CARD_BG).pack(pady=(0, 10))

        card(0, "STREAK (DAYS)", current)
        card(1, "BEST STREAK", best)
        card(2, "UNLOCKS", total)
        card(3, "FIRST TRY", first_try_count)
        card(4, "AVG WPM", avg_wpm)

        tk.Label(
            stats_holder,
            text=(f"Level {level}   XP {level_xp}/{level_need}   (total {progress.get('xp', 0)})\n"
                  f"Daily goal: {progress.get('goal_progress', 0)} / {cfg.get('daily_goal', 1)}   |   "
                  f"Emergency unlocks: {emergency_count}   |   Time typing: {total_time:.0f}s\n"
                  f"Badges: {', '.join(badges) if badges else 'None yet'}"),
            font=("Consolas", 9), fg=TEXT, justify="left"
        ).pack(anchor="w", pady=(12, 8))

        # ---- last 7 days chart: first-try (accent) at the bottom, typos on top
        chart_h = 200
        chart = tk.Canvas(stats_holder, height=chart_h, bg=CARD_BG,
                          highlightthickness=1, highlightbackground=BORDER)
        chart.pack(fill="x", pady=(0, 10))
        series = phrase_lock.weekly_series(stats, days=7)
        typo_color = "#3a1f28"

        def draw_chart(_event=None):
            chart.delete("all")
            w = chart.winfo_width()
            if w < 100:  # not laid out yet
                w = 700
            pad_l, pad_r, pad_t, pad_b = 40, 20, 44, 40
            plot_w = max(10, w - pad_l - pad_r)
            plot_h = chart_h - pad_t - pad_b
            slot = plot_w / len(series)
            bar_w = slot * 0.55
            y_base = pad_t + plot_h
            max_total = max([b["total"] for b in series] + [1])
            axis_max = max_total if max_total <= 4 else -(-max_total // 4) * 4
            steps = axis_max if axis_max <= 4 else 4
            for i in range(steps + 1):
                y = pad_t + plot_h * (1 - i / steps)
                chart.create_line(pad_l, y, w - pad_r, y, fill=BORDER)
                chart.create_text(pad_l - 6, y, anchor="e", text=str(round(axis_max * i / steps)),
                                  fill=MUTED, font=("Consolas", 8))
            for i, b in enumerate(series):
                cx = pad_l + slot * (i + 0.5)
                x0, x1 = cx - bar_w / 2, cx + bar_w / 2
                total_h = plot_h * b["total"] / axis_max
                ft_h = plot_h * b["first_try"] / axis_max
                if ft_h > 0:
                    chart.create_rectangle(x0, y_base - ft_h, x1, y_base, fill=ACCENT, outline="")
                if total_h > ft_h:
                    chart.create_rectangle(x0, y_base - total_h, x1, y_base - ft_h, fill=typo_color, outline="")
                chart.create_text(cx, y_base + 12, text=b["label"], fill=TEXT, font=("Consolas", 9, "bold"))
                chart.create_text(cx, y_base + 26, text=b["date"][5:], fill=MUTED, font=("Consolas", 7))
                metrics = []
                if b["wpm"] is not None:
                    metrics.append(f"{b['wpm']:.0f}wpm")
                if b["accuracy"] is not None:
                    metrics.append(f"{b['accuracy']:.0f}%")
                if metrics:
                    chart.create_text(cx, y_base - total_h - 8, text=" ".join(metrics),
                                      fill=CYAN, font=("Consolas", 7, "bold"))
                if b["total"]:
                    chart.create_text(cx, y_base - total_h - 20, text=str(b["total"]),
                                      fill=TEXT, font=("Consolas", 8, "bold"))
            chart.create_text(pad_l, 12, anchor="w", text="Last 7 days", fill=MUTED, font=("Consolas", 8, "bold"))
            chart.create_rectangle(pad_l + 90, 6, pad_l + 102, 18, fill=ACCENT, outline="")
            chart.create_text(pad_l + 108, 12, anchor="w", text="first try", fill=TEXT, font=("Consolas", 8))
            chart.create_rectangle(pad_l + 170, 6, pad_l + 182, 18, fill=typo_color, outline="")
            chart.create_text(pad_l + 188, 12, anchor="w", text="had typo", fill=TEXT, font=("Consolas", 8))

        chart.bind("<Configure>", draw_chart)
        draw_chart()

        # ---- recent unlocks
        list_frame = tk.Frame(stats_holder, bg=UI_BG)
        list_frame.pack(fill="both", expand=True)
        lb_scroll = ttk.Scrollbar(list_frame, orient="vertical")
        listbox = tk.Listbox(list_frame, bg=INPUT_BG, fg=TEXT, selectbackground=ACCENT,
                             highlightthickness=0, borderwidth=0, font=("Consolas", 9),
                             yscrollcommand=lb_scroll.set)
        lb_scroll.configure(command=listbox.yview)
        lb_scroll.pack(side="right", fill="y")
        listbox.pack(side="left", fill="both", expand=True)
        for s in reversed(stats[-50:]):
            mode = "emergency" if s.get("emergency") else ("first try" if s.get("first_try") else "had typo")
            extra = f"  -  {s['wpm']:.0f} wpm" if isinstance(s.get("wpm"), (int, float)) else ""
            listbox.insert(
                "end",
                f"{s.get('timestamp', '?')}  -  {s.get('rounds', '?')} round(s), "
                f"{s.get('duration_seconds', '?')}s  -  {mode}{extra}",
            )
        if not stats:
            listbox.insert("end", "No unlocks recorded yet.")

    def on_tab_changed(_event=None):
        if notebook.select() == str(t_stats):
            refresh_stats()

    notebook.bind("<<NotebookTabChanged>>", on_tab_changed)

    # ======================================================================
    # actions
    # ======================================================================
    def launch_manual_lock():
        """Launch the lock overlay mode of this same executable."""
        try:
            script = os.path.abspath(phrase_lock.__file__)
            if getattr(sys, "frozen", False):
                exe = sys.executable
                command = [exe, "--lock"]
                cwd = os.path.dirname(exe)
            else:
                command = [sys.executable, script, "--lock"]
                cwd = os.path.dirname(script)
            subprocess.Popen(
                command,
                cwd=cwd,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                close_fds=True,
            )
        except Exception as e:
            messagebox.showerror("Lock Now", f"Could not start PhraseLock:\n{e}")

    def on_preview():
        # Preview in a separate process: Tk must not create a second root here.
        try:
            script = os.path.abspath(phrase_lock.__file__)
            if getattr(sys, "frozen", False):
                exe = sys.executable
                command = [exe, "--preview"]
                cwd = os.path.dirname(exe)
            else:
                command = [sys.executable, script, "--preview"]
                cwd = os.path.dirname(script)
            subprocess.Popen(
                command,
                cwd=cwd,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            messagebox.showerror("Preview", f"Could not start preview:\n{e}")

    def collect_cfg():
        raw_phrases = phrases_text.get("1.0", "end").splitlines()
        phrases = [p.strip() for p in raw_phrases if p.strip()]
        if not phrases:
            phrases = list(DEFAULT_CONFIG["phrases"])
        start_t = parse_hhmm(schedule_start_var.get())
        end_t = parse_hhmm(schedule_end_var.get())
        return {
            "enabled": enabled_var.get(),
            "title": title_var.get().strip() or DEFAULT_CONFIG["title"],
            "phrases": phrases,
            "phrases_file": phrases_file_var.get().strip(),
            "background_images": list(bg_list),
            "background_image": bg_list[0] if bg_list else "",
            "background_mode": bg_mode_var.get().lower(),
            "background_per_screen": bg_per_screen_var.get(),
            "animate_gif_backgrounds": animate_gif_var.get(),
            "screen_background_modes": collect_screen_modes(),
            "lock_screens": collect_lock_screens(),
            "panel_color": panel_color_var.get().strip() or DEFAULT_CONFIG["panel_color"],
            "panel_opacity": num(panel_opacity_var, 100, 10, 100),
            "required_repeats": num(repeats_var, 1, 1, 20),
            "reset_on_error": reset_on_error_var.get(),
            "disable_paste": disable_paste_var.get(),
            "case_insensitive": case_insensitive_var.get(),
            "min_delay_seconds": num(min_delay_var, 0, 0, 60),
            "play_sound": play_sound_var.get(),
            "schedule_enabled": schedule_enabled_var.get(),
            "schedule_days": [i for i, v in enumerate(day_vars) if v.get()] or list(range(7)),
            # Normalised to zero-padded HH:MM; if invalid (only possible while
            # the schedule is off) keep the previously saved value.
            "schedule_start": fmt_hhmm(start_t) if start_t else cfg.get("schedule_start", "00:00"),
            "schedule_end": fmt_hhmm(end_t) if end_t else cfg.get("schedule_end", "23:59"),
            "emergency_password_salt": cfg.get("emergency_password_salt", ""),
            "emergency_password_hash": cfg.get("emergency_password_hash", ""),
            "emergency_password_iterations": cfg.get("emergency_password_iterations", DEFAULT_CONFIG["emergency_password_iterations"]),
            "auto_protection": auto_protection_var.get(),
            "daily_goal": num(daily_goal_var, 1, 1, 50),
            "difficulty": difficulty_var.get(),
            "difficulty_weighting": weighting_var.get(),
            "strict_mode": strict_mode_var.get(),
            "max_attempts": num(max_attempts_var, 0, 0, 100),
            "lockout_seconds": num(lockout_seconds_var, 15, 1, 300),
            "theme": theme_var.get(),
            "font_family": font_var.get(),
            "ui_scale": num(ui_scale_var, 100, 75, 150),
            "scanlines": scanlines_var.get(),
            "glow_effect": glow_var.get(),
            "glitch_effect": glitch_var.get(),
            "sound_on_error": sound_error_var.get(),
            "success_sound": success_sound_var.get().strip(),
            "error_sound": error_sound_var.get().strip(),
            "focus_session_enabled": focus_enabled_var.get(),
            "focus_session_minutes": num(focus_minutes_var, 45, 1, 240),
            "focus_block_apps": [x.strip() for x in blocked_apps_text.get('1.0', 'end').splitlines() if x.strip()],
            "idle_lock_enabled": idle_enabled_var.get(),
            "idle_lock_minutes": num(idle_minutes_var, 30, 1, 240),
            "pause_hotkey": hotkeys.normalize_hotkey(pause_hotkey_var.get()),
            "pause_minutes": num(pause_minutes_var, 15, 1, 240),
        }

    def validation_problem():
        """Return (tab_key, message) for the first blocking problem, else None."""
        if schedule_enabled_var.get():
            s, e = validate_times()
            if s is None or e is None:
                return "rules", "The schedule start/end must be valid HH:MM times (00:00 to 23:59)."
        if not validate_color():
            return "look", "The panel colour is not valid. Use a hex value like #1a1a2e."
        typed = pause_hotkey_var.get().strip()
        if typed and not hotkeys.normalize_hotkey(typed):
            return "protection", ("The pause hotkey is not valid. Use Ctrl, Alt or Win plus one key, "
                                  "for example Ctrl+Alt+P.")
        return None

    saved_msg_var = tk.StringVar()
    saved_clear = {"job": None}

    def flash_saved():
        saved_msg_var.set("Saved " + datetime.now().strftime("%H:%M:%S"))
        if saved_clear["job"]:
            root.after_cancel(saved_clear["job"])
        saved_clear["job"] = root.after(4000, lambda: saved_msg_var.set(""))

    def on_save(event=None):
        nonlocal cfg
        problem = validation_problem()
        if problem:
            key, message = problem
            notebook.select(tab_by_key[key])
            messagebox.showerror("Cannot save", message, parent=root)
            return

        # Start from the existing config so keys without a UI control
        # (sound_volume, manual_lock_hotkey, xp...) are not reset on Save.
        new_cfg = {**cfg, **collect_cfg()}

        if clear_pw_var.get():
            new_cfg.update({
                "emergency_password_salt": "",
                "emergency_password_hash": "",
            })
        elif emergency_pw_var.get() or emergency_pw2_var.get():
            if emergency_pw_var.get() != emergency_pw2_var.get():
                notebook.select(tab_by_key["protection"])
                messagebox.showerror("Emergency password", "The two passwords do not match.", parent=root)
                return
            if len(emergency_pw_var.get()) < 6:
                notebook.select(tab_by_key["protection"])
                messagebox.showerror("Emergency password", "Use at least 6 characters.", parent=root)
                return
            new_cfg.update(phrase_lock.set_emergency_password(emergency_pw_var.get()))

        save_config(new_cfg)
        cfg = new_cfg
        if new_cfg.get("enabled", True):
            try:
                ensure_phrase_lock_monitor()
            except Exception as e:
                messagebox.showwarning("PhraseLock monitor", f"Settings were saved, but the background monitor could not be started:\n{e}", parent=root)
        emergency_pw_var.set("")
        emergency_pw2_var.set("")
        clear_pw_var.set(False)
        emergency_status_var.set(
            "Emergency password: configured" if cfg.get("emergency_password_hash")
            else "Emergency password: not configured"
        )
        # Show the normalised times back in the fields.
        schedule_start_var.set(cfg.get("schedule_start", "00:00"))
        schedule_end_var.set(cfg.get("schedule_end", "23:59"))
        flash_saved()

    # ---------------------------------------------------------------- footer
    def footer_btn(text, command, side, bg=CARD_ALT, fg=TEXT):
        tk.Button(footer, text=text, command=command, bg=bg, fg=fg,
                  activebackground=ACCENT, activeforeground="white",
                  relief="flat", bd=0, padx=18, pady=7, cursor="hand2",
                  font=("Consolas", 10, "bold")).pack(side=side, padx=(10, 0) if side == "left" else (0, 10), pady=10)

    footer_btn("SAVE", on_save, "left", bg=ACCENT, fg="white")
    footer_btn("PREVIEW", on_preview, "left")
    footer_btn("EXPORT", lambda: backup.export_dialog(root, lambda: {**cfg, **collect_cfg()}, validation_problem), "left")
    footer_btn("IMPORT", lambda: backup.import_dialog(root) and root.destroy(), "left")
    tk.Label(footer, textvariable=saved_msg_var, font=("Consolas", 9), fg="#19e68c", bg=CARD_BG).pack(side="left", padx=14)
    footer_btn("[ LOCK NOW ]", launch_manual_lock, "right")

    root.bind("<Control-s>", on_save)
    
    # ------------------------------------------------------------ autosave
    autosave = {"job": None}

    watched_vars = [
        enabled_var, title_var, phrases_file_var, difficulty_var, theme_var, font_var,
        ui_scale_var, scanlines_var, glow_var, glitch_var, bg_images_var, bg_mode_var,
        all_screens_var, *screen_vars.values(), bg_per_screen_var, animate_gif_var, *mode_vars.values(), panel_color_var, panel_opacity_var, play_sound_var, sound_error_var,
        success_sound_var, error_sound_var, repeats_var, reset_on_error_var,
        strict_mode_var, weighting_var, disable_paste_var, case_insensitive_var,
        min_delay_var, max_attempts_var, lockout_seconds_var, daily_goal_var,
        schedule_enabled_var, schedule_start_var, schedule_end_var, focus_enabled_var,
        focus_minutes_var, idle_enabled_var, idle_minutes_var, auto_protection_var,
        pause_hotkey_var, pause_minutes_var,
        *day_vars,
    ]

    def do_autosave():
        nonlocal cfg
        autosave["job"] = None
        try:
            # Half-typed or invalid values (bad colour, bad HH:MM) are skipped
            # silently; they get saved as soon as they become valid.
            if validation_problem():
                return
            new_cfg = {**cfg, **collect_cfg()}
            if new_cfg == cfg:
                return
            was_enabled = cfg.get("enabled", True)
            save_config(new_cfg)
            cfg = new_cfg
            if new_cfg.get("enabled", True) and not was_enabled:
                try:
                    ensure_phrase_lock_monitor()
                except Exception:
                    pass
            flash_saved()
        except Exception as exc:
            try:
                phrase_lock.log(f"Autosave failed: {exc}")
            except Exception:
                pass

    def schedule_autosave(*_):
        if autosave["job"]:
            root.after_cancel(autosave["job"])
        autosave["job"] = root.after(400, do_autosave)

    for v in watched_vars:
        v.trace_add("write", schedule_autosave)

    # Multi-line boxes don't have variables, so hook the keyboard instead.
    for txt in (phrases_text, blocked_apps_text):
        txt.bind("<KeyRelease>", schedule_autosave, add="+")
        txt.bind("<FocusOut>", schedule_autosave, add="+")
    
    root.mainloop()


if __name__ == "__main__":
    main()
