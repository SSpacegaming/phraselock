"""Animated GIF backgrounds: decoding and frame timing (no Windows or Tk needed).

overlay.py draws the frames; this module only decodes a GIF into plain RGB
frames within a memory budget, and drives the "next frame" timing through a
scheduler that is passed in (Tk's root.after in the app, a fake in the tests).
"""

import bisect
import math
import os
import time
import traceback

from config import log

MAX_FRAMES = 240                       # longer GIFs are cut after this many frames
MAX_DECODED_BYTES = 96 * 1024 * 1024   # decoded RGB budget for one GIF
TOTAL_DECODED_BYTES = 192 * 1024 * 1024  # budget for all GIFs of one lock screen
MIN_DELAY_MS = 40                      # never faster than 25 fps (keeps the CPU calm)
DEFAULT_DELAY_MS = 100                 # what browsers use for 0/10 ms GIF delays
BACKDROP = (17, 17, 17)                # shown through transparent GIF pixels (#111111)

_CACHE = {}


def frame_delay_ms(raw):
    """Milliseconds to show a frame, from the GIF's own duration value."""
    try:
        delay = int(raw)
    except (TypeError, ValueError):
        delay = 0
    if delay <= 10:
        delay = DEFAULT_DELAY_MS
    return max(MIN_DELAY_MS, delay)


class GifFrames:
    """Decoded frames (PIL RGB images, all the same size) and their delays."""

    def __init__(self, frames, delays):
        self.frames = list(frames)
        self.delays = list(delays)

    def __len__(self):
        return len(self.frames)

    @property
    def nbytes(self):
        return sum(f.size[0] * f.size[1] * 3 for f in self.frames)


