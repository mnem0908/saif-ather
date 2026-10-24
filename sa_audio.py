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


def fs_music(host, style, key, dur, out):
    """Freesound background track (CC0 first). Returns (path, source) or raises"""
    import requests
    st = STYLES.get(style) or STYLES["chill"]
    base = "https://freesound.org/apiv2/search/text/"
    last = None
    for lic in ('license:"Creative Commons 0" ', ""):
        r = requests.get(base, timeout=20, params={"query": st["query"], "filter": lic + "duration:[25 TO 240]", "sort": "rating_desc", "fields": "id,name,previews,username,license,duration", "page_size": 10, "token": key},
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


def get_music(host, style, key, dur, jid, warns):
    out = f"{host.W}/out/{jid}_music.m4a"
    if style not in STYLES:
        style = "chill"
    if key:
        try:
            return fs_music(host, style, key, dur, out)
        except Exception as e:
            warns.append(f"موسيقى Freesound فشلت ({e}) — استُخدمت موسيقى مولّدة محلياً.")
    return synth_music(host, style, dur, out), f"مولّدة ({STYLES[style]['label']})"


def detect_cuts(host, video, duration, maxn=40):
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", video, "-vf", "select='gt(scene,0.28)',showinfo", "-an", "-f", "null", "-"], capture_output=True, text=True)
    ts, last = [], -9
    for t in re.findall(r"pts_time:([\d.]+)", r.stderr):
        t = float(t)
        if t - last >= 0.9 and 0.2 < t < duration - 0.3:
            ts.append(t); last = t
    return ts[:maxn]


def build_plan(host, d, raw_video, duration, segments):
    """returns (plan, source)"""
    code = d.get("code", "")
    plan = host.code_sfx(code, duration)
    if plan:
        return plan, "من SFX في الكود"
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
    sc, mc = d.get("sfx") or {}, d.get("music") or {}
    sfx, rep = [], {"sfx": None, "music": None}
    if sc.get("enabled"):
        J.update(stage="تجهيز المؤثرات الصوتية", progress=92)
        plan, src = build_plan(host, d, raw, duration, segments)
        fs_n = loc_n = 0
        reasons = set()
        for i, it in enumerate(plan[:80]):
            if it["t"] >= duration:
                continue
            path, source = host.get_sfx(it["kind"], key, i % 4)
            if source.startswith("Freesound"):
                fs_n += 1
            else:
                loc_n += 1
                m = re.search(r"\((.*)\)", source)
                if key and m: reasons.add(m.group(1)[:90])
            sfx.append((path, it["t"], SFX_VOL * it.get("vol", 1.0)))
            used.append({"kind": it["kind"], "t": it["t"], "source": source})
        rep["sfx"] = {"plan": src, "count": len(sfx), "freesound": fs_n, "local": loc_n}
        if not sfx:
            warns.append("المؤثرات مفعّلة لكن لم تُوجد مواضع مناسبة لها.")
        if key and loc_n and not fs_n:
            warns.append("تعذّر جلب أي مؤثر من Freesound فاستُخدمت مؤثرات محلية: " + "؛ ".join(sorted(reasons)))
        elif not key and sfx:
            warns.append("لم يُضبط مفتاح Freesound في لوحة الأدمن، استُخدمت مؤثرات مولّدة محلياً.")
    music = None
    if mc.get("enabled"):
        J.update(stage="تجهيز الموسيقى الخلفية", progress=94)
        try:
            music, msrc = get_music(host, mc.get("style") or "chill", key, duration, jid, warns)
            rep["music"] = {"source": msrc, "style": mc.get("style") or "chill"}
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
    return used, warns, rep
