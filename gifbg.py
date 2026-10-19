"""Animated GIF backgrounds: decoding and frame timing (no Windows or Tk needed).

overlay.py draws the frames; this module only decodes a GIF into plain RGB
frames within a memory budget, and drives the "next frame" timing through a
scheduler that is passed in (Tk's root.after in the app, a fake in the tests).
"""

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


class Animator:
    """Calls show(index) for each next frame, on the GIF's own timing.

    schedule(ms, fn) must run fn once after ms milliseconds and return a handle;
    cancel(handle) is optional. Time spent drawing a frame is subtracted from the
    next delay, and a frame that raises (for example because the window is gone)
    stops the animation instead of repeating the error.
    """

    def __init__(self, delays, show, schedule, cancel=None, clock=time.monotonic):
        self.delays = list(delays) or [DEFAULT_DELAY_MS]
        self.show = show
        self.schedule = schedule
        self.cancel = cancel
        self.clock = clock
        self.index = 0
        self.running = False
        self._handle = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._handle = self.schedule(self.delays[self.index], self._tick)

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
        self.index = (self.index + 1) % len(self.delays)
        started = self.clock()
        try:
            self.show(self.index)
        except Exception:
            self.running = False
            self._handle = None
            return
        spent = int((self.clock() - started) * 1000)
        self._handle = self.schedule(max(1, self.delays[self.index] - spent), self._tick)
