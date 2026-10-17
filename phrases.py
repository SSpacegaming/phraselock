"""Phrase library loading (TXT / CSV / JSON)."""

import os
import csv
import json
import traceback

from config import CONFIG_DIR, DEFAULT_CONFIG, log

PHRASE_STATE_PATH = os.path.join(CONFIG_DIR, "phrase_state.json")

DIFFICULTY_WEIGHTS = {
    "easy": 1,
    "normal": 2,
    "hard": 3,
    "extreme": 4,
}

def _load_state():
    try:
        with open(PHRASE_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_state(data):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = PHRASE_STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, PHRASE_STATE_PATH)
    except Exception:
        log("Could not save phrase state:\n" + traceback.format_exc())


def get_last_phrase():
    return _load_state().get("last_phrase", "")


def remember_last_phrase(text):
    if not text:
        return
    data = _load_state()
    data["last_phrase"] = text
    _save_state(data)


def _weight_for(item):
    diff = str(item.get("difficulty", "normal")).lower()
    return DIFFICULTY_WEIGHTS.get(diff, DIFFICULTY_WEIGHTS["normal"])


def pick_phrase(items, previous=None, cfg=None, avoid_last_session=True):
    """Pick a phrase.

    * items: list of {"text","category","difficulty"} dicts (already filtered).
    * previous: the phrase shown on the previous round in this session (so we
      avoid repeating it within a session even when weighted).
    * cfg: full config, used to read `difficulty_weighting`.
    * avoid_last_session: when True (default), the last phrase from the
      previous session is excluded from the first pick.
    """
    import random
    if not items:
        return ""
    if len(items) == 1:
        return items[0].get("text", "")

    last_session = get_last_phrase() if avoid_last_session else ""
    candidates = [it for it in items if it.get("text") != previous]
    if not candidates:
        candidates = items

    if last_session:
        no_session_repeat = [it for it in candidates if it.get("text") != last_session]
        if no_session_repeat:
            candidates = no_session_repeat

    weighting = True if cfg is None else bool(cfg.get("difficulty_weighting", True))
    if weighting:
        weights = [_weight_for(it) for it in candidates]
        return random.choices(candidates, weights=weights, k=1)[0].get("text", "")
    return random.choice(candidates).get("text", "")

def load_external_phrases(path):
    path = (path or "").strip().strip('"')
    if not path or not os.path.isfile(path):
        return []
    result = []
    try:
        if path.lower().endswith(".json"):
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            items = data if isinstance(data, list) else data.get("phrases", [])
            for item in items:
                if isinstance(item, str) and item.strip():
                    result.append({"text": item.strip(), "category": "General",
                                   "difficulty": "normal"})
                elif isinstance(item, dict) and str(item.get("phrase", item.get("text", ""))).strip():
                    result.append({
                        "text": str(item.get("phrase", item.get("text"))).strip(),
                        "category": str(item.get("category", "General")),
                        "difficulty": str(item.get("difficulty", "normal")).lower(),
                    })
            return result
        if path.lower().endswith(".csv"):
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
                        continue
                    if not result and row[0].strip().lower() in ("phrase", "phrases", "sentence", "text"):
                        continue
                    result.append({
                        "text": row[0].strip(),
                        "category": (row[1].strip() if len(row) > 1 and row[1].strip() else "General"),
                        "difficulty": (row[2].strip().lower() if len(row) > 2 and row[2].strip() else "normal"),
                    })
            return result
        with open(path, "r", encoding="utf-8-sig") as f:
            return [{"text": line.strip(), "category": "General", "difficulty": "normal"}
                    for line in f if line.strip() and not line.lstrip().startswith("#")]
    except Exception:
        log("Could not read external phrases file:\n" + traceback.format_exc())
        return []


def get_phrases(cfg):
    external = load_external_phrases(cfg.get("phrases_file", ""))
    if not external:
        external = [{"text": p.strip(), "category": "General", "difficulty": "normal"}
                    for p in (cfg.get("phrases") or []) if isinstance(p, str) and p.strip()]
    wanted = str(cfg.get("difficulty", "all")).lower()
    if wanted != "all":
        filtered = [p for p in external if p.get("difficulty", "normal").lower() == wanted]
        if filtered:
            external = filtered
    return external or [{"text": DEFAULT_CONFIG["phrases"][0],
                         "category": "General", "difficulty": "normal"}]