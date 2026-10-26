# -*- coding: utf-8 -*-
"""Audio finishing: sound effects (Freesound or synthesized), background music with voice ducking, visible diagnostics."""
import os, re, json, time, subprocess, math

SFX_VOL = 0.55
MUSIC_VOL = 0.4
STYLES = {
    "chill": {"label": "هادئ", "query": "chill ambient background music loop", "bpm": 72, "chords": [(57, 0, 3, 7), (53, 0, 4, 7), (48, 0, 4, 7), (55, 0, 4, 7)], "pulse": 0.0, "lp": 2200},
    "upbeat": {"label": "حماسي", "query": "upbeat energetic background music loop corporate", "bpm": 118, "chords": [(48, 0, 4, 7), (55, 0, 4, 7), (57, 0, 3, 7), (53, 0, 4, 7)], "pulse": 0.55, "lp": 4200},
    "cinematic": {"label": "سينمائي", "query": "cinematic epic dramatic background music", "bpm": 60, "chords": [(50, 0, 3, 7), (46, 0, 4, 7), (53, 0, 4, 7), (48, 0, 4, 7)], "pulse": 0.15, "lp": 1800},
    "lofi": {"label": "لو-فاي", "query": "lofi chill hip hop beat background loop", "bpm": 80, "chords": [(50, 0, 3, 7, 10), (55, 0, 3, 7, 10), (53, 0, 4, 7, 11), (48, 0, 4, 7, 11)], "pulse": 0.3, "lp": 1500},
}


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def synth_music(host, style, dur, out):
    """chord-pad music generated with ffmpeg only (no downloads, always available)"""
    st = STYLES.get(style) or STYLES["chill"]
    beat = 60.0 / st["bpm"]
    L = beat * 4                      # one chord = one bar
    total = L * len(st["chords"])
    parts = []
    for i, ch in enumerate(st["chords"]):
        root = ch[0]
        notes = "+".join(f"sin(2*PI*{midi(root + iv):.3f}*t)" for iv in ch[1:])
        bass = f"1.1*sin(2*PI*{midi(root - 12):.3f}*t)"
        parts.append(f"between(mod(t,{total:.4f}),{i * L:.4f},{(i + 1) * L:.4f})*({notes}+{bass})")
    env = f"min(1,mod(t,{L:.4f})/0.35)*min(1,({L:.4f}-mod(t,{L:.4f}))/0.5)"
    pulse = f"(1-{st['pulse']}+{st['pulse']}*pow(sin(PI*mod(t,{beat:.4f})/{beat:.4f}),2))" if st["pulse"] else "1"
    expr = f"0.2*({'+'.join(parts)})*{env}*{pulse}"
    tmp = out + ".loop.wav"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={total:.3f}", "-af",
                        f"lowpass=f={st['lp']},aecho=0.7:0.55:{int(beat * 750)}:0.28,aformat=channel_layouts=stereo", tmp], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("synth music: " + r.stderr[-300:])
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", tmp, "-t", f"{dur:.3f}", "-c:a", "aac", "-b:a", "160k", out], capture_output=True, text=True)
    os.remove(tmp)
    if r.returncode != 0:
        raise RuntimeError("synth loop: " + r.stderr[-300:])
    return out


