# -*- coding: utf-8 -*-
"""Text-to-speech with precise sync: several providers, sentence-level synthesis, word timings (native -> ASR -> proportional)."""
import os, re, io, json, time, base64, asyncio, subprocess, threading, difflib, unicodedata, uuid, traceback
import requests
from flask import request, jsonify

EDGE_VOICES = [
    ("ar-IQ-RanaNeural", "رنا — عراقية (أنثى)"), ("ar-IQ-BasselNeural", "باسل — عراقي (ذكر)"), ("ar-SA-HamedNeural", "حامد — سعودي (ذكر)"), ("ar-SA-ZariyahNeural", "زارية — سعودية (أنثى)"),
    ("ar-EG-SalmaNeural", "سلمى — مصرية (أنثى)"), ("ar-EG-ShakirNeural", "شاكر — مصري (ذكر)"), ("ar-AE-HamdanNeural", "حمدان — إماراتي (ذكر)"), ("ar-JO-TaimNeural", "تيم — أردني (ذكر)"),
    ("ar-LB-LaylaNeural", "ليلى — لبنانية (أنثى)"), ("ar-SY-AmanyNeural", "أماني — سورية (أنثى)"), ("en-US-AriaNeural", "Aria — English US (F)"), ("en-US-GuyNeural", "Guy — English US (M)"),
    ("en-US-AndrewMultilingualNeural", "Andrew — Multilingual (M)"), ("en-US-AvaMultilingualNeural", "Ava — Multilingual (F)"), ("en-GB-SoniaNeural", "Sonia — English UK (F)"), ("en-GB-RyanNeural", "Ryan — English UK (M)"),
    ("tr-TR-AhmetNeural", "Ahmet — Türkçe (M)"), ("fr-FR-DeniseNeural", "Denise — Français (F)"), ("es-ES-ElviraNeural", "Elvira — Español (F)"), ("fa-IR-FaridNeural", "فرید — فارسی (M)"),
]
MINIMAX_VOICES = [("male-qn-qingse", "Qingse (M)"), ("female-shaonv", "Shaonv (F)"), ("female-yujie", "Yujie (F)"), ("male-qn-jingying", "Jingying (M)"), ("presenter_male", "Presenter (M)"), ("presenter_female", "Presenter (F)"),
                  ("audiobook_male_1", "Audiobook (M)"), ("audiobook_female_1", "Audiobook (F)"), ("English_expressive_narrator", "Expressive narrator (EN)")]
OPENAI_VOICES = [(v, v) for v in ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse")]
ELEVEN_FALLBACK = [("21m00Tcm4TlvDq8ikWAM", "Rachel"), ("pNInz6obpgDQGcFmaJgB", "Adam"), ("EXAVITQu4vr4xnSDxMaL", "Sarah"), ("TX3LPaxmHKxFdv7VOQHJ", "Liam")]
_voice_cache = {}


def edge_ok():
    try:
        import edge_tts  # noqa
        return True
    except Exception:
        return False


def available(P):
    out = []
    if edge_ok():
        out.append({"id": "edge", "label": "Edge (مجاني)", "native": True})
    if P.setting("elevenlabs_key"):
        out.append({"id": "elevenlabs", "label": "ElevenLabs", "native": True})
    if P.setting("minimax_key") and P.setting("minimax_group"):
        out.append({"id": "minimax", "label": "MiniMax", "native": False})
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


# ------------------------------------------------------------------ providers: return (mp3_bytes, timed|None)
def synth_edge(text, voice, speed, P):
    import edge_tts
    rate = f"{int(round((speed - 1) * 100)):+d}%"

    async def go():
        try:
            com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
        except TypeError:
            com = edge_tts.Communicate(text, voice, rate=rate)
        audio, timed = bytearray(), []
        async for ch in com.stream():
            if ch["type"] == "audio":
                audio += ch["data"]
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                timed.append((ch["text"], s, s + ch["duration"] / 1e7))
        return bytes(audio), timed
    last = None
    for attempt in range(3):
        try:
            a, t = asyncio.run(go())
            if a:
                return a, t or None
        except Exception as e:
            last = e; time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Edge TTS: {last}")


def synth_eleven(text, voice, speed, P):
    key = P.setting("elevenlabs_key")
    body = {"text": text, "model_id": P.setting("elevenlabs_model") or "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "speed": max(0.7, min(1.2, speed))}}
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps", params={"output_format": "mp3_44100_128"}, headers={"xi-api-key": key}, json=body, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs HTTP {r.status_code}: {r.text[:200]}")
    j = r.json()
    audio = base64.b64decode(j["audio_base64"])
    al = j.get("alignment") or {}
    chars, st, en = al.get("characters") or [], al.get("character_start_times_seconds") or [], al.get("character_end_times_seconds") or []
    timed, cur, s0, e0 = [], "", None, 0
    for c, s, e in zip(chars, st, en):
        if c.isspace():
            if cur:
                timed.append((cur, s0, e0)); cur, s0 = "", None
            continue
        if s0 is None: s0 = s
        cur += c; e0 = e
    if cur:
        timed.append((cur, s0, e0))
    return audio, timed or None


def synth_minimax(text, voice, speed, P):
    base = (P.setting("minimax_base") or "https://api.minimax.io").rstrip("/")
    body = {"model": P.setting("minimax_model") or "speech-02-hd", "text": text, "stream": False,
            "voice_setting": {"voice_id": voice, "speed": max(0.5, min(2.0, speed)), "vol": 1.0, "pitch": 0},
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1}}
    r = requests.post(f"{base}/v1/t2a_v2", params={"GroupId": P.setting("minimax_group")}, headers={"Authorization": "Bearer " + P.setting("minimax_key")}, json=body, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"MiniMax HTTP {r.status_code}: {r.text[:200]}")
    j = r.json()
    br = j.get("base_resp") or {}
    if br.get("status_code", 0) != 0:
        raise RuntimeError(f"MiniMax {br.get('status_code')}: {br.get('status_msg')}")
    return bytes.fromhex(j["data"]["audio"]), None


