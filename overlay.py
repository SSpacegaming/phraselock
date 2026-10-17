"""The fullscreen lock overlay (Tk + PIL compositing)."""

import os
import sys
import time
import random
import traceback
import threading
import subprocess
import tkinter as tk
from tkinter import font as tkfont

import tkinter as _tkmod
import traceback as _tb

_orig_tk_init = _tkmod.Tk.__init__

def _traced_tk_init(self, *a, **k):
    log("Tk() created from:\n" + "".join(_tb.format_stack(limit=6)))
    _orig_tk_init(self, *a, **k)

_tkmod.Tk.__init__ = _traced_tk_init

import win32api
import win32event
import win32con
import winerror

from config import (
    CONFIG_PATH, DEFAULT_CONFIG, _normalize, _contrast_colors,
    load_config, log, self_command,
)
from media import play_audio, _remote_media_cache
from stats import (
    get_progress, get_streak, get_xp_level,
    record_stat, update_streak, add_progress, verify_emergency_password,
)

from phrases import pick_phrase, remember_last_phrase, get_last_phrase


try:
    import winsound
except Exception:
    winsound = None

OVERLAY_MUTEX_NAME = "Local\\PhraseLockOverlay"

BACKGROUND_MODES = ("fill", "fit", "stretch", "center", "tile")


_standby = {
    "trigger": threading.Event(),
    "ready": threading.Event(),
    "active": threading.Event(),
}


def _try_acquire_overlay_mutex():
    try:
        handle = win32event.CreateMutex(None, False, OVERLAY_MUTEX_NAME)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            win32api.CloseHandle(handle)
            return None
        return handle
    except Exception:
        log("Overlay mutex failed:\n" + traceback.format_exc())
        return False


def _overlay_is_running():
    if _standby["active"].is_set():
        return True
    try:
        handle = win32event.OpenMutex(win32con.SYNCHRONIZE, False, OVERLAY_MUTEX_NAME)
        win32api.CloseHandle(handle)
        return True
    except Exception:
        return False


def _pick_and_remember(items, previous=None, cfg=None):
    text = pick_phrase(items, previous=previous, cfg=cfg)
    remember_last_phrase(text)
    return text