def load_gif_frames(path, max_frames=MAX_FRAMES, max_bytes=MAX_DECODED_BYTES):
    """Decode an animated GIF, or return None.

    None means "not an animated GIF" (a still image, another format, a single
    frame GIF, a missing or broken file): the caller then draws it as before.
    Big GIFs are shrunk and/or cut so the decoded frames fit in *max_bytes*.
    """
    try:
        from PIL import Image, ImageSequence
        with Image.open(path) as im:
            if im.format != "GIF" or getattr(im, "n_frames", 1) < 2:
                return None
            w, h = im.size
            if w < 1 or h < 1:
                return None
            n_frames = im.n_frames
            full = w * h * 3
            # Keep at least a quarter of the pixels; cut frames instead of blurring more.
            total = min(n_frames, max_frames, max(2, int(max_bytes // (full * 0.25))))
            per_frame = max_bytes // total
            scale = 1.0 if full <= per_frame else math.sqrt(per_frame / full)
            size = (w, h) if scale >= 1.0 else (max(1, int(w * scale)), max(1, int(h * scale)))
            frames, delays = [], []
            for index, frame in enumerate(ImageSequence.Iterator(im)):
                if index >= total:
                    break
                base = Image.new("RGBA", (w, h), BACKDROP + (255,))
                base.alpha_composite(frame.convert("RGBA"))
                rgb = base.convert("RGB")
                if size != (w, h):
                    rgb = rgb.resize(size, Image.Resampling.BILINEAR)
                frames.append(rgb)
                delays.append(frame_delay_ms(frame.info.get("duration")))
        if len(frames) < 2:
            return None
        if total < n_frames:
            log(f"GIF cut to {len(frames)} of {n_frames} frames: {path}")
        return GifFrames(frames, delays)
    except Exception:
        log(f"Could not decode GIF {path}:\n" + traceback.format_exc())
        return None


def clear_cache():
    """Forget decoded GIFs (called when a lock screen is rebuilt)."""
    _CACHE.clear()


def get_gif_frames(path):
    """Decoded frames of an animated GIF file, shared between screens.

    Returns None for anything that is not an animated GIF, and also when the
    decoded-memory budget for this lock screen is used up (the picture is then
    shown still, like before).
    """
    if not path or not os.path.isfile(path) or not str(path).lower().endswith(".gif"):
        return None
    try:
        key = (os.path.abspath(path), os.path.getmtime(path))
    except OSError:
        return None
    if key in _CACHE:
        return _CACHE[key]
    remaining = TOTAL_DECODED_BYTES - sum(g.nbytes for g in _CACHE.values() if g)
    if remaining < 8 * 1024 * 1024:
        log(f"GIF memory budget used up, showing it as a still picture: {path}")
        return None
    frames = load_gif_frames(path, max_bytes=min(MAX_DECODED_BYTES, remaining))
    _CACHE[key] = frames
    return frames


_SCANLINE_MASKS = {}
SCANLINE_COLOR = (10, 10, 16)


def apply_scanlines(img, color=SCANLINE_COLOR):
    """Draw the dark scanlines (every 6th row) on *img* in place and return it.

    Same picture as drawing each line separately, but one fast paste through a
    mask that is built once per screen size.
    """
    from PIL import Image
    key = img.size
    mask = _SCANLINE_MASKS.get(key)
    if mask is None:
        w, h = key
        mask = Image.new("L", key, 0)
        mask.paste(255, (0, 0, w, 1))
        strip = Image.new("L", (w, 6), 0)
        strip.paste(255, (0, 0, w, 1))
        for y in range(0, h, 6):
            mask.paste(strip, (0, y))
        _SCANLINE_MASKS.clear()          # keep only the size(s) in use
        _SCANLINE_MASKS[key] = mask
    fill = tuple(color) + ((42,) if img.mode == "RGBA" else ())
    img.paste(fill, (0, 0), mask)
    return img


class Animator:
    """Plays one GIF on the wall clock: show(index) draws the frame that is due.

    One Animator drives every screen that shows the same GIF (show draws them
    all), so the screens stay in step. When drawing is slower than the GIF, the
    frames that are already over are skipped instead of queuing up, so the
    animation keeps its speed and the lock screen stays responsive.

    schedule(ms, fn) must run fn once after ms milliseconds and return a handle;
    cancel(handle) is optional. A frame that raises (for example because the
    window is gone) stops the animation instead of repeating the error. on_slow
    is called once, with (average draw ms, average GIF frame ms), when drawing a
    frame takes longer on average than the GIF's own frame time.
    """

    MIN_GAP_MS = 8          # breathing room for the UI when we are running behind
    SLOW_CHECK_AFTER = 20   # frames drawn before judging the speed

    def __init__(self, delays, show, schedule, cancel=None, clock=time.monotonic, on_slow=None):
        self.delays = list(delays) or [DEFAULT_DELAY_MS]
        self.show = show
        self.schedule = schedule
        self.cancel = cancel
        self.clock = clock
        self.on_slow = on_slow
        self.index = 0
        self.running = False
        self._handle = None
        self._t0 = 0.0
        self._ends = []
        total = 0
        for d in self.delays:
            total += d
            self._ends.append(total)
        self.total_ms = total
        self._drawn = 0
        self._draw_ms = 0.0
        self._slow_reported = False

    def frame_at(self, ms):
        """Index of the frame that is due *ms* milliseconds after the start."""
        return min(bisect.bisect_right(self._ends, ms % self.total_ms), len(self.delays) - 1)

    def _now_ms(self):
        return (self.clock() - self._t0) * 1000.0

    def start(self):
        if self.running:
            return
        self.running = True
        self.index = 0                       # frame 0 is already on screen
        self._t0 = self.clock()
        self._handle = self.schedule(self._ends[0], self._tick)

    def stop(self):
        self.running = False
        handle, self._handle = self._handle, None
        if handle is not None and self.cancel is not None:
            try:
                self.cancel(handle)
            except Exception:
                pass

    def _tick(self):
        if not self.running:
            return
        target = self.frame_at(self._now_ms())
        if target != self.index:
            started = self.clock()
            try:
                self.show(target)
            except Exception:
                self.running = False
                self._handle = None
                return
            self.index = target
            self._note_draw((self.clock() - started) * 1000.0)
        pos = self._now_ms() % self.total_ms
        due = self.frame_at(pos)
        if due != self.index:                # still behind: draw the current frame next
            wait = self.MIN_GAP_MS
        else:
            wait = max(1, math.ceil(self._ends[due] - pos))
        self._handle = self.schedule(wait, self._tick)

    def _note_draw(self, ms):
        self._drawn += 1
        self._draw_ms += ms
        if (self._drawn == self.SLOW_CHECK_AFTER and not self._slow_reported
                and self.on_slow is not None):
            avg_draw = self._draw_ms / self._drawn
            avg_delay = self.total_ms / len(self.delays)
            if avg_draw > avg_delay:
                self._slow_reported = True
                try:
                    self.on_slow(avg_draw, avg_delay)
                except Exception:
                    pass