def fs_music(host, style, key, dur, out, query=None):
    """Freesound background track (CC0 first). Returns (path, source) or raises"""
    import requests
    st = STYLES.get(style) or STYLES["chill"]
    base = "https://freesound.org/apiv2/search/text/"
    last = None
    for lic in ('license:"Creative Commons 0" ', ""):
        r = requests.get(base, timeout=20, params={"query": query or st["query"], "filter": lic + "duration:[25 TO 240]", "sort": "rating_desc", "fields": "id,name,previews,username,license,duration", "page_size": 10, "token": key},
                         headers={"Authorization": "Token " + key, "User-Agent": "SA-Motion-Studio/11"})
        if r.status_code != 200:
            raise RuntimeError(f"Freesound HTTP {r.status_code}")
        res = r.json().get("results", [])
        if res:
            s = res[int(hash(style + str(int(dur))) % len(res))]
            pv = s.get("previews") or {}
            url = pv.get("preview-hq-mp3") or pv.get("preview-lq-mp3")
            a = requests.get(url, timeout=40)
            if not a.ok or len(a.content) < 5000:
                last = "preview download failed"
                continue
            raw = out + ".src.mp3"
            open(raw, "wb").write(a.content)
            rr = subprocess.run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", raw, "-t", f"{dur:.3f}", "-af", "aformat=channel_layouts=stereo", "-c:a", "aac", "-b:a", "160k", out], capture_output=True, text=True)
            os.remove(raw)
            if rr.returncode != 0:
                raise RuntimeError("music loop: " + rr.stderr[-200:])
            return out, f"Freesound #{s['id']} «{s.get('name','')[:30]}» by {s.get('username')} ({'CC0' if lic else s.get('license','').split('/')[-2:-1] or 'license?'})"
    raise RuntimeError(last or "لا نتائج موسيقى في Freesound")


def fs_sfx(host, key, query, variant):
    """a recorded sound-effect from Freesound for a free-text query (cached). -> (path, source)"""
    import hashlib, requests
    q = (query or "").strip()
    fn = f"{host.W}/sfx_cache/fsq_{hashlib.sha1(q.encode()).hexdigest()[:14]}_{variant % 3}.mp3"
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    if os.path.exists(fn) and os.path.getsize(fn) > 1000:
        return fn, "Freesound (cache)"
    res = host.fs_search(q, key)
    if not res:
        raise RuntimeError("لا نتائج في Freesound لـ «" + q[:30] + "»")
    sres = res[variant % len(res)]
    pv = sres.get("previews") or {}
    url = pv.get("preview-hq-mp3") or pv.get("preview-lq-mp3")
    a = requests.get(url, timeout=20) if url else None
    if a is None or not a.ok or len(a.content) < 1000:
        raise RuntimeError("تعذّر تنزيل المعاينة")
    open(fn, "wb").write(a.content)
    return fn, f"Freesound #{sres['id']} by {sres.get('username', '?')}"


_STOP = {"a", "an", "the", "and", "with", "of", "in", "on", "to", "for", "that", "then", "builds", "gently", "bpm", "instrumental", "sound", "sounds", "effect", "effects", "sfx", "very", "soft", "slow", "fast", "deep", "long", "tail"}


def _kw(text, n=5):
    """a long description -> a few Freesound search words (Freesound ANDs every word, so short queries find more)"""
    ws = [w for w in re.findall(r"[A-Za-z][A-Za-z\-']+", text or "") if w.lower() not in _STOP]
    return " ".join(ws[:n])


def get_music(host, style, key, dur, jid, warns, spec=None):
    """background music: a real Freesound track looped to length (search words: spec.fs, else keywords of spec.prompt, else the style default); else a pad synthesized locally."""
    out = f"{host.W}/out/{jid}_music.m4a"
    spec = spec or {}
    if style not in STYLES:
        style = "chill"
    if key:
        for q in [x for x in (spec.get("fs"), _kw(spec.get("prompt"))) if x] + [None]:
            try:
                return fs_music(host, style, key, dur, out, q)
            except Exception as e:
                warns.append(f"موسيقى Freesound ({q or 'افتراضي'}): {e}")
    else:
        warns.append("لا يوجد مفتاح Freesound للموسيقى — استُخدمت موسيقى مولّدة بسيطة. أضف المفتاح من «مفاتيحي الخاصة».")
    return synth_music(host, style, dur, out), f"مولّدة محلياً ({STYLES[style]['label']})"


def detect_cuts(host, video, duration, maxn=40):
    if not video or not os.path.exists(video):
        return []
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", video, "-vf", "select='gt(scene,0.28)',showinfo", "-an", "-f", "null", "-"], capture_output=True, text=True)
    ts, last = [], -9
    for t in re.findall(r"pts_time:([\d.]+)", r.stderr):
        t = float(t)
        if t - last >= 0.9 and 0.2 < t < duration - 0.3:
            ts.append(t); last = t
    return ts[:maxn]


