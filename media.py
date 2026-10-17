"""Remote media download + local audio playback (WAV via winsound, MP3 via MCI)."""

import os
import time
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