# -*- coding: utf-8 -*-
"""Text-to-speech with precise sync: Gemini / Groq (Orpheus) / OpenAI-compatible, sentence-level synthesis, word timings (native -> ASR -> proportional)."""
import os, re, io, json, time, base64, subprocess, threading, difflib, unicodedata, uuid, traceback, shutil, tempfile
import requests
from flask import request, jsonify


# Gemini prebuilt voices (name, label). The label shows the voice character; gender is used only to pick a sensible default.
GEMINI_VOICES = [
    ("Kore", "Kore — حازمة (أنثى)"), ("Sulafat", "Sulafat — دافئة (أنثى)"), ("Zephyr", "Zephyr — مشرقة (أنثى)"), ("Aoede", "Aoede — خفيفة (أنثى)"),
    ("Leda", "Leda — شابة (أنثى)"), ("Vindemiatrix", "Vindemiatrix — لطيفة (أنثى)"), ("Gacrux", "Gacrux — ناضجة (أنثى)"), ("Achernar", "Achernar — ناعمة (أنثى)"),
    ("Callirrhoe", "Callirrhoe — مرتاحة (أنثى)"), ("Autonoe", "Autonoe — مشرقة (أنثى)"), ("Despina", "Despina — سلسة (أنثى)"), ("Erinome", "Erinome — واضحة (أنثى)"),
    ("Laomedeia", "Laomedeia — حيوية (أنثى)"), ("Pulcherrima", "Pulcherrima — مباشرة (أنثى)"),
    ("Charon", "Charon — إعلامي (ذكر)"), ("Orus", "Orus — حازم (ذكر)"), ("Puck", "Puck — مرح (ذكر)"), ("Fenrir", "Fenrir — متحمس (ذكر)"),
    ("Enceladus", "Enceladus — هادئ (ذكر)"), ("Iapetus", "Iapetus — واضح (ذكر)"), ("Umbriel", "Umbriel — مرتاح (ذكر)"), ("Algieba", "Algieba — سلس (ذكر)"),
    ("Algenib", "Algenib — خشن (ذكر)"), ("Rasalgethi", "Rasalgethi — إعلامي (ذكر)"), ("Alnilam", "Alnilam — حازم (ذكر)"), ("Schedar", "Schedar — متوازن (ذكر)"),
    ("Achird", "Achird — ودود (ذكر)"), ("Zubenelgenubi", "Zubenelgenubi — عفوي (ذكر)"), ("Sadachbia", "Sadachbia — حيوي (ذكر)"), ("Sadaltager", "Sadaltager — خبير (ذكر)"),
]
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODELS = ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts")  # tried in order after the model set in the admin panel
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL_AR, GROQ_MODEL_EN = "canopylabs/orpheus-arabic-saudi", "canopylabs/orpheus-v1-english"
GROQ_AR_VOICES = ("abdullah", "fahad")
GROQ_VOICES = [("abdullah", "Abdullah — عربي (ذكر)"), ("fahad", "Fahad — عربي (ذكر)"), ("hannah", "Hannah — English (F)"), ("autumn", "Autumn — English (F)"),
               ("diana", "Diana — English (F)"), ("austin", "Austin — English (M)"), ("daniel", "Daniel — English (M)"), ("troy", "Troy — English (M)")]
