# -*- coding: utf-8 -*-
"""ElevenLabs as ONE key for all sound work: sound effects, background music, speech-to-text (Scribe) and
key diagnostics. Everything degrades gracefully: callers fall back to Freesound / local synthesis / Groq / Whisper."""
import os, re, time, hashlib, requests

BASE = (os.environ.get("EL_API_URL") or "https://api.elevenlabs.io").rstrip("/")
DOWN = {}  # per key (hash): one subscriber's bad/exhausted key never blocks the others


def _kid(key):
    return hashlib.sha1((key or "").encode()).hexdigest()[:12]

# short English prompts work best for sound-effect generation
KIND_PROMPTS = {
    "whoosh": ("fast cinematic whoosh swoosh transition sound effect", 1.0),
    "pop": ("short soft bubble pop UI sound effect", 0.6),
    "impact": ("heavy cinematic impact hit with deep boom", 1.4),
    "rise": ("rising tension riser sweep building up", 2.0),
    "ding": ("bright clean notification bell ding", 1.0),
    "click": ("crisp UI button click", 0.5),
    "bass": ("deep sub bass drop", 1.5),
    "glitch": ("short digital glitch stutter sound effect", 0.8),
    "shine": ("magical sparkle shine twinkle", 1.2),
    "tick": ("single clock tick", 0.5),
    "typing": ("fast keyboard typing", 1.5),
}
MUSIC_PROMPTS = {
    "chill": "calm relaxed lo-fi background music, soft pads and light beat, instrumental",
    "upbeat": "upbeat energetic modern pop background music for a social media video, instrumental",
    "cinematic": "epic cinematic trailer background music, strings and drums building up, instrumental",
    "dark": "dark moody ambient electronic background music, instrumental",
}


def _hdr(key, ctype="application/json"):
    h = {"xi-api-key": key, "User-Agent": "SA-Motion-Studio/12"}
    if ctype:
        h["Content-Type"] = ctype
    return h


def explain(r):
    """HTTP response -> short Arabic reason."""
    try:
        d = r.json().get("detail")
    except Exception:
        d = None
    status = (d.get("status") if isinstance(d, dict) else "") or ""
    msg = (d.get("message") if isinstance(d, dict) else (d if isinstance(d, str) else "")) or ""
    if r.status_code == 401 and status == "invalid_api_key":
        return "المفتاح غير صحيح"
    if r.status_code == 401 and status in ("missing_permissions", "forbidden"):
        m = re.search(r"permission[s]?[^.]*?([a-z_]+)", msg or "")
        return "المفتاح صحيح لكن ينقصه صلاحية" + (f" ({m.group(1)})" if m else "")
    if r.status_code == 401:
        return "المفتاح مرفوض (401)"
    if r.status_code == 402 or status in ("quota_exceeded", "payment_required"):
        return "انتهى رصيد حسابك في ElevenLabs"
    if r.status_code == 429:
        return "تجاوزت حد الطلبات المتزامنة/السريعة، حاول بعد قليل"
    if status in ("paid_plan_required", "payment_issue") or r.status_code == 403:
        return "هذه الميزة تتطلب باقة مدفوعة في ElevenLabs"
    return f"HTTP {r.status_code}: {(msg or r.text)[:140]}"


def _scope(key, method, path, **kw):
    """zero-cost permission probe: an authorised call with an empty/invalid body answers 4xx validation, not 401/403."""
    try:
        r = requests.request(method, BASE + path, headers=_hdr(key, kw.pop("ctype", "application/json")), timeout=20, **kw)
    except requests.RequestException as e:
        return None, f"تعذّر الاتصال: {str(e)[:80]}"
    if r.status_code in (400, 404, 422, 200):
        return True, ""
    return False, explain(r)


def probe(key):
    """-> {valid, caps:{sfx,music,stt,tts}, tier, chars_left, notes[]}"""
    key = (key or "").strip()
    out = {"valid": False, "caps": {}, "tier": "", "chars_left": None, "notes": []}
    if not key:
        out["notes"].append("لا يوجد مفتاح")
        return out
    checks = {
        "sfx": ("POST", "/v1/sound-generation", {"json": {"text": ""}}),
        "music": ("POST", "/v1/music", {"json": {}}),
        "stt": ("POST", "/v1/speech-to-text", {"data": {"model_id": "scribe_v1"}, "ctype": None}),
        "tts": ("POST", "/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb", {"json": {}}),
    }
    invalid = False
    for name, (m, p, kw) in checks.items():
        ok, why = _scope(key, m, p, **dict(kw))
        out["caps"][name] = bool(ok)
        if ok is False:
            if "غير صحيح" in why or "مرفوض" in why:
                invalid = True
                out["notes"].append(why)
                break
            out["notes"].append({"sfx": "المؤثرات", "music": "الموسيقى", "stt": "التفريغ", "tts": "النطق"}[name] + ": " + why)
        if ok is None:
            out["notes"].append(why)
            return out
    if invalid:
        out["caps"] = {k: False for k in out["caps"]}
        return out
    out["valid"] = True
    try:  # plan & balance need the user_read scope: optional
        r = requests.get(BASE + "/v1/user/subscription", headers=_hdr(key, None), timeout=20)
        if r.status_code == 200:
            j = r.json()
            out["tier"] = j.get("tier", "")
            out["chars_left"] = max(0, int(j.get("character_limit", 0)) - int(j.get("character_count", 0)))
    except Exception:
        pass
    return out