def _nw(x):
    return re.sub(r"[^\w]", "", re.sub(r"[\u064B-\u065F\u0670]", "", (x or "").lower()))


def _num(obj, k):
    m = re.search(r"\b" + k + r"\s*:\s*(-?[\d.]+)", obj)
    try: return float(m.group(1)) if m else None
    except ValueError: return None


def _str(obj, k):
    """string value of key k: "..." / '...' / `...` (quotes of the other kinds and escaped quotes allowed inside)"""
    m = re.search(r"\b" + k + r"\s*:\s*(?:\"((?:[^\"\\]|\\.)*)\"|'((?:[^'\\]|\\.)*)'|`([^`]*)`)", obj)
    if not m:
        return None
    v = next(g for g in m.groups() if g is not None)
    return re.sub(r"\\(.)", r"\1", v).strip() or None


def _scan(code, name, opener, closer):
    """text between the opener/closer that follow `export const NAME [: type] =` — string-aware, so `]`/`}` inside strings are safe"""
    m = re.search(r"export\s+const\s+" + name + r"\b\s*(?::[^=]+)?=\s*" + re.escape(opener), code or "")
    if not m:
        return None
    i, depth, q = m.end(), 1, None
    while i < len(code):
        c = code[i]
        if q:
            if c == "\\":
                i += 1
            elif c == q:
                q = None
        elif c in "\"'`":
            q = c
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return code[m.end():i]
        i += 1
    return None


def _objects(body):
    """top-level {...} items of an array body (string-aware)"""
    out, i, n = [], 0, len(body)
    while i < n:
        if body[i] == "{":
            depth, j, q = 1, i + 1, None
            while j < n and depth:
                c = body[j]
                if q:
                    if c == "\\":
                        j += 1
                    elif c == q:
                        q = None
                elif c in "\"'`":
                    q = c
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                j += 1
            out.append(body[i + 1:j - 1]); i = j
        else:
            i += 1
    return out


def parse_music(code):
    """`export const MUSIC = { style: "upbeat", fs: "search words", prompt: "optional description (its keywords are used when fs is missing)" }`"""
    b = _scan(code, "MUSIC", "{", "}")
    if b is None:
        return None
    src = (_str(b, "source") or "").lower()
    return {"prompt": (_str(b, "prompt") or "")[:300], "style": (_str(b, "style") or "").lower(), "fs": (_str(b, "fs") or "")[:80],
            "source": "freesound" if src == "freesound" else ""}


