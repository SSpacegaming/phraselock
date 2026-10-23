"""Remote media download + local audio playback (WAV via winsound, MP3 via MCI)."""

import os
import random
import ctypes
import threading
import traceback
import hashlib
import urllib.request
import urllib.parse

from config import MEDIA_CACHE_DIR, log

try:
    import winsound
except Exception:
    winsound = None

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_AUDIO_BYTES = 15 * 1024 * 1024

_AUDIO_LOCK = threading.Lock()
_AUDIO_COUNTER = 0


def _is_http_url(value):
    try:
        p = urllib.parse.urlparse(str(value).strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def _remote_media_cache(value, kind):
    """Return a local cached copy for a remote media URL, or the original path."""
    value = str(value or "").strip()
    if not _is_http_url(value):
        return value

    allowed_audio = {".wav", ".mp3"}
    allowed_image = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
    allowed = allowed_image if kind == "image" else allowed_audio

    parsed = urllib.parse.urlparse(value)
    if os.path.splitext(parsed.path)[1].lower() not in allowed:
        log(f"Ignoring {kind} URL with unsupported extension: {value}")
        return ""

    limit = MAX_IMAGE_BYTES if kind == "image" else MAX_AUDIO_BYTES
    try:
        os.makedirs(MEDIA_CACHE_DIR, exist_ok=True)
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        ext = os.path.splitext(parsed.path)[1].lower()
        target = os.path.join(MEDIA_CACHE_DIR, digest + ext)
        if os.path.isfile(target) and os.path.getsize(target) <= limit:
            return target
        req = urllib.request.Request(value, headers={"User-Agent": "PhraseLock/3.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > limit:
                raise ValueError(f"remote {kind} is larger than {limit // (1024 * 1024)} MB")
            total = 0
            with open(target, "wb") as out:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        out.close()
                        try:
                            os.remove(target)
                        except OSError:
                            pass
                        raise ValueError(f"remote {kind} is larger than {limit // (1024 * 1024)} MB")
                    out.write(chunk)
        log(f"Cached remote {kind}: {value}")
        return target
    except Exception:
        log(f"Could not download remote {kind} {value}:\n" + traceback.format_exc())
        return ""


def _resolve_image(value):
    """Default *resolve* for choose_background(s): cache remote images locally."""
    return _remote_media_cache(value, "image")


def background_sources(cfg):
    """Return the configured background images (local paths or URLs), in order.

    New key "background_images" (list). When it is missing (None), the older
    single "background_image" value is used, so existing configs keep working.
    An empty list means: no image, solid background.
    """
    raw = cfg.get("background_images")
    if raw is None:
        raw = [cfg.get("background_image") or ""]
    if isinstance(raw, str):
        raw = [raw]
    out = []
    for item in raw:
        item = str(item or "").strip()
        if item and item not in out:
            out.append(item)
    return out


def choose_background(sources, previous=None, rng=random, resolve=None, exists=os.path.isfile):
    """Pick one usable background at random.

    Returns (source, local_path), or ("", "") when none of the sources is
    usable. The image used last time (*previous*) is avoided when another
    usable one exists, so the same picture is not shown twice in a row.
    Remote sources are only downloaded when they get tried.
    """
    if resolve is None:
        resolve = _resolve_image
    fresh = [x for x in sources if x != previous]
    rng.shuffle(fresh)
    others = [x for x in sources if x == previous]
    for source in fresh + others:
        path = resolve(source)
        if path and exists(path):
            return source, path
        log(f"Background image not usable, trying another: {source}")
    return "", ""


def choose_backgrounds(sources, count, previous=None, rng=random, resolve=None, exists=os.path.isfile):
    """Pick *count* backgrounds, as different from each other as possible.

    Returns a list of (source, local_path) of length *count*. The first entry
    avoids *previous* when another usable image exists. When there are fewer
    usable images than screens, images are reused in turn. When nothing is
    usable every entry is ("", "").
    """
    count = max(1, int(count))
    if resolve is None:
        resolve = _resolve_image
    fresh = [x for x in sources if x != previous]
    rng.shuffle(fresh)
    others = [x for x in sources if x == previous]
    usable = []
    for source in fresh + others:
        if len(usable) >= count:
            break
        path = resolve(source)
        if path and exists(path):
            usable.append((source, path))
        else:
            log(f"Background image not usable, trying another: {source}")
    if not usable:
        return [("", "")] * count
    result = list(usable)
    i = 0
    while len(result) < count:
        result.append(usable[i % len(usable)])
        i += 1
    return result[:count]


_LAST_BACKGROUND = {"source": None}


def pick_background_image(cfg):
    """Local path of the background to use for this lock ("" for none)."""
    sources = background_sources(cfg)
    if not sources:
        return ""
    source, path = choose_background(sources, previous=_LAST_BACKGROUND["source"])
    if source:
        _LAST_BACKGROUND["source"] = source
    return path


def pick_backgrounds(cfg, count):
    """Local background paths for *count* locked screens (first = phrase panel).

    Same picture everywhere by default; with cfg["background_per_screen"] each
    screen gets its own random picture (as far as there are enough images).
    """
    count = max(1, int(count))
    sources = background_sources(cfg)
    if not sources:
        return [""] * count
    if count == 1 or not cfg.get("background_per_screen", False):
        return [pick_background_image(cfg)] * count
    picks = choose_backgrounds(sources, count, previous=_LAST_BACKGROUND["source"])
    if picks[0][0]:
        _LAST_BACKGROUND["source"] = picks[0][0]
    return [path for _src, path in picks]


def play_audio(value):
    """Play a local WAV/MP3 or cached remote WAV/MP3 on Windows."""
    global _AUDIO_COUNTER
    value = str(value or "").strip()
    if not value:
        return False
    path = _remote_media_cache(value, "audio") if _is_http_url(value) else value
    if not path or not os.path.isfile(path):
        log(f"Audio file not found: {value}")
        return False
    ext = os.path.splitext(path)[1].lower()
    if ext not in {".wav", ".mp3"}:
        log(f"Unsupported audio format: {path}")
        return False
    if ext == ".wav" and winsound is not None:
        try:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            log(f"Playing WAV: {path}")
            return True
        except Exception:
            log("winsound WAV playback failed:\n" + traceback.format_exc())
    if os.name != "nt":
        return False

    def _mci_worker(audio_path, extension):
        global _AUDIO_COUNTER
        alias = f"phrlockaudio{_AUDIO_COUNTER}"
        _AUDIO_COUNTER += 1
        winmm = ctypes.windll.winmm
        safe = audio_path.replace('"', '')
        if extension == ".mp3":
            open_cmd = f'open "{safe}" type mpegvideo alias {alias}'
        else:
            open_cmd = f'open "{safe}" type waveaudio alias {alias}'
        buf = ctypes.create_unicode_buffer(512)
        try:
            rc = winmm.mciSendStringW(open_cmd, buf, 512, 0)
            if rc != 0:
                log(f"MCI open failed ({rc}) for {audio_path}")
                return
            rc = winmm.mciSendStringW(f"play {alias} wait", None, 0, 0)
            if rc != 0:
                log(f"MCI play failed ({rc}) for {audio_path}")
        except Exception:
            log("MCI playback failed:\n" + traceback.format_exc())
        finally:
            try:
                winmm.mciSendStringW(f"close {alias}", None, 0, 0)
            except Exception:
                pass

    threading.Thread(target=_mci_worker, args=(path, ext), daemon=True).start()
    log(f"Playing audio: {path}")
    return True