def summary(pr):
    if not pr["valid"]:
        return "✗ " + ("؛ ".join(pr["notes"]) or "المفتاح غير صالح")
    names = {"sfx": "مؤثرات", "music": "موسيقى", "stt": "تفريغ", "tts": "نطق"}
    ok = [names[k] for k, v in pr["caps"].items() if v]
    no = [names[k] for k, v in pr["caps"].items() if not v]
    s = "✓ مفتاح ElevenLabs صالح"
    if pr["tier"]:
        s += f" · باقة {pr['tier']}"
    if pr["chars_left"] is not None:
        s += f" · المتبقي {pr['chars_left']:,} رصيد"
    s += " · يدعم: " + ("، ".join(ok) or "—")
    if no:
        s += " · ينقصه: " + "، ".join(no) + " (فعّل الصلاحية من إعدادات المفتاح في ElevenLabs)"
    return s


def _cache_path(host, tag, text, extra=""):
    d = f"{host.W}/sfx_cache"
    os.makedirs(d, exist_ok=True)
    return f"{d}/el_{tag}_{hashlib.sha1((text + '|' + extra).encode()).hexdigest()[:16]}.mp3"


def available(key):
    return time.time() >= DOWN.get(_kid(key), (0, ""))[0]


def _down(key, r):
    if r.status_code in (401, 402, 403, 429):
        DOWN[_kid(key)] = (time.time() + (120 if r.status_code == 429 else 900), explain(r))


def sfx(host, key, text, duration=None):
    """-> (path, source). Raises RuntimeError with an Arabic reason."""
    if not available(key):
        raise RuntimeError("ElevenLabs متوقف مؤقتاً: " + DOWN[_kid(key)][1])
    text = (text or "").strip()[:200]
    dur = None if duration is None else max(0.5, min(10.0, float(duration)))
    fn = _cache_path(host, "sfx", text, str(dur))
    if os.path.exists(fn) and os.path.getsize(fn) > 800:
        return fn, "ElevenLabs (cache)"
    body = {"text": text, "prompt_influence": 0.5}
    if dur:
        body["duration_seconds"] = dur
    r = requests.post(BASE + "/v1/sound-generation", params={"output_format": "mp3_44100_128"}, headers=_hdr(key), json=body, timeout=60)
    if r.status_code != 200 or len(r.content) < 800:
        _down(key, r)
        raise RuntimeError(explain(r))
    open(fn, "wb").write(r.content)
    return fn, "ElevenLabs"


def music(host, key, style, seconds, prompt=None):
    out_len = int(max(3.0, min(120.0, seconds + 2.0)) * 1000)
    out_len = ((out_len + 4999) // 5000) * 5000  # bucket => better cache hits
    prompt = (prompt or "").strip()[:600] or MUSIC_PROMPTS.get(style) or MUSIC_PROMPTS["chill"]
    if prompt and "instrumental" not in prompt.lower() and "vocals" not in prompt.lower():
        prompt += ", instrumental"
    if not available(key):
        raise RuntimeError("ElevenLabs متوقف مؤقتاً: " + DOWN[_kid(key)][1])
    fn = _cache_path(host, "mus", prompt, str(out_len))
    if os.path.exists(fn) and os.path.getsize(fn) > 5000:
        return fn, "ElevenLabs Music (cache)"
    r = requests.post(BASE + "/v1/music", params={"output_format": "mp3_44100_128"}, headers=_hdr(key),
                      json={"prompt": prompt, "music_length_ms": out_len, "force_instrumental": True}, timeout=240)
    if r.status_code != 200 or len(r.content) < 5000:
        _down(key, r)
        raise RuntimeError(explain(r))
    open(fn, "wb").write(r.content)
    return fn, "ElevenLabs Music"


def stt_words(key, path, lang=""):
    """ElevenLabs Scribe -> (words[{text,start,end}], language)"""
    if not available(key):
        raise RuntimeError("ElevenLabs متوقف مؤقتاً: " + DOWN[_kid(key)][1])
    data = {"model_id": "scribe_v1", "timestamps_granularity": "word", "tag_audio_events": "false"}
    if lang:
        data["language_code"] = lang
    with open(path, "rb") as f:
        r = requests.post(BASE + "/v1/speech-to-text", headers=_hdr(key, None), data=data, files={"file": (os.path.basename(path), f, "audio/wav")}, timeout=600)
    if r.status_code != 200:
        _down(key, r)
        raise RuntimeError(explain(r))
    j = r.json()
    words = [{"text": w["text"].strip(), "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3)}
             for w in j.get("words", []) if w.get("type", "word") == "word" and (w.get("text") or "").strip()]
    return words, j.get("language_code", lang or "")