OPENAI_VOICES = [(v, v) for v in ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse")]
DEFAULT_VOICE = {"gemini": {"female": "Kore", "male": "Charon"}, "groq": {"female": "hannah", "male": "austin"}, "openai": {"female": "nova", "male": "onyx"}}
PROVIDER_ORDER = ("gemini", "groq", "openai")
_voice_cache = {}


def available(P):
    out = []
    if P.setting("gemini_key"):
        out.append({"id": "gemini", "label": "Gemini TTS", "native": False})
    if P.setting("groq_key"):
        out.append({"id": "groq", "label": "Groq (Orpheus)", "native": False})
    if P.setting("openai_key"):
        out.append({"id": "openai", "label": "OpenAI / متوافق", "native": False})
    return out




# ------------------------------------------------------------------ text helpers
def sentences(text, maxlen=420):
    text = re.sub(r"[ \t]+", " ", text.replace("\r", "")).strip()
    out = []
    for para in re.split(r"\n+", text):
        para = para.strip()
        if not para:
            continue
        parts = re.split(r"(?<=[\.\!\?؟۔…])\s+", para)
        for i, s in enumerate(parts):
            s = s.strip()
            while len(s) > maxlen:
                cut = max(s.rfind("،", 0, maxlen), s.rfind(",", 0, maxlen), s.rfind(" ", 0, maxlen))
                cut = cut if cut > 80 else maxlen
                out.append({"text": s[:cut].strip(), "para": False}); s = s[cut:].strip()
            if s:
                out.append({"text": s, "para": i == len(parts) - 1})
    # merge very short neighbours so prosody stays natural
    merged = []
    for s in out:
        if merged and len(merged[-1]["text"]) < 18 and not merged[-1]["para"]:
            merged[-1]["text"] += " " + s["text"]; merged[-1]["para"] = s["para"]
        else:
            merged.append(s)
    return merged


_diac = re.compile(r"[ً-ٰٟۖ-ۭـ]")


def norm(t):
    t = _diac.sub("", unicodedata.normalize("NFKC", t)).lower()
    t = re.sub(r"[أإآٱ]", "ا", t).replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"[^\w]", "", t, flags=re.U)


def align_tokens(script, timed, w0, w1):
    """script: list[str]; timed: list[(text,start,end)] from any source; returns [(start,end)] for every script token inside window [w0,w1]"""
    n = len(script)
    res = [None] * n
    if timed:
        a = [norm(t) for t in script]
        b = [norm(t[0]) for t in timed]
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    res[i1 + k] = (timed[j1 + k][1], timed[j1 + k][2])
            elif tag == "replace" and (i2 - i1) == (j2 - j1):
                for k in range(i2 - i1):
                    res[i1 + k] = (timed[j1 + k][1], timed[j1 + k][2])
        if sum(r is not None for r in res) < 0.5 * n:  # too little agreement -> do not trust
            res = [None] * n
    # interpolate the gaps proportionally to character length
    i = 0
    while i < n:
        if res[i] is not None:
            i += 1; continue
        j = i
        while j < n and res[j] is None:
            j += 1
        left = res[i - 1][1] if i > 0 else w0
        right = res[j][0] if j < n else w1
        right = max(right, left + 0.05 * (j - i))
        wt = [len(script[k]) + 1 for k in range(i, j)]
        tot = float(sum(wt)); acc = left
        for k, w in zip(range(i, j), wt):
            d = (right - left) * w / tot
            res[k] = (acc, acc + d); acc += d
        i = j
    # monotonic + sane durations
    prev = w0
    out = []
    for s, e in res:
        s = max(s, prev); e = max(e, s + 0.06); out.append((round(s, 3), round(e, 3))); prev = e
    return out


# ------------------------------------------------------------------ audio helpers
def ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + r.stderr[-400:])