def smart_plan(host, code, duration, words, raw_video, owner, warns):
    """Code-driven sound design. Each entry of `export const SFX = [...]` may be placed by
       t (seconds) | rt (0..1 of the video) | word:"text" (+nth) | scene:N (N-th cut)   [+ offset]
       and can play a built-in `kind` or one of the user's own library files via `file`.
       `export const SYNC = { snap: 0.3 }` snaps every cue to the nearest spoken-word start or scene cut."""
    body = _scan(code, "SFX", "[", "]")
    if body is None:
        return None, None
    snap = 0.0
    msy = _scan(code, "SYNC", "{", "}")
    if msy is not None:
        snap = max(0.0, min(1.5, _num(msy, "snap") or 0.0))
    entries = _objects(body)
    need_cuts = snap > 0 or any(re.search(r"\bscene\s*:", e) for e in entries)
    cuts = detect_cuts(host, raw_video, duration) if need_cuts else []
    anchors = sorted([w["start"] for w in words] + cuts)
    nwords = [(_nw(w.get("text")), w) for w in words]
    plan, how, snapped = [], {"t": 0, "word": 0, "scene": 0, "rt": 0}, 0
    for e in entries:
        kind, fname, prompt, fsq = _str(e, "kind"), _str(e, "file"), _str(e, "sfx"), _str(e, "fs")
        if not (kind or fname or prompt or fsq):
            continue
        t, via = _num(e, "t"), "t"
        if t is None and _num(e, "rt") is not None:
            t, via = _num(e, "rt") * duration, "rt"
        if t is None and _str(e, "word"):
            target, nth = _nw(_str(e, "word")), int(_num(e, "nth") or 1)
            hits = [w for n, w in nwords if n and (n == target or (len(target) > 2 and target in n))]
            if len(hits) >= nth:
                t, via = hits[nth - 1]["start"], "word"
            else:
                warns.append(f"الكلمة «{_str(e, 'word')}» غير موجودة في التفريغ (فُرّغ الصوت؟) فتخطّيت هذا المؤثر.")
                continue
        if t is None and _num(e, "scene") is not None:
            i = int(_num(e, "scene"))
            if 1 <= i <= len(cuts):
                t, via = cuts[i - 1], "scene"
            else:
                warns.append(f"لا توجد قطعة مشهد رقم {i} (اكتُشفت {len(cuts)}).")
                continue
        if t is None:
            continue
        t += _num(e, "offset") or 0.0
        if snap > 0 and anchors and via != "word":
            near = min(anchors, key=lambda a: abs(a - t))
            if abs(near - t) <= snap and abs(near - t) > 0.001:
                t = near; snapped += 1
        item = {"t": max(0.0, t), "vol": _num(e, "vol") or _num(e, "volume") or 1.0}
        if fname:
            fn = os.path.basename(fname)
            rec = (host.MEDIA or {}).get(fn)
            if not rec or not (rec.get("owner") == owner or owner == "ADMIN"):
                warns.append(f"الملف «{fn}» غير موجود في مكتبتك.")
                continue
            p = f"{host.W}/public/{fn}"
            if not os.path.exists(p):
                warns.append(f"الملف «{fn}» غير متاح حالياً.")
                continue
            item["file"] = p; item["kind"] = "custom"
        elif prompt or fsq:
            if prompt: item["prompt"] = prompt[:200]
            if fsq: item["fs"] = fsq[:80]
            item["kind"] = kind or "whoosh"
            try: item["dur"] = _num(e, "dur")
            except Exception: pass
        else:
            item["kind"] = kind
        how[via] += 1
        plan.append(item)
    parts = [f"{n} عند {lbl}" for k, lbl in (("t", "ثانية محددة"), ("rt", "نسبة من الفيديو"), ("word", "كلمة منطوقة"), ("scene", "قطعة مشهد")) for n in [how[k]] if n]
    summ = f"{len(plan)} مؤثر ({'، '.join(parts)})" + (f" · انحاز {snapped} لأقرب كلمة/قطعة" if snapped else "")
    return plan, summ


def build_plan(host, d, raw_video, duration, segments, warns=None, owner=""):
    """returns (plan, source)"""
    code = d.get("code", "")
    words = d.get("words") or []
    if not words and segments:
        words = [{"text": x.get("text", ""), "start": x["start"], "end": x.get("end", x["start"])} for x in segments]
    plan, summ = smart_plan(host, code, duration, words, raw_video, owner, warns if warns is not None else [])
    if plan is not None:
        return plan, "الكود: " + summ
    if segments:
        plan = []
        for i, s in enumerate(segments):
            k = s.get("sfx") or host.pick_sfx(s.get("text", ""), i)
            if k:
                plan.append({"t": max(0, s["start"] - (0.3 if k in ("whoosh", "rise") else 0)), "kind": k, "vol": 1.0})
        if plan:
            return plan, "من كلام التفريغ"
    cuts = detect_cuts(host, raw_video, duration)
    if cuts:
        kinds = ["whoosh", "pop", "whoosh", "impact", "shine", "tick"]
        plan = [{"t": max(0, t - 0.1), "kind": kinds[i % len(kinds)] if i else "rise", "vol": 1.0} for i, t in enumerate(cuts)]
        return plan, f"من تغيّر المشاهد ({len(cuts)} قطعة)"
    # nothing detectable: a few gentle accents so the user still hears the feature
    step = max(2.0, duration / 6)
    return [{"t": x, "kind": "whoosh" if i % 2 == 0 else "pop", "vol": 0.8} for i, x in enumerate([step * k for k in range(1, 6)] if duration > 5 else [])], "نقاط موزّعة (لا تفريغ ولا قطعات)"


def volumedetect(path):
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else None


def mix(host, video, out, duration, voice, sfx_list, music_path):
    vinfo = host.probe(video)
    inputs = ["-i", video]
    f, speech, idx = [], [], 1
    if vinfo["has_audio"]:
        f.append("[0:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[b]"); speech.append("[b]")
    if voice and os.path.exists(voice):
        inputs += ["-i", voice]
        f.append(f"[{idx}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,apad[v0]"); speech.append("[v0]"); idx += 1
    sfx_labels = []
    for i, (path, t, v) in enumerate(sfx_list):
        if not os.path.exists(path):
            continue
        ms = max(0, int(t * 1000)); inputs += ["-i", path]
        f.append(f"[{idx}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,volume={v:.3f},adelay={ms}|{ms},apad[s{i}]"); sfx_labels.append(f"[s{i}]"); idx += 1
    final_labels = []
    if speech:
        if len(speech) == 1:
            f.append(f"{speech[0]}anull[sp]")
        else:
            f.append(f"{''.join(speech)}amix=inputs={len(speech)}:duration=longest:dropout_transition=0:normalize=0[sp]")
    if music_path:
        inputs += ["-i", music_path]
        fo = max(0.0, duration - 1.5)
        f.append(f"[{idx}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,volume={MUSIC_VOL},afade=t=in:d=1.2,afade=t=out:st={fo:.2f}:d=1.4,apad[mu]"); idx += 1
        if speech:
            f.append("[sp]asplit=2[sp1][sp2]")
            f.append("[mu][sp2]sidechaincompress=threshold=0.02:ratio=9:attack=15:release=450:makeup=1[md]")
            final_labels += ["[sp1]", "[md]"]
        else:
            final_labels.append("[mu]")
    elif speech:
        final_labels.append("[sp]")
    final_labels += sfx_labels
    if not final_labels:
        inputs += ["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        f.append(f"[{idx}:a]anull[a0]"); final_labels = ["[a0]"]
    n = len(final_labels)
    f.append(f"{''.join(final_labels)}amix=inputs={n}:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.93,atrim=0:{duration:.3f}[a]")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(f), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
                        "-t", f"{duration:.3f}", "-movflags", "+faststart", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg mix: " + r.stderr[-900:])


def finish(host, jid, d, J, raw, final, duration, voice, segments):
    """full audio stage. Returns (used_sfx, warnings, report)"""
    warns, used = [], []
    plat = getattr(host, "PLATFORM", None)
    key = ((plat.setting("freesound_key") if plat else "") or (d.get("sfx") or {}).get("key") or "").strip()
    sc, mc = dict(d.get("sfx") or {}), dict(d.get("music") or {})
    code = d.get("code", "") or ""
    mspec = parse_music(code)
    auto = []
    allow = d.get("_allow") if isinstance(d.get("_allow"), dict) else {"sfx": True, "music": True}
    if not sc.get("enabled") and allow.get("sfx") and _scan(code, "SFX", "[", "]") is not None:
        sc["enabled"] = True; auto.append("المؤثرات")
    if not mc.get("enabled") and allow.get("music") and mspec is not None:
        mc["enabled"] = True; auto.append("الموسيقى")
    sfx, rep = [], {"sfx": None, "music": None, "auto_enabled": auto}
    if sc.get("enabled"):
        J.update(stage="تجهيز المؤثرات الصوتية", progress=92)
        plan, src = build_plan(host, d, raw, duration, segments, warns, J.get("owner", ""))
        fs_n = loc_n = 0
        reasons = set()
        fs_fail = []
        for i, it in enumerate(plan[:80]):
            if it["t"] >= duration:
                continue
            if it.get("file"):  # the subscriber's own audio file
                sfx.append((it["file"], it["t"], SFX_VOL * it.get("vol", 1.0)))
                used.append({"kind": "custom", "t": it["t"], "source": "ملفك"})
                continue
            path = source = None
            # described sound (sfx:"...") or fs:"query" -> Freesound search by words; a plain kind -> the studio's per-kind query; no key / no hit -> local synth
            q = it.get("fs") or (_kw(it.get("prompt"), 4) if it.get("prompt") else "")
            if key:
                try:
                    if q:
                        path, source = fs_sfx(host, key, q, i)
                except Exception as e:
                    if str(e)[:90] not in fs_fail: fs_fail.append(str(e)[:90])
                if not path:
                    try:
                        p0, s0 = host.get_sfx(it["kind"], key, i % 4)
                        if s0.startswith("Freesound"):
                            path, source = p0, s0
                        elif s0[:90] not in fs_fail:
                            fs_fail.append(s0[:90])
                    except Exception as e:
                        if str(e)[:90] not in fs_fail: fs_fail.append(str(e)[:90])
            if not path:
                path, source = host.get_sfx(it["kind"], "", i % 4)
            if source.startswith("Freesound"):
                fs_n += 1
            else:
                loc_n += 1
                m = re.search(r"\((.*)\)", source)
                if key and m: reasons.add(m.group(1)[:90])
            sfx.append((path, it["t"], SFX_VOL * it.get("vol", 1.0)))
            used.append({"kind": it["kind"], "t": it["t"], "source": source})
        rep["sfx"] = {"plan": src, "count": len(sfx), "freesound": fs_n, "local": loc_n}
        if src.startswith("الكود"): rep["sync"] = src[6:]
        if not sfx:
            warns.append("المؤثرات مفعّلة لكن لم تُوجد مواضع مناسبة لها.")
        if key and fs_fail and loc_n:
            warns.append(f"تعذّر جلب {loc_n} مؤثر من Freesound فاستُخدم المحلي: " + "؛ ".join(fs_fail[:3]))
        if not key and sfx and loc_n:
            warns.append("لا يوجد مفتاح Freesound: أضف المفتاح من «مفاتيحي الخاصة» لمؤثرات حقيقية. استُخدمت مؤثرات مولّدة محلياً.")
    music = None
    if mc.get("enabled"):
        J.update(stage="تجهيز الموسيقى الخلفية", progress=94)
        try:
            music, msrc = get_music(host, (mspec or {}).get("style") or mc.get("style") or "chill", key, duration, jid, warns, mspec)
            rep["music"] = {"source": msrc, "style": (mspec or {}).get("style") or mc.get("style") or "chill", "prompt": (mspec or {}).get("prompt") or ""}
        except Exception as e:
            warns.append(f"فشل توليد الموسيقى: {e}")
    J.update(stage="مزج الصوت", progress=96)
    try:
        mix(host, raw, final, duration, voice, sfx, music)
    finally:
        if music and os.path.exists(music):
            try: os.remove(music)
            except OSError: pass
    info = host.probe(final)
    if not info["has_audio"]:
        warns.append("الفيديو النهائي بلا مسار صوتي!")
    else:
        mv = volumedetect(final)
        rep["mean_db"] = mv
        if mv is None or mv < -55:
            hints = []
            if not (voice or sfx or music):
                hints.append("لا يوجد صوت ملف ولا مؤثرات ولا موسيقى مفعّلة")
            warns.append("الصوت صامت تقريباً" + (": " + "، ".join(hints) if hints else " — تحقق أن الملف المرفوع يحتوي صوتاً وأن «دمج صوت الملف» مفعّل."))
    warns = [re.sub(r"(token|key|api_key)=[^&\s)']+", r"\1=***", w) for w in warns]
    return used, warns, rep