def synth_openai(text, voice, speed, P):
    base = (P.setting("openai_base") or "https://api.openai.com/v1").rstrip("/")
    r = requests.post(f"{base}/audio/speech", headers={"Authorization": "Bearer " + P.setting("openai_key")},
                      json={"model": P.setting("openai_model") or "gpt-4o-mini-tts", "input": text, "voice": voice, "response_format": "mp3", "speed": max(0.25, min(4.0, speed))}, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"TTS HTTP {r.status_code}: {r.text[:200]}")
    return r.content, None


SYNTH = {"edge": synth_edge, "elevenlabs": synth_eleven, "minimax": synth_minimax, "openai": synth_openai}


def list_voices(P, prov):
    if prov == "edge":
        return EDGE_VOICES
    if prov == "minimax":
        return MINIMAX_VOICES
    if prov == "openai":
        return OPENAI_VOICES
    if prov == "elevenlabs":
        c = _voice_cache.get("el")
        if c and time.time() - c[0] < 600:
            return c[1]
        try:
            r = requests.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": P.setting("elevenlabs_key")}, timeout=20)
            vs = [(v["voice_id"], v["name"] + (" — " + (v.get("labels") or {}).get("accent", "") if (v.get("labels") or {}).get("accent") else "")) for v in r.json().get("voices", [])]
            if vs:
                _voice_cache["el"] = (time.time(), vs)
                return vs
        except Exception:
            pass
        return ELEVEN_FALLBACK
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
        return {"ok": r.status_code == 200, "msg": "Groq يعمل ✓" if r.status_code == 200 else f"HTTP {r.status_code}"}
    if prov in SYNTH:
        if prov == "edge" and not edge_ok(): return {"ok": False, "msg": "مكتبة edge-tts غير مثبتة"}
        voice = {"edge": "en-US-AriaNeural", "elevenlabs": ELEVEN_FALLBACK[0][0], "minimax": "female-shaonv", "openai": "alloy"}[prov]
        if prov == "elevenlabs" and not P.setting("elevenlabs_key"): return {"ok": False, "msg": "المفتاح غير مضبوط"}
        if prov == "minimax" and not (P.setting("minimax_key") and P.setting("minimax_group")): return {"ok": False, "msg": "المفتاح أو Group ID غير مضبوط"}
        if prov == "openai" and not P.setting("openai_key"): return {"ok": False, "msg": "المفتاح غير مضبوط"}
        a, t = SYNTH[prov]("Hello, this is a test.", voice, 1.0, P)
        return {"ok": True, "msg": f"{prov} يعمل ✓ ({len(a) // 1024}KB" + (" + توقيت كلمات أصلي)" if t else ")")}
    return {"ok": False, "msg": "مزوّد غير معروف"}


# ------------------------------------------------------------------ ASR helpers (optional refinement / transcription)
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
            audio, timed = SYNTH[prov](s["text"], voice, speed, P)
            raw = f"{work}/s{i}.mp3"; open(raw, "wb").write(audio)
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