def fit_background(img, screen_w, screen_h, mode="fill", bg_color="#111111"):
    """Return an RGB image of exactly screen_w x screen_h.

    fill    - scale to cover the screen, keep aspect ratio, crop the overflow
    fit     - scale to fit inside the screen, keep aspect ratio, bars around it
    stretch - force to screen size (distorts)
    center  - original size, centered (cropped if bigger, bars if smaller)
    tile    - repeat at original size
    """
    from PIL import Image, ImageOps, ImageColor

    mode = (mode or "fill").lower()
    if mode not in BACKGROUND_MODES:
        mode = "fill"

    try:
        img = ImageOps.exif_transpose(img)   # honour phone-photo rotation
    except Exception:
        pass
    img = img.convert("RGB")
    iw, ih = img.size
    resample = Image.Resampling.LANCZOS

    # Degenerate sizes: tiling a 2px image would take forever.
    if mode == "tile" and (iw < 16 or ih < 16):
        mode = "stretch"

    if mode == "stretch":
        return img.resize((screen_w, screen_h), resample)

    canvas = Image.new("RGB", (screen_w, screen_h), ImageColor.getrgb(bg_color))

    if mode == "fill":
        scale = max(screen_w / iw, screen_h / ih)
        nw, nh = max(1, round(iw * scale)), max(1, round(ih * scale))
        resized = img.resize((nw, nh), resample)
        left, top = (nw - screen_w) // 2, (nh - screen_h) // 2
        return resized.crop((left, top, left + screen_w, top + screen_h))

    if mode == "fit":
        scale = min(screen_w / iw, screen_h / ih)
        nw, nh = max(1, round(iw * scale)), max(1, round(ih * scale))
        resized = img.resize((nw, nh), resample)
        canvas.paste(resized, ((screen_w - nw) // 2, (screen_h - nh) // 2))
        return canvas

    if mode == "center":
        # paste() clips negative offsets, so oversized images get cropped evenly
        canvas.paste(img, ((screen_w - iw) // 2, (screen_h - ih) // 2))
        return canvas

    # tile
    for y in range(0, screen_h, ih):
        for x in range(0, screen_w, iw):
            canvas.paste(img, (x, y))
    return canvas

PREVIEW_PID_PATH = os.path.join(os.path.dirname(CONFIG_PATH), "preview.pid")

def _replace_previous_preview():
    """Close an older preview window, then register this process as the preview."""
    try:
        import psutil
    except ImportError:
        psutil = None

    try:
        with open(PREVIEW_PID_PATH, "r") as f:
            old_pid = int(f.read().strip())
    except Exception:
        old_pid = None

    if psutil and old_pid and old_pid != os.getpid():
        try:
            proc = psutil.Process(old_pid)
            # Only kill it if it really is a preview (guards against PID reuse).
            if "--preview" in (proc.cmdline() or []):
                subprocess.run(
                    ["taskkill", "/PID", str(old_pid), "/T", "/F"],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    capture_output=True, timeout=5,
                )
        except Exception:
            pass

    try:
        os.makedirs(os.path.dirname(PREVIEW_PID_PATH), exist_ok=True)
        with open(PREVIEW_PID_PATH, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def _clear_preview_pid():
    try:
        with open(PREVIEW_PID_PATH, "r") as f:
            if int(f.read().strip()) == os.getpid():
                os.remove(PREVIEW_PID_PATH)
    except Exception:
        pass

def show_overlay(cfg, phrase_items, record_stats=True, preview=False, standby=None):
    """Show the lock overlay.

    phrase_items: list of {"text", "category", "difficulty"} dicts (already
    filtered and loaded by the caller so this module stays independent of
    file-format logic).
    """

    phrases = [x.get("text", "") for x in phrase_items]
    title = cfg.get("title", DEFAULT_CONFIG["title"])
    required = max(1, int(cfg.get("required_repeats", 1) or 1))
    reset_on_error = bool(cfg.get("reset_on_error", True))
    bg_image_path = _remote_media_cache((cfg.get("background_image") or "").strip(), "image")
    bg_mode = str(cfg.get("background_mode", "fill")).lower()
    panel_color = cfg.get("panel_color") or "#1a1a2e"
    try:
        panel_opacity = max(10, min(100, int(cfg.get("panel_opacity", 100)))) / 100.0
    except (TypeError, ValueError):
        panel_opacity = 1.0
    disable_paste = bool(cfg.get("disable_paste", False))
    case_insensitive = bool(cfg.get("case_insensitive", False))
    min_delay = max(0, int(cfg.get("min_delay_seconds", 0) or 0))
    play_sound = bool(cfg.get("play_sound", False))
    success_sound = _remote_media_cache(str(cfg.get("success_sound", "") or ""), "audio")
    error_sound = _remote_media_cache(str(cfg.get("error_sound", "") or ""), "audio")
    current_streak, _ = get_streak()
    max_attempts = max(0, int(cfg.get("max_attempts", 0) or 0))
    lockout_seconds = max(1, int(cfg.get("lockout_seconds", 15) or 15))
    strict_mode = bool(cfg.get("strict_mode", False))
    theme = str(cfg.get("theme", "Cyber Red"))
    scanlines = bool(cfg.get("scanlines", True))
    glow_effect = bool(cfg.get("glow_effect", True))
    glitch_effect = bool(cfg.get("glitch_effect", False))
    ui_scale = max(75, min(150, int(cfg.get("ui_scale", 100) or 100))) / 100.0
    font_family = str(cfg.get("font_family", "Consolas"))
    daily_goal = max(1, int(cfg.get("daily_goal", 1) or 1))
    progress_data = get_progress()
    level, level_xp, level_need = get_xp_level(progress_data.get("xp", 0))

    theme_map = {
        "Cyber Red": ("#ff1744", "#00e5ff", "#b400ff"),
        "Neon Pink": ("#ff2aa3", "#7df9ff", "#c86bff"),
        "Cyber Blue": ("#2979ff", "#00e5ff", "#7c4dff"),
        "Matrix": ("#00e676", "#00ff41", "#76ff03"),
        "Dark Purple": ("#9c27ff", "#e040fb", "#ff4081"),
        "Blackout": ("#eeeeee", "#777777", "#444444"),
    }
    theme_red, theme_cyan, theme_purple = theme_map.get(theme, theme_map["Cyber Red"])
    start_time = time.monotonic()

    if preview:
        _replace_previous_preview()

    root = tk.Tk()
    if standby is not None:
        root.withdraw()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.title(title)

    ui_bg = "#030305"
    accent = panel_color if panel_color else theme_red
    tech_red = theme_red
    tech_cyan = theme_cyan
    root.configure(bg=ui_bg)
    if preview:
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.bind("<Alt-F4>", lambda e: root.destroy())
        root.bind("<Escape>", lambda e: root.destroy())
    else:
        root.protocol("WM_DELETE_WINDOW", lambda: None)
        root.bind("<Alt-F4>", lambda e: "break")
        root.bind("<Escape>", lambda e: "break")

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    try:
        from PIL import Image, ImageTk, ImageColor, ImageDraw
        pil_available = True
    except Exception:
        pil_available = False
        Image = ImageTk = ImageColor = ImageDraw = None

    bg_pil = None
    if pil_available and bg_image_path and os.path.isfile(bg_image_path):
        try:
            with Image.open(bg_image_path) as src:
                bg_pil = fit_background(src, screen_w, screen_h, bg_mode)
            log(f"Background loaded: mode={bg_mode} file={bg_image_path}")
        except Exception:
            log("Could not load the background image:\n" + traceback.format_exc())
    elif bg_image_path:
        log(f"Background file not found: {bg_image_path}")

    if bg_pil is None and pil_available:
        bg_pil = Image.new("RGB", (screen_w, screen_h), "#111111")

    phrase_font = tkfont.Font(family=font_family, size=max(10, int(18 * ui_scale)), weight="bold")
    small_font = tkfont.Font(family=font_family, size=max(8, int(10 * ui_scale)))
    title_font = tkfont.Font(family=font_family, size=max(9, int(11 * ui_scale)), weight="bold")
    text_colors = _contrast_colors(panel_color)

    panel_w = 700
    panel_h = 420
    panel_x = max(0, (screen_w - panel_w) // 2)
    panel_y = max(0, (screen_h - panel_h) // 2)
    panel_rect_color = ImageColor.getrgb(panel_color) if pil_available else (26, 26, 46)

    composed = None
    if pil_available and bg_pil is not None:
        overlay_img = Image.new("RGBA", (panel_w, panel_h), panel_rect_color + (int(panel_opacity * 255),))
        mask = Image.new("L", (panel_w, panel_h), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, panel_w - 1, panel_h - 1), radius=8, fill=255)
        composed = bg_pil.convert("RGBA")
        composed.alpha_composite(overlay_img, (panel_x, panel_y))
        crop = composed.crop((panel_x, panel_y, panel_x + panel_w, panel_y + panel_h))
        original_crop = bg_pil.convert("RGBA").crop((panel_x, panel_y, panel_x + panel_w, panel_y + panel_h))
        crop.putalpha(mask)
        original_crop.alpha_composite(crop)
        composed.paste(original_crop, (panel_x, panel_y))
        if scanlines:
            line_draw = ImageDraw.Draw(composed)
            for yy in range(0, screen_h, 6):
                line_draw.line((0, yy, screen_w, yy), fill=(10, 10, 16, 42), width=1)
        bg_photo = ImageTk.PhotoImage(composed.convert("RGB"), master=root)
        bg_label = tk.Label(root, image=bg_photo, bd=0, highlightthickness=0)
        bg_label.image = bg_photo
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)
    else:
        root.configure(bg=panel_color)
        bg_label = None

    if pil_available and composed is not None:
        panel_crop = composed.crop((panel_x, panel_y, panel_x + panel_w, panel_y + panel_h)).convert("RGB")
        panel_photo = ImageTk.PhotoImage(panel_crop, master=root)
        content = tk.Canvas(root, width=panel_w, height=panel_h, bd=0,
                            highlightthickness=0, relief="flat", bg=panel_color)
        content.place(x=panel_x, y=panel_y)
        content.create_image(0, 0, image=panel_photo, anchor="nw")
        content._panel_photo = panel_photo
    else:
        content = tk.Canvas(root, width=panel_w, height=panel_h, bd=0,
                            highlightthickness=0, relief="flat", bg=panel_color)
        content.place(x=panel_x, y=panel_y)

    pad_x = 48
    content_w = panel_w - (pad_x * 2)

    content.create_text(pad_x, 34, anchor="w", text="// PHRASELOCK :: CONTROL MODE",
                        font=title_font, fill=tech_cyan)
    content.create_text(pad_x, 65, anchor="w", text="DISCIPLINE PROTOCOL  /  INPUT REQUIRED",
                        font=small_font, fill=tech_red)

    current_phrase_var = tk.StringVar(value=_pick_and_remember(phrase_items, cfg=cfg))
    phrase_id = content.create_text(pad_x, 98, anchor="nw",
                                    text=current_phrase_var.get(),
                                    font=phrase_font, fill=text_colors["primary"],
                                    width=content_w)
    counter_var = tk.StringVar(value=f"[ROUND] 0 / {required} COMPLETED")
    counter_id = content.create_text(pad_x, 157, anchor="nw", text=counter_var.get(),
                                     font=small_font, fill=text_colors["secondary"],
                                     width=content_w)
    streak_var = tk.StringVar(value=f"[STREAK] FIRST-TRY DAYS :: {current_streak}")
    streak_id = content.create_text(pad_x, 184, anchor="nw", text=streak_var.get(),
                                    font=(font_family, max(9, int(10 * ui_scale)), "bold"),
                                    fill=text_colors["secondary"], width=content_w)
    progress_var = tk.StringVar(
        value=f"[DAILY GOAL] {progress_data.get('goal_progress', 0)} / {daily_goal}   "
              f"[LVL {level}] XP {level_xp}/{level_need}"
    )
    progress_id = content.create_text(pad_x, 211, anchor="nw", text=progress_var.get(),
                                      font=small_font, fill=text_colors["secondary"],
                                      width=content_w)

    def bind_canvas_var(var, item_id):
        def update(*_):
            try:
                content.itemconfig(item_id, text=var.get())
            except tk.TclError:
                pass
        var.trace_add("write", update)
        update()

    bind_canvas_var(current_phrase_var, phrase_id)
    bind_canvas_var(counter_var, counter_id)
    bind_canvas_var(streak_var, streak_id)
    bind_canvas_var(progress_var, progress_id)

    entry_var = tk.StringVar()
    entry = tk.Entry(root, textvariable=entry_var, font=("Consolas", 12),
                     justify="left", bg="#08080c", fg="#f7f7fb",
                     insertbackground=tech_cyan, relief="flat", bd=0,
                     highlightthickness=2, highlightcolor=tech_cyan,
                     highlightbackground="#30303a")
    entry.place(x=panel_x + pad_x, y=panel_y + 244, width=content_w, height=34)
    entry.focus_force()

    if disable_paste:
        for seq in ("<<Paste>>", "<Control-v>", "<Control-V>", "<Shift-Insert>"):
            entry.bind(seq, lambda e: "break")

    error_id = content.create_text(pad_x, 286, anchor="nw", text="",
                                   font=small_font, fill="#ff6b6b", width=content_w)

    class CanvasTextProxy:
        def __init__(self, canvas, item_id):
            self.canvas = canvas
            self.item_id = item_id
            self._state = "normal"

        def config(self, **kwargs):
            if "text" in kwargs:
                self.canvas.itemconfig(self.item_id, text=kwargs["text"])
            if "state" in kwargs:
                self._state = kwargs["state"]

        configure = config

        def cget(self, key):
            if key == "text":
                return self.canvas.itemcget(self.item_id, "text")
            return getattr(self, "_state", "normal")

    error_label = CanvasTextProxy(content, error_id)

    submit_btn = tk.Button(root, text="[ EXECUTE UNLOCK ]",
                           font=(font_family, max(9, int(10 * ui_scale)), "bold"),
                           bg=tech_red, fg="white", activebackground=accent,
                           activeforeground="white", relief="flat", bd=0,
                           padx=16, pady=8, cursor="hand2",
                           highlightthickness=2 if glow_effect else 0,
                           highlightbackground=tech_red, highlightcolor=tech_cyan)
    submit_btn.place(x=panel_x + (panel_w - 280) // 2, y=panel_y + 350, width=280, height=42)

    emergency_available = bool(cfg.get("emergency_password_hash")) and not preview
    emergency_btn = None
    emergency_dialog = None

    state = {"completed": 0, "can_submit": min_delay <= 0, "had_error": False,
            "emergency_used": False, "attempts": 0,
            "chars_typed": 0, "correct_rounds": 0, "submissions": 0}

    if min_delay > 0:
        submit_btn.config(state="disabled")
        remaining = {"n": min_delay}
        wait_id = content.create_text(pad_x, 316, anchor="nw",
                                      text=f"Please wait {remaining['n']}s...",
                                      font=small_font, fill=text_colors["secondary"],
                                      width=content_w)
        wait_label = CanvasTextProxy(content, wait_id)

        def tick():
            remaining["n"] -= 1
            if remaining["n"] <= 0:
                state["can_submit"] = True
                submit_btn.config(state="normal")
                wait_label.config(text="")
            else:
                wait_label.config(text=f"Please wait {remaining['n']}s...")
                root.after(1000, tick)
        root.after(1000, tick)

    def finish_success(emergency=False):
        if play_sound:
            try:
                if not play_audio(success_sound):
                    if winsound is not None:
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                log("Success audio playback failed:\n" + traceback.format_exc())
        first_try = not state["had_error"] and not emergency
        if record_stats:
            record_stat(
                required,
                time.monotonic() - start_time,
                first_try=first_try,
                emergency=emergency,
                chars_typed=0 if emergency else state.get("chars_typed", 0),
                correct_rounds=None if emergency else state.get("correct_rounds", 0),
                submissions=state.get("submissions", 0),
            )
            if not emergency:
                update_streak(first_try)
                add_progress(50 if first_try else 20, successful=True)
        root.grab_release()
        if play_sound and success_sound:
            root.after(300, root.destroy)
        else:
            root.destroy()
        if not emergency and cfg.get("focus_session_enabled", False) and record_stats:
            try:
                command, cwd = self_command("--focus-session")
                subprocess.Popen(command, cwd=cwd,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                 close_fds=True)
            except Exception:
                log("Could not launch focus session:\n" + traceback.format_exc())

    def emergency_unlock():
        nonlocal emergency_dialog
        if not emergency_available or emergency_dialog is not None:
            return
        emergency_dialog = tk.Toplevel(root)
        dialog = emergency_dialog
        dialog.title("Emergency unlock")
        dialog.attributes("-topmost", True)
        dialog.transient(root)
        dialog.protocol("WM_DELETE_WINDOW", lambda: close_emergency())
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        dialog.configure(bg="#10101a")
        tk.Label(dialog, text="// EMERGENCY OVERRIDE", font=("Consolas", 13, "bold"),
                 fg=accent, bg="#10101a").pack(padx=24, pady=(22, 4))
        tk.Label(dialog, text="AUTHORIZATION KEY REQUIRED.", font=("Consolas", 10),
                 fg="#aaa6bd", bg="#10101a").pack(padx=20, pady=(0, 12))
        pw_var = tk.StringVar()
        pw = tk.Entry(dialog, textvariable=pw_var, show="*", width=32,
                      bg="#181824", fg="white", insertbackground="white",
                      relief="flat", bd=0, highlightthickness=2,
                      highlightcolor=accent, highlightbackground="#2d2b3c")
        pw.pack(padx=20, pady=5)
        msg = tk.Label(dialog, text="", fg="#ff6b8a", bg="#10101a")
        msg.pack(padx=20, pady=(0, 5))

        def close_emergency():
            nonlocal emergency_dialog
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            try:
                dialog.destroy()
            except tk.TclError:
                pass
            emergency_dialog = None
            root.attributes("-topmost", True)
            root.lift()
            root.focus_force()

        def submit_emergency(event=None):
            if verify_emergency_password(cfg, pw_var.get()):
                try:
                    dialog.grab_release()
                    dialog.destroy()
                except tk.TclError:
                    pass
                emergency_dialog = None
                state["emergency_used"] = True
                finish_success(emergency=True)
            else:
                msg.config(text="Incorrect emergency password.")
                pw_var.set("")
                pw.focus_force()

        tk.Button(dialog, text="[ OVERRIDE ]", command=submit_emergency, width=15,
                  font=("Consolas", 10, "bold"), bg=tech_red, fg="white",
                  activebackground=accent, activeforeground="white",
                  relief="flat", bd=0, padx=12, pady=7,
                  cursor="hand2").pack(pady=(6, 20))
        pw.bind("<Return>", submit_emergency)
        pw.focus_force()

    if emergency_available:
        emergency_btn = tk.Button(root, text="Emergency unlock",
                                  font=("Consolas", 8, "bold"),
                                  command=emergency_unlock, relief="flat",
                                  bd=1, padx=10, pady=5, cursor="hand2",
                                  bg="#09090e", fg="#777785",
                                  activebackground="#1a0a10",
                                  activeforeground="white")
        emergency_btn.place(relx=0.995, rely=0.995, anchor="se")

    def check(event=None):
        if preview:
            return
        if not state["can_submit"]:
            return
        typed_raw = entry_var.get()
        typed = _normalize(typed_raw, case_insensitive)
        target = _normalize(current_phrase_var.get(), case_insensitive)
        state["submissions"] = state.get("submissions", 0) + 1
        if typed == target:
            state["completed"] += 1
            state["correct_rounds"] = state.get("correct_rounds", 0) + 1
            state["chars_typed"] = state.get("chars_typed", 0) + len(typed_raw)
            entry_var.set("")
            error_label.config(text="")
            if state["completed"] >= required:
                finish_success()
                return
            counter_var.set(f"[ROUND] {state['completed']} / {required} COMPLETED")
            current_phrase_var.set(_pick_and_remember(phrase_items, previous=current_phrase_var.get(), cfg=cfg))
        else:
            state["had_error"] = True
            state["attempts"] += 1
            if cfg.get("sound_on_error", False):
                try:
                    if not play_audio(error_sound) and winsound is not None:
                        winsound.MessageBeep(winsound.MB_ICONHAND)
                except Exception:
                    log("Error audio playback failed:\n" + traceback.format_exc())
            if reset_on_error or strict_mode:
                state["completed"] = 0
                counter_var.set(f"[ROUND] 0 / {required} COMPLETED")
            error_label.config(text="ACCESS DENIED // INPUT MISMATCH")
            if glitch_effect:
                original = error_label.cget("text")

                def glitch_step(n=0):
                    if n >= 4:
                        try:
                            error_label.config(text=original)
                        except tk.TclError:
                            pass
                        return
                    try:
                        error_label.config(text=["// // INPUT CORRUPTED // //",
                                                 "ACCESS // DENIED",
                                                 original][n % 3])
                    except tk.TclError:
                        return
                    root.after(70, lambda: glitch_step(n + 1))

                glitch_step()
            entry_var.set("")
            if max_attempts and state["attempts"] >= max_attempts:
                error_label.config(text=f"LOCKOUT // RETRY IN {lockout_seconds}s")
                submit_btn.config(state="disabled")
                state["can_submit"] = False
                state["attempts"] = 0

                def unlock_after_lockout(n=lockout_seconds):
                    if n <= 0:
                        state["can_submit"] = True
                        submit_btn.config(state="normal")
                        error_label.config(text="")
                        entry.focus_force()
                        return
                    error_label.config(text=f"LOCKOUT // RETRY IN {n}s")
                    root.after(1000, lambda: unlock_after_lockout(n - 1))

                root.after(1000, unlock_after_lockout)

    entry.bind("<Return>", check)
    submit_btn.config(command=check)
    if preview:
        submit_btn.config(text="Close Preview", command=root.destroy)

    def keep_on_top():
        try:
            if emergency_dialog is None:
                root.attributes("-topmost", True)
                root.lift()
            else:
                emergency_dialog.attributes("-topmost", True)
                emergency_dialog.lift()
            root.after(500, keep_on_top)
        except tk.TclError:
            pass

    if standby is None:
        keep_on_top()
        if not preview:
            root.grab_set()
        root.mainloop()
        if preview:
            _clear_preview_pid()
        return

    def watched_mtimes():
        out = []
        for p in (CONFIG_PATH, (cfg.get("phrases_file") or "").strip().strip('"')):
            try:
                out.append(os.path.getmtime(p) if p else None)
            except OSError:
                out.append(None)
        return out

    config_mtime = watched_mtimes()
    poll = {"n": 0}
    overlay_handle = {"h": None}

    def activate():
        nonlocal start_time
        handle = _try_acquire_overlay_mutex()
        if handle is None:
            log("Another overlay is already showing; standby stays hidden.")
            return False
        overlay_handle["h"] = handle
        standby["ready"].clear()
        standby["active"].set()
        current_phrase_var.set(_pick_and_remember(phrase_items, cfg=cfg))
        streak_now, _best = get_streak()
        streak_var.set(f"[STREAK] FIRST-TRY DAYS :: {streak_now}")
        prog = get_progress()
        lvl, lxp, lneed = get_xp_level(prog.get("xp", 0))
        progress_var.set(
            f"[DAILY GOAL] {prog.get('goal_progress', 0)} / {daily_goal}   "
            f"[LVL {lvl}] XP {lxp}/{lneed}"
        )
        start_time = time.monotonic()
        root.deiconify()
        root.attributes("-fullscreen", True)
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
        entry.focus_force()
        root.grab_set()
        keep_on_top()
        return True

    def poll_trigger():
        try:
            if standby["trigger"].is_set():
                standby["trigger"].clear()
                if activate():
                    return
            poll["n"] += 1
            changed = poll["n"] % 40 == 0 and watched_mtimes() != config_mtime
            if changed:
                log("Config changed; rebuilding standby overlay.")
                root.destroy()
                return
            root.after(25, poll_trigger)
        except tk.TclError:
            pass

    standby["ready"].set()
    root.after(25, poll_trigger)
    try:
        root.mainloop()
    finally:
        standby["ready"].clear()
        standby["active"].clear()
        if overlay_handle["h"]:
            try:
                win32api.CloseHandle(overlay_handle["h"])
            except Exception:
                pass


def start_standby_overlay(load_phrase_items):
    """Keep one hidden, fully built overlay ready inside this process."""
    def worker():
        while True:
            try:
                cfg = load_config()
                if not cfg.get("enabled", True):
                    time.sleep(2)
                    continue
                _standby["trigger"].clear()
                items = load_phrase_items(cfg)
                show_overlay(cfg, items, record_stats=True, preview=False, standby=_standby)
            except Exception:
                log("Standby overlay error:\n" + traceback.format_exc())
                _standby["ready"].clear()
                _standby["active"].clear()
                time.sleep(3)
            time.sleep(0.5)

    threading.Thread(target=worker, name="PhraseLockStandby", daemon=True).start()