def dur_of(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def speech_window(path, total):
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af", "silencedetect=noise=-42dB:d=0.06", "-f", "null", "-"], capture_output=True, text=True)
    st = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    s0, e0 = 0.0, total
    if st and st[0] <= 0.02 and en:
        s0 = max(0.0, en[0] - 0.03)
    if st and len(st) > len(en) - (1 if (st and st[0] <= 0.02) else 0) and st[-1] > total * 0.5:
        e0 = min(total, st[-1] + 0.04)
    return s0, max(e0, s0 + 0.1)



# ------------------------------------------------------------------ providers: return (audio_bytes, timed|None)
# None for `timed` is normal: none of the three returns word timings, so the pipeline aligns words with ASR (Groq / local Whisper).
def _api_msg(r):
    return re.sub(r"(api_key|key)[:=]\s*\S+", r"\1:***", _api_msg_raw(r))


def _api_msg_raw(r):
    try:
        j = r.json()
        e = j.get("error") if isinstance(j, dict) else None
        if isinstance(e, dict): return str(e.get("message") or e)[:220]
        if e: return str(e)[:220]
        return str(j.get("detail") or j.get("message") or j)[:220]
    except Exception:
        return (r.text or "")[:220]


def _wav_from_pcm(pcm, rate=24000):
    import wave
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return b.getvalue()


def _tempo(data, speed, ext):
    """Gemini and Groq have no speed control: change the pace with ffmpeg atempo (pitch is preserved)."""
    if abs(speed - 1.0) < 0.03:
        return data
    d = tempfile.mkdtemp()
    try:
        a, b = os.path.join(d, "i." + ext), os.path.join(d, "o." + ext)
        open(a, "wb").write(data)
        ffmpeg(["-i", a, "-filter:a", f"atempo={max(0.5, min(2.0, speed)):.3f}", b])
        return open(b, "rb").read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _gemini_pcm(j):
    for c in j.get("candidates") or []:
        for p in (c.get("content") or {}).get("parts") or []:
            d = p.get("inlineData") or p.get("inline_data") or {}
            if d.get("data"):
                m = re.search(r"rate=(\d+)", d.get("mimeType") or d.get("mime_type") or "")
                return base64.b64decode(d["data"]), (int(m.group(1)) if m else 24000)
    return None


def synth_gemini(text, voice, speed, P, lang=None, style=None):
    """Gemini TTS (generateContent -> raw PCM 24 kHz). `style` is a natural-language delivery hint, e.g. "warm, calm documentary tone"."""
    key = P.setting("gemini_key")
    if not key:
        raise RuntimeError("Gemini: المفتاح غير مضبوط")
    models = [m for m in dict.fromkeys([P.setting("gemini_model") or "", *GEMINI_MODELS]) if m]
    prompt = f"{style.strip().rstrip(':')}: {text}" if style and style.strip() else text
    last = None
    for model in models:
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
        for attempt in range(3):
            try:
                r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=150)
            except requests.RequestException as e:
                last = f"Gemini: تعذّر الاتصال ({str(e)[:80]})"; time.sleep(1.5 * (attempt + 1)); continue
            if r.status_code == 200:
                got = _gemini_pcm(r.json())
                if got:
                    return _tempo(_wav_from_pcm(got[0], got[1]), speed, "wav"), None
                last = f"Gemini ({model}): لم يرجع صوتاً"; time.sleep(1.0 + attempt); continue  # the model sometimes answers with text only -> retry
            msg = _api_msg(r)
            last = f"Gemini HTTP {r.status_code} ({model}): {msg}"
            if r.status_code in (400, 401, 403) and re.search(r"suspend|api key|permission|denied|invalid", msg, re.I):
                if re.search(r"suspend", msg, re.I):
                    raise RuntimeError("Gemini: Google أوقفت هذا المشروع/الحساب (CONSUMER_SUSPENDED) — مفتاح جديد من نفس المشروع سيفشل أيضاً. أنشئ المفتاح داخل مشروع جديد أو بحساب Google آخر من aistudio.google.com، أو اختر Groq")
                raise RuntimeError("Gemini: المفتاح مرفوض من Google — تأكد أنه منسوخ كاملاً وأن Generative Language API مفعّل (" + msg[:90] + ")")
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2.5 * (attempt + 1)); continue
            if r.status_code in (400, 404) and re.search(r"model|not found|not supported|unsupported", msg, re.I) and not re.search(r"api key", msg, re.I):
                break  # this model is not available for the key -> next model
            raise RuntimeError(last)
    raise RuntimeError(last or "Gemini: فشل التوليد")


def _wav_concat(parts):
    import wave
    out = io.BytesIO(); w = None
    for p in parts:
        r = wave.open(io.BytesIO(p), "rb")
        if w is None:
            w = wave.open(out, "wb"); w.setparams(r.getparams())
        w.writeframes(r.readframes(r.getnframes())); r.close()
    w.close()
    return out.getvalue()


def synth_groq(text, voice, speed, P, lang=None, style=None):
    """Groq TTS (Canopy Labs Orpheus): Arabic-Saudi voices use the Saudi model, English voices the English model. Input is limited to ~200 chars per request, so the line is split and the wavs are joined."""
    key = P.setting("groq_key")
    if not key:
        raise RuntimeError("Groq: المفتاح غير مضبوط")
    model = GROQ_MODEL_AR if voice in GROQ_AR_VOICES else GROQ_MODEL_EN
    chunks = [c["text"] for c in sentences(text, 170)] or [text]
    wavs = []
    for ch in chunks:
        last = None
        for attempt in range(3):
            try:
                r = requests.post(f"{GROQ_BASE}/audio/speech", headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                                  json={"model": model, "input": ch, "voice": voice, "response_format": "wav"}, timeout=120)
            except requests.RequestException as e:
                last = f"Groq: تعذّر الاتصال ({str(e)[:80]})"; time.sleep(1.5 * (attempt + 1)); continue
            if r.status_code == 200 and r.content[:4] == b"RIFF":
                wavs.append(r.content); last = None; break
            msg = _api_msg(r)
            last = f"Groq HTTP {r.status_code} ({model}): {msg}"
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2.5 * (attempt + 1)); continue
            if re.search(r"terms|accept", msg, re.I):
                last += " — فعّل شروط الموديل من console.groq.com (Playground) ثم أعد المحاولة"
            raise RuntimeError(last)
        if last:
            raise RuntimeError(last)
    return _tempo(_wav_concat(wavs), speed, "wav"), None


def synth_openai(text, voice, speed, P, lang=None, style=None):
    base = (P.setting("openai_base") or "https://api.openai.com/v1").rstrip("/")
    model = P.setting("openai_model") or "gpt-4o-mini-tts"
    body = {"model": model, "input": text, "voice": voice, "response_format": "mp3", "speed": max(0.25, min(4.0, speed))}
    if style and "gpt-4o" in model:
        body["instructions"] = style[:300]
    r = requests.post(f"{base}/audio/speech", headers={"Authorization": "Bearer " + P.setting("openai_key")}, json=body, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"TTS HTTP {r.status_code}: {r.text[:200]}")
    return r.content, None


SYNTH = {"gemini": synth_gemini, "groq": synth_groq, "openai": synth_openai}


def list_voices(P, prov):
    if prov == "gemini":
        return GEMINI_VOICES
    if prov == "groq":
        return GROQ_VOICES
    if prov == "openai":
        return OPENAI_VOICES
    return []


def test_provider(P, prov):
    if prov == "freesound":
        k = P.setting("freesound_key")
        if not k: return {"ok": False, "msg": "المفتاح غير مضبوط"}
        r = requests.get("https://freesound.org/apiv2/search/text/", params={"query": "whoosh", "page_size": 1, "token": k}, timeout=20)
        return {"ok": r.status_code == 200, "msg": "Freesound يعمل ✓" if r.status_code == 200 else f"HTTP {r.status_code}: {r.text[:120]} — تأكد أنه API Key (وليس Client secret)"}
    if prov == "groq":
        k = P.setting("groq_key")
        if not k: return {"ok": False, "msg": "المفتاح غير مضبوط"}
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": "Bearer " + k}, timeout=20)
        if r.status_code != 200: return {"ok": False, "msg": f"HTTP {r.status_code}"}
        try:
            a, _t = synth_groq("مرحباً بكم.", "abdullah", 1.0, P, lang="ar")
            return {"ok": True, "msg": f"Groq يعمل ✓ (تفريغ + صوت عربي، عيّنة {len(a) // 1024}KB)"}
        except Exception as e:
            return {"ok": True, "msg": "Groq يعمل للتفريغ ✓ — الصوت غير متاح: " + str(e)[:170]}
    if prov in SYNTH:
        if not P.setting(prov + "_key"): return {"ok": False, "msg": "المفتاح غير مضبوط"}
        a, _t = SYNTH[prov]("Hello, this is a test.", DEFAULT_VOICE[prov]["female"], 1.0, P, lang="en")
        label = {"gemini": "Gemini", "openai": "OpenAI"}[prov]
        return {"ok": True, "msg": f"{label} يعمل ✓ (عيّنة {len(a) // 1024}KB)"}
    return {"ok": False, "msg": "مزوّد غير معروف"}



# ------------------------------------------------------------------ ASR helpers (word timings for providers that have none / transcription)
def groq_words(P, path, lang=""):
    key = P.setting("groq_key")
    if not key or os.path.getsize(path) > 24 * 1024 * 1024:
        return None
    with open(path, "rb") as f:
        r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"Authorization": "Bearer " + key}, timeout=180,
                          files={"file": (os.path.basename(path), f, "audio/wav")},
                          data={"model": "whisper-large-v3-turbo", "response_format": "verbose_json", "timestamp_granularities[]": "word", **({"language": lang} if lang else {})})
    if r.status_code != 200:
        raise RuntimeError(f"Groq HTTP {r.status_code}: {r.text[:150]}")
    j = r.json()
    words = [{"text": w["word"].strip(), "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3)} for w in j.get("words", []) if w.get("word", "").strip()]
    return words, j.get("language", lang or "")



def asr_timed(host, P, J, wav, lang):
    """word timings for audio that has none: Groq Whisper (fast) -> local faster-whisper"""
    try:
        g = groq_words(P, wav, lang)
        if g and g[0]:
            return [(w["text"], w["start"], w["end"]) for w in g[0]]
    except Exception as e:
        print("groq asr failed:", e, flush=True)
    try:
        import faster_whisper  # noqa
        words, _ = host.run_asr(J["_jid"], wav, lang, "small", "cuda" if host.GPU else "cpu")
        return [(w["text"], w["start"], w["end"]) for w in words]
    except Exception as e:
        print("local asr unavailable:", e, flush=True)
        return None



# ------------------------------------------------------------------ code-driven narration (export const NARRATION = [...])
def parse_narration(code):
    """`export const NARRATION = [{ text: "...", t: 0.4, pause: 0.5, voice: "...", speed: 1 }, ...]` -> (lines, opts). Header options come
    from an optional first object without text: { provider, voice, lang, gender, style, speed, gap }."""
    import sa_audio
    body = sa_audio._scan(code, "NARRATION", "[", "]")
    if body is None:
        return None
    lines, opts = [], {}
    for o in sa_audio._objects(body):
        text = sa_audio._str(o, "text")
        if not text:
            for k in ("provider", "voice", "lang", "gender", "style"):
                v = sa_audio._str(o, k)
                if v: opts[k] = v
            if sa_audio._num(o, "speed"): opts["speed"] = sa_audio._num(o, "speed")
            if sa_audio._num(o, "gap") is not None: opts["gap"] = sa_audio._num(o, "gap")
            continue
        lines.append({"text": re.sub(r"\s+", " ", text)[:600], "t": sa_audio._num(o, "t"), "pause": sa_audio._num(o, "pause"),
                      "voice": sa_audio._str(o, "voice"), "speed": sa_audio._num(o, "speed")})
    return (lines[:60], opts) if lines else None


def narration_chars(lines):
    return sum(len(x["text"]) for x in lines)


_LEGACY_VOICE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}(-[A-Za-z]+)?-\w+Neural$")  # old Edge voice ids in saved scripts


def _pick_voice(P, prov, want, lang, gender, keep=True):
    """`want` is honoured only for the provider the script asked for (keep=True); a fallback provider uses its own default for the gender."""
    want = (want or "").strip() if keep else ""
    if want and _LEGACY_VOICE.fullmatch(want):
        want = ""
    vs = list_voices(P, prov) or []
    if want:
        ids = {v.lower(): v for v, _n in vs}
        if want.lower() in ids:
            return ids[want.lower()]
        for vid, name in vs:  # a voice NAME or part of it
            if want.lower() in name.lower():
                return vid
        if prov == "openai" and re.fullmatch(r"[A-Za-z0-9_.:\-]{1,80}", want):
            return want  # a custom / cloned voice id of the account
    g = gender if gender in ("male", "female") else "female"
    if prov == "groq" and (lang or "ar") == "ar":
        return "abdullah"  # the Saudi Arabic voices are male (abdullah, fahad)
    return DEFAULT_VOICE.get(prov, {}).get(g) or (vs[0][0] if vs else "")


def narrate(host, P, J, jid, lines, opts):
    """Generate the narration; if the chosen provider fails, fall back to the next available one (with a note)."""
    avail = [p["id"] for p in available(P)]
    asked = (opts.get("provider") or "").strip().lower()
    if asked in ("auto", "any", "default"):
        asked = ""  # automatic: the studio picks the first provider that has a key (gemini -> groq -> openai)
    first = asked if asked in avail else None
    chain = ([first] if first else []) + [x for x in PROVIDER_ORDER if x in avail and x != first]
    if not chain:
        raise RuntimeError("لا يوجد مزوّد صوت متاح: أضف مفتاح Gemini أو Groq (أو OpenAI) من «مفاتيحي الخاصة».")
    notes, last = [], None
    if asked and not first:
        notes.append(f"المزوّد «{asked}» غير متاح في الاستوديو — استُخدم {chain[0]}.")
    for idx, prov in enumerate(chain):
        try:
            res = _narrate(host, P, J, jid, lines, opts, prov, keep_voice=(idx == 0))
            res["notes"] = notes
            return res
        except RuntimeError as e:
            if "الإلغاء" in str(e):
                raise
            last = e
            notes.append(f"{prov}: {str(e)[:200]}" + (" — جارٍ استخدام مزوّد آخر" if prov != chain[-1] else ""))
        except Exception as e:
            last = e
            notes.append(f"{prov}: {str(e)[:200]}")
    raise RuntimeError("تعذّر توليد الصوت عبر كل المزوّدين: " + " | ".join(notes))



def _narrate(host, P, J, jid, lines, opts, prov, keep_voice=True):
    lang = (opts.get("lang") or "ar")[:2].lower()
    base_speed = max(0.7, min(1.25, float(opts.get("speed") or 1.0)))
    gap = max(0.05, min(2.0, float(opts.get("gap") if opts.get("gap") is not None else 0.35)))
    work = f"{host.W}/uploads/{jid}_narr"
    os.makedirs(work, exist_ok=True)
    try:
        parts, scenes, words, cursor, any_native = [], [], [], 0.0, False
        moved = []
        n = len(lines)
        for i, ln in enumerate(lines):
            J.update(stage=f"توليد الصوت {i + 1}/{n} ({prov})", progress=3 + int(12 * i / max(1, n)))
            if J.get("cancelled"):
                raise RuntimeError("تم الإلغاء")
            voice = _pick_voice(P, prov, ln.get("voice") or opts.get("voice"), lang, opts.get("gender"), keep=keep_voice)
            audio, timed = SYNTH[prov](ln["text"], voice, max(0.7, min(1.25, ln.get("speed") or base_speed)), P, lang=lang, style=opts.get("style"))
            raw = f"{work}/s{i}.aud"; open(raw, "wb").write(audio)
            wav = f"{work}/s{i}.wav"
            ffmpeg(["-i", raw, "-ar", "48000", "-ac", "1", wav])
            total = dur_of(wav)
            w0, w1 = speech_window(wav, total)
            want = ln.get("t")
            if i == 0 and want is None:
                want = 0.4
            if want is not None and want > cursor + 0.01:  # exact placement: pad silence up to t
                sil = f"{work}/p{i}.wav"
                ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{want - cursor:.3f}", sil]); parts.append(sil)
                cursor = want
            elif want is not None and want < cursor - 0.01:
                moved.append((i + 1, round(want, 2), round(cursor, 2)))
            toks = ln["text"].split()
            if timed:
                any_native = True
            pairs = align_tokens(toks, timed, w0, w1)
            for t, (a, b) in zip(toks, pairs):
                words.append({"text": t, "start": round(cursor + a, 3), "end": round(cursor + b, 3)})
            scenes.append({"text": ln["text"], "start": round(cursor + w0, 3), "end": round(cursor + w1, 3), "i": i})
            parts.append(wav)
            cursor += total
            pad = ln.get("pause") if ln.get("pause") is not None else gap
            if i < n - 1 and pad > 0:
                sil = f"{work}/g{i}.wav"
                ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{pad:.3f}", sil]); parts.append(sil)
                cursor += pad
        lst = f"{work}/list.txt"
        open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
        full = f"{host.W}/out/{jid}_narr.wav"
        os.makedirs(os.path.dirname(full), exist_ok=True)
        ffmpeg(["-f", "concat", "-safe", "0", "-i", lst, "-c:a", "pcm_s16le", full])
        if not any_native:  # providers without native timings: refine with ASR when available (sentence windows stay exact)
            J.update(stage="مزامنة الكلمات بالتفريغ", progress=16)
            J["_jid"] = jid
            timed = asr_timed(host, P, J, full, lang)
            if timed:
                pairs = align_tokens([w["text"] for w in words], timed, 0.0, cursor)
                k = 0
                for sc in scenes:
                    cnt = len(lines[sc["i"]]["text"].split())
                    for q in range(k, k + cnt):
                        a, b = pairs[q]
                        a = min(max(a, sc["start"] - 0.05), sc["end"]); b = min(max(b, a + 0.06), sc["end"] + 0.05)
                        words[q]["start"], words[q]["end"] = round(a, 3), round(b, 3)
                    k += cnt
        segs = host.build_segments(words, 3)
        for sc in scenes:
            sc.pop("i", None)
        return {"path": full, "words": words, "segments": segs, "scenes": scenes, "end": round(cursor, 3), "provider": prov, "voice": voice,
                "chars": narration_chars(lines), "moved": moved, "native": any_native}
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------ job
def tts_job(host, P, jid, uid, d):
    J = host.JOBS[jid]
    work = f"{host.W}/uploads/{jid}_tts"
    os.makedirs(work, exist_ok=True)
    try:
        prov, voice = d["provider"], d["voice"]
        speed = max(0.6, min(1.5, float(d.get("speed", 1.0) or 1.0)))
        gap = max(0.0, min(1.5, float(d.get("gap", 0.18))))
        sents = sentences(d["text"])
        if not sents:
            raise RuntimeError("النص فارغ")
        n = len(sents)
        parts, cursor, scenes, all_words, any_native = [], 0.0, [], [], False
        precise = d.get("precise", True)
        for i, s in enumerate(sents):
            J.update(stage=f"توليد الصوت {i + 1}/{n}", progress=5 + int(70 * i / n))
            if J.get("cancelled"):
                raise RuntimeError("تم الإلغاء")
            audio, timed = SYNTH[prov](s["text"], voice, speed, P, lang=((d.get("lang") or "")[:2].lower() or None))
            raw = f"{work}/s{i}.aud"; open(raw, "wb").write(audio)
            wav = f"{work}/s{i}.wav"
            ffmpeg(["-i", raw, "-ar", "48000", "-ac", "1", wav])
            total = dur_of(wav)
            w0, w1 = speech_window(wav, total)
            toks = s["text"].split()
            if timed:
                any_native = True
            pairs = align_tokens(toks, timed, w0, w1)
            for t, (a, b) in zip(toks, pairs):
                all_words.append({"text": t, "start": round(cursor + a, 3), "end": round(cursor + b, 3)})
            scenes.append({"text": s["text"], "start": round(cursor + w0, 3), "end": round(cursor + w1, 3), "i": i})
            parts.append(wav)
            pad = gap + (0.32 if s["para"] else 0.0)
            if i < n - 1 and pad > 0:
                sil = f"{work}/g{i}.wav"
                ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{pad:.3f}", sil]); parts.append(sil)
                cursor += total + pad
            else:
                cursor += total
        J.update(stage="دمج المقاطع", progress=80)
        lst = f"{work}/list.txt"
        open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
        full = f"{work}/full.wav"
        ffmpeg(["-f", "concat", "-safe", "0", "-i", lst, "-c:a", "pcm_s16le", full])
        if precise and (not any_native or d.get("force_asr")):
            J.update(stage="مزامنة دقيقة بالتفريغ", progress=84)
            J["_jid"] = jid
            timed = asr_timed(host, P, J, full, d.get("lang", ""))
            if timed:
                toks = [w["text"] for w in all_words]
                pairs = align_tokens(toks, timed, 0.0, cursor)
                # sentence boundaries are exactly known: keep every word inside its own sentence window
                k = 0
                for sc in scenes:
                    cnt = len(sents[sc["i"]]["text"].split())
                    for q in range(k, k + cnt):
                        a, b = pairs[q]
                        a = min(max(a, sc["start"] - 0.05), sc["end"]); b = min(max(b, a + 0.06), sc["end"] + 0.05)
                        all_words[q]["start"], all_words[q]["end"] = round(a, 3), round(b, 3)
                    k += cnt
        J.update(stage="تجهيز الملف", progress=90)
        base = uuid.uuid4().hex[:10]
        title = "🎙 " + re.sub(r"\s+", " ", d["text"]).strip()[:36]
        rec = host.finalize_media(J, full, title, base)
        rec["words"] = all_words
        rec["segments"] = host.build_segments(all_words, int(d.get("max_words", 3) or 3))
        rec["scenes"] = scenes
        rec["source"] = "tts"
        rec["tts"] = {"provider": prov, "voice": voice, "native_timing": any_native}
        host.MEDIA[rec["file"]] = rec
        host.save_meta(host.MEDIA)
        P.bump(uid, tts_chars=len(d["text"]))
        P.audit("tts", uid, "", f"{prov}/{voice} {len(d['text'])}ch")
        J.update(status="done", progress=100, result=rec)
    except Exception as e:
        traceback.print_exc()
        J.update(status="error", error=str(e)[:600])
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


TTS_LOCK = threading.Lock()


def register(app, P):
    host = P.h

    @app.route("/api/tts/voices")
    def tts_voices():
        prov = request.args.get("provider", "")
        return jsonify({"providers": available(P), "voices": [{"id": a, "name": b} for a, b in list_voices(P, prov)] if prov else []})

    @app.route("/api/tts", methods=["POST"])
    def tts_start():
        d = request.get_json(silent=True) or {}
        text = str(d.get("text", "")).strip()
        prov = d.get("provider", "")
        avail = {p["id"] for p in available(P)}
        if prov not in avail:
            return jsonify({"error": "مزوّد الصوت غير متاح — اطلب من المدير ضبط المفتاح."}), 400
        voice = str(d.get("voice") or "").strip()
        if not voice or not re.fullmatch(r"[A-Za-z0-9_.:\-]{1,80}", voice):
            return jsonify({"error": "معرّف الصوت غير صالح"}), 400
        if not text:
            return jsonify({"error": "اكتب النص أولاً"}), 400
        u = P.me()
        q = P.quotas(u)
        left = q.get("tts_chars_day", 0) - P.usage(u["id"]).get("tts_chars", 0)
        if len(text) > min(8000, max(left, 0)):
            return jsonify({"error": f"حصة TTS اليومية المتبقية {max(left, 0)} حرف (النص {len(text)})."}), 429
        with TTS_LOCK:
            if any(j.get("status") == "processing" and j.get("kind") == "tts" and j.get("owner") == u["id"] for j in list(host.JOBS.values())):
                return jsonify({"error": "لديك توليد صوت قيد التنفيذ."}), 409
            jid = host.job(kind="tts", stage="بدء")
        d.update(text=text, provider=prov, voice=voice)
        threading.Thread(target=tts_job, args=(host, P, jid, u["id"], d), daemon=True).start()
        return jsonify({"job_id": jid})
