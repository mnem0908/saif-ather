# -*- coding: utf-8 -*-
"""Cloud rendering on GitHub Actions: upload -> dispatch -> follow -> collect chunks -> merge locally.
Designed for the 1000 req/hour GITHUB_TOKEN limit: ETag-conditional polling (304 answers are free),
explicit rate-limit handling (never a silent freeze) and stall detection."""
import os, re, json, time, shutil, zipfile, mimetypes, subprocess
from concurrent.futures import ThreadPoolExecutor
import requests

TARGET_CHUNK_SECONDS = 4.0


class SlotPool:
    """Global fair scheduler for GitHub runner slots. GitHub's free plan runs ~20 jobs at once; if several renders each
    dispatch a dozen machines, the later ones sit 'queued' on GitHub for ages. Here they wait in the studio instead
    (with a visible queue position) and are dispatched only when machines are really free, sized to what is free."""
    def __init__(self):
        import threading
        self.cv = threading.Condition(); self.used = 0; self.q = []

    def acquire(self, cap, want, audio, J):
        tok = object(); extra = 1 if audio else 0
        with self.cv:
            self.q.append(tok)
            try:
                while True:
                    if J.get("cancelled"): raise RuntimeError("تم الإلغاء")
                    free = cap - self.used
                    mine = max(1, min(want, max(2, int(cap * 0.65)) - extra))
                    need = 1 + extra if want <= 1 else 2 + extra
                    if self.q[0] is tok and free >= need:
                        g = max(1 if want <= 1 else 2, min(mine, free - extra))
                        self.used += g + extra
                        return g
                    pos = self.q.index(tok) + 1
                    J.update(stage="في الطابور — بانتظار أجهزة فارغة", progress=3, details=f"دورك {pos} · المشغول {self.used}/{cap}")
                    self.cv.wait(2)
            finally:
                self.q.remove(tok); self.cv.notify_all()

    def release(self, n):
        with self.cv:
            self.used = max(0, self.used - n); self.cv.notify_all()


POOL = SlotPool()


class RateLimited(Exception):
    def __init__(self, wait):
        super().__init__(f"GitHub rate limit, wait {wait}s")
        self.wait = wait


class GH:
    def __init__(self, host):
        self.h = host
        self.cache = {}
        self.remaining = None
        self.calls = 0

    def headers(self, extra=None):
        h = {"Authorization": f"Bearer {self.h.GH_TOKEN}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        h.update(extra or {})
        return h

    def _note(self, r):
        self.calls += 1
        rem = r.headers.get("x-ratelimit-remaining")
        if rem is not None:
            try: self.remaining = int(rem)
            except ValueError: pass

    def _limited(self, r):
        if r.status_code in (403, 429):
            if r.headers.get("x-ratelimit-remaining") == "0" or "rate limit" in r.text[:300].lower() or r.headers.get("retry-after"):
                reset = int(r.headers.get("x-ratelimit-reset", "0") or 0)
                ra = int(r.headers.get("retry-after", "0") or 0)
                return max(ra, reset - int(time.time()), 5) + 2
        return 0

    def req(self, method, path, tries=3, **kw):
        kw.setdefault("timeout", 45)
        hdr = kw.pop("headers", None)
        last = None
        for i in range(tries):
            try:
                r = requests.request(method, self.h.GH_API + path, headers=self.headers(hdr), **kw)
            except requests.RequestException as e:
                last = e; time.sleep(1.5 * (i + 1)); continue
            self._note(r)
            w = self._limited(r)
            if w: raise RateLimited(w)
            if r.status_code >= 500 and i < tries - 1:
                time.sleep(1.5 * (i + 1)); continue
            return r
        raise RuntimeError(f"تعذر الاتصال بـ السحابة: {last}")

    def get(self, path, params=None):
        """conditional GET: unchanged resources answer 304 and cost nothing against the rate limit"""
        key = (path, tuple(sorted((params or {}).items())))
        et, data = self.cache.get(key, (None, None))
        r = self.req("GET", path, params=params, headers={"If-None-Match": et} if et else None)
        if r.status_code == 304 and data is not None: return 200, data
        if r.status_code == 200:
            j = r.json()
            if r.headers.get("etag"): self.cache[key] = (r.headers["etag"], j)
            return 200, j
        return r.status_code, None


def enabled(host):
    return bool(host.GH_TOKEN and host.GH_REPO and "/" in host.GH_REPO)


def release_id(gh):
    h = gh.h
    st, j = gh.get(f"/repos/{h.GH_REPO}/releases/tags/media")
    if st == 200: return j["id"]
    r = gh.req("POST", f"/repos/{h.GH_REPO}/releases", json={"tag_name": "media", "name": "media", "body": "Temporary media for cloud renders", "prerelease": True})
    if r.status_code == 422:
        st, j = gh.get(f"/repos/{h.GH_REPO}/releases/tags/media")
        if st == 200: return j["id"]
    if r.status_code >= 300: raise RuntimeError(f"تعذر تجهيز مخزن الملفات على السحابة ({r.status_code}): {r.text[:200]}")
    return r.json()["id"]


_SWEPT = [0.0]


def sweep(gh, rid, max_age=2 * 3600):
    """Release assets are world-readable on a public repo: never leave user media there if a render died half-way."""
    if time.time() - _SWEPT[0] < 1800: return
    _SWEPT[0] = time.time()
    try:
        st, items = gh.get(f"/repos/{gh.h.GH_REPO}/releases/{rid}/assets", {"per_page": 100})
        if st != 200 or not isinstance(items, list): return
        for a in items:
            try: age = time.time() - time.mktime(time.strptime(a["created_at"], "%Y-%m-%dT%H:%M:%SZ")) + time.timezone
            except Exception: continue
            if age > max_age and re.match(r"^[0-9a-f]{12}_", a.get("name", "")):
                gh.req("DELETE", f"/repos/{gh.h.GH_REPO}/releases/assets/{a['id']}", tries=1, timeout=30)
    except Exception:
        pass


def upload(gh, rid, path, name):
    h = gh.h
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    last = None
    for i in range(3):
        try:
            with open(path, "rb") as f:
                r = requests.post(f"{h.GH_UPLOADS}/repos/{h.GH_REPO}/releases/{rid}/assets", params={"name": name}, data=f, timeout=1800, headers=gh.headers({"Content-Type": ctype}))
            if r.status_code < 300:
                j = r.json(); return j["id"], j["browser_download_url"]
            last = f"{r.status_code}: {r.text[:150]}"
            w = gh._limited(r)
            if w: raise RateLimited(w)
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"فشل رفع {name} إلى السحابة ({last})")


_BASE_REMOTION = {"@remotion/cli", "@remotion/bundler", "@remotion/renderer", "@remotion/google-fonts", "@remotion/transitions"}


def packages(host, code):
    out = set()
    for m in re.findall(r"(?:from|import)\s*\(?\s*[\"']([^\"'./][^\"']*)[\"']", code):
        p = host.pkg_of(m)
        if p in ("react", "react-dom", "remotion") or p in _BASE_REMOTION: continue
        if not re.fullmatch(r"(@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*", p): continue
        if p in host.ALLOWED_PKGS or p.startswith("@remotion/"): out.add(p)
    return sorted(out)


def fail_text(gh, run, jobs):
    h = gh.h
    bad = [j for j in jobs if j.get("conclusion") == "failure"]
    parts = []
    for j in bad[:1]:
        steps = [s["name"] for s in j.get("steps", []) if s.get("conclusion") == "failure"]
        parts.append(f"المرحلة الفاشلة: {j['name']}" + (f" ← {', '.join(steps)}" if steps else ""))
        try:
            lg = gh.req("GET", f"/repos/{h.GH_REPO}/actions/jobs/{j['id']}/logs", timeout=60, tries=1)
            if lg.status_code == 200:
                lines = [re.sub(r"^\S+Z\s", "", ln) for ln in lg.text.splitlines() if ln.strip()]
                parts.append("\n".join(lines[-25:])[-2500:])
        except Exception:
            pass
    parts.append("")
    return "\n".join(parts)


def _download(gh, art, dest):
    last = None
    for i in range(3):
        try:
            with requests.get(art["archive_download_url"], headers=gh.headers(), stream=True, timeout=600) as z:
                if z.status_code == 200:
                    with open(dest, "wb") as f:
                        for blk in z.iter_content(1 << 20): f.write(blk)
                    return
                last = f"HTTP {z.status_code}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"فشل تنزيل {art['name']} ({last})")


def _unzip_one(zp, member_re, dest):
    with zipfile.ZipFile(zp) as zf:
        for n in zf.namelist():
            if re.fullmatch(member_re, os.path.basename(n)):
                with zf.open(n) as src, open(dest, "wb") as dst: shutil.copyfileobj(src, dst)
                return True
    return False


def render(host, jid, d, J, props, mfile, mtype, out):
    gh = GH(host); W = host.W; repo = host.GH_REPO
    cfg = d["config"]; fps = cfg["fps"]; frames = cfg["frames"]; duration = frames / fps
    comp = d.get("comp") or {}
    if not re.fullmatch(r"[A-Z]\w*", comp.get("name", "") or ""): raise RuntimeError("لم أجد اسم المكوّن لإرساله للسحابة")
    carries = bool(host.code_has_audio(d.get("code", "")))
    assets, tmp, art_ids = [], [], []
    held = 0
    try:
        J.update(stage="رفع الملفات إلى السحابة", progress=2, details="")
        rid = release_id(gh)
        sweep(gh, rid)
        media, medias = None, []
        fl = [f for f in (props.get("files") or []) if f.get("file")] or ([{"file": mfile, "type": mtype}] if mfile else [])
        for f in fl[:6]:
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f["file"])
            aid, murl = upload(gh, rid, f"{W}/public/{f['file']}", f"{jid}_{safe}")
            assets.append(aid); medias.append({"file": f["file"], "type": f.get("type"), "url": murl})
            if J.get("cancelled"): raise RuntimeError("تم الإلغاء")
        media = next((m for m in medias if m["file"] == mfile), None) or (medias[0] if medias else None)
        if J.get("cancelled"): raise RuntimeError("تم الإلغاء")
        job_doc = {"code": d.get("code", ""), "comp": {"name": comp["name"], "default": bool(comp.get("default"))},
                   "config": {"width": cfg["width"], "height": cfg["height"], "fps": fps, "frames": frames},
                   "props": props, "media": media, "medias": medias, "packages": packages(host, d.get("code", ""))}
        jpath = f"{W}/out/{jid}_job.json"; tmp.append(jpath)
        json.dump(job_doc, open(jpath, "w", encoding="utf-8"), ensure_ascii=False)
        aid, job_url = upload(gh, rid, jpath, f"{jid}_job.json"); assets.append(aid)

        try: per = max(2.0, float(host.PLATFORM.setting("sec_per_machine", 10)))
        except Exception: per = float(TARGET_CHUNK_SECONDS)
        # short videos stay on ONE machine (set-up cost of a second machine outweighs the gain); long ones are split
        want = 1 if duration <= per * 1.5 else max(2, min(host.CLOUD_CHUNKS, int(-(-duration // per))))
        try: cap = int(host.PLATFORM.setting("cloud_slots", 15))
        except Exception: cap = 15
        chunks = POOL.acquire(max(4, cap), want, carries, J)
        held = chunks + (1 if carries else 0)
        inputs = {"job_id": jid, "job_url": job_url, "frames": str(frames), "duration": f"{duration:.3f}", "fps": str(fps),
                  "width": str(cfg["width"]), "height": str(cfg["height"]), "crf": str(cfg["crf"]), "preset": str(cfg["preset"]), "chunks": str(chunks),
                  "audio": "true" if carries else "false", "merge": "false"}
        J.update(stage="إطلاق الرندر على أجهزة السحابة", progress=4, details=f"{chunks} أجهزة")
        r = gh.req("POST", f"/repos/{repo}/actions/workflows/{host.GH_WORKFLOW}/dispatches", json={"ref": host.GH_REF, "inputs": inputs})
        if r.status_code != 204:
            hint = " (تعذّر تشغيل الرندر السحابي — أبلغ الأدمن)" if r.status_code in (403, 404) else ""
            raise RuntimeError(f"رفض السحابة إطلاق المهمة ({r.status_code}): {r.text[:300]}{hint}")

        run = None
        for _ in range(45):
            if J.get("cancelled"): raise RuntimeError("تم الإلغاء")
            st, j = gh.get(f"/repos/{repo}/actions/workflows/{host.GH_WORKFLOW}/runs", {"event": "workflow_dispatch", "per_page": 20})
            if st == 200:
                run = next((x for x in j.get("workflow_runs", []) if jid in (x.get("display_title") or "")), None)
                if run: break
            time.sleep(2)
        if not run: raise RuntimeError("تعذّر بدء الرندر السريع، أعد المحاولة بعد قليل.")
        run_id = run["id"]; J["_run_url"] = run.get("html_url")

        t0 = time.time(); stall_since = None; jobs = []
        while True:
            if J.get("cancelled"):
                try: gh.req("POST", f"/repos/{repo}/actions/runs/{run_id}/cancel", tries=1)
                except Exception: pass
                raise RuntimeError("تم الإلغاء")
            el = int(time.time() - t0)
            if el > 3600:
                try: gh.req("POST", f"/repos/{repo}/actions/runs/{run_id}/cancel", tries=1)
                except Exception: pass
                raise RuntimeError("انتهت مهلة الرندر السحابي (ساعة): " + str(run.get("html_url", "")))
            try:
                st_r, rj_ = gh.get(f"/repos/{repo}/actions/runs/{run_id}")
                st_j, jj_ = gh.get(f"/repos/{repo}/actions/runs/{run_id}/jobs", {"per_page": 100})
                if st_j == 200: jobs = jj_.get("jobs", [])
                if st_r == 200: run = rj_
                if st_r != 200 and st_j != 200:
                    stall_since = stall_since or time.time()
                    J.update(stage="السحابة لا يرد مؤقتاً", details=f"HTTP {st_r}/{st_j} · أعيد المحاولة")
                    if time.time() - stall_since > 180: raise RuntimeError(f"السحابة لا يستجيب (HTTP {st_r}). راجع: {run.get('html_url', '')}")
                    time.sleep(8); continue
                stall_since = None
            except RateLimited as e:
                J.update(stage="حد طلبات السحابة — انتظار ثم أكمل", details=f"{e.wait}ث · الرندر مستمر على السحابة ولن يضيع")
                if e.wait > 1500: raise RuntimeError(f"استنفدت حد طلبات السحابة لساعة. الرندر ما زال يعمل هنا: {run.get('html_url', '')} — أعد المحاولة بعد {e.wait // 60} دقيقة.")
                time.sleep(min(e.wait, 60)); continue
            if run.get("status") == "completed":
                if run.get("conclusion") != "success":
                    raise RuntimeError("فشل الرندر السحابي (" + str(run.get("conclusion")) + ")\n" + fail_text(gh, run, jobs))
                break
            rj = [j for j in jobs if j["name"].startswith("render")]
            done = sum(1 for j in rj if j.get("status") == "completed" and j.get("conclusion") == "success")
            running = sum(1 for j in rj if j.get("status") == "in_progress")
            plan = next((j for j in jobs if j["name"] == "plan"), None)
            if rj:
                J.update(stage=f"رندر موزّع على {len(rj)} أجهزة", progress=10 + int(78 * (done + running * 0.4) / max(1, len(rj))), details=f"اكتمل {done}/{len(rj)} · {el}ث")
            elif plan and plan.get("status") == "completed":
                J.update(stage="تجهيز الأجهزة", progress=8, details=f"{el}ث")
            else:
                J.update(stage="بانتظار جهاز من السحابة", progress=5, details=f"{el}ث")
            time.sleep(5)

        J.update(stage="تنزيل الأجزاء ودمجها", progress=90, details="")
        st, aj = gh.get(f"/repos/{repo}/actions/runs/{run_id}/artifacts", {"per_page": 100})
        arts = aj.get("artifacts", []) if st == 200 else []
        art_ids = [a["id"] for a in arts]
        n_expected = len([j for j in jobs if j["name"].startswith("render")])
        ch = sorted([a for a in arts if re.fullmatch(rf"chunk-{jid}-\d+", a["name"])], key=lambda a: int(a["name"].rsplit("-", 1)[1]))
        whole = next((a for a in arts if a["name"] == f"video-{jid}"), None)
        if whole and not ch:  # workflow merged on its own
            zp = f"{W}/out/{jid}_dl.zip"; tmp.append(zp); _download(gh, whole, zp)
            if not _unzip_one(zp, r"video\.mp4", out): raise RuntimeError("ملف الفيديو غير موجود داخل الأرشيف.")
        else:
            if not ch or (n_expected and len(ch) < n_expected): raise RuntimeError(f"اكتمل الرندر لكن وُجدت {len(ch)} من {n_expected} أجزاء فقط.")
            files = []
            def fetch(a):
                zp = f"{W}/out/{jid}_{a['name']}.zip"; tmp.append(zp); _download(gh, a, zp)
                i = int(a["name"].rsplit("-", 1)[1]); dst = f"{W}/out/{jid}_c{i:03d}.mp4"; tmp.append(dst)
                if not _unzip_one(zp, r"chunk-\d+\.mp4", dst): raise RuntimeError(f"الجزء {i} فارغ")
                return dst
            with ThreadPoolExecutor(max_workers=6) as ex: files = list(ex.map(fetch, ch))
            lst = f"{W}/out/{jid}_list.txt"; tmp.append(lst)
            open(lst, "w").write("".join(f"file '{f}'\n" for f in files))
            cat = f"{W}/out/{jid}_cat.mp4"; tmp.append(cat)
            rr = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", cat], capture_output=True, text=True)
            if rr.returncode != 0: raise RuntimeError("فشل دمج الأجزاء: " + rr.stderr[-400:])
            aud = next((a for a in arts if a["name"] == f"audio-{jid}"), None)
            if aud:
                ap = f"{W}/out/{jid}_audio.zip"; tmp.append(ap); _download(gh, aud, ap)
                aac = f"{W}/out/{jid}_a.aac"; tmp.append(aac)
                if _unzip_one(ap, r"audio\.aac", aac):
                    rr = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", cat, "-i", aac, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out], capture_output=True, text=True)
                    if rr.returncode != 0: raise RuntimeError("فشل إضافة الصوت: " + rr.stderr[-400:])
                else: shutil.copy(cat, out)
            else:
                shutil.copy(cat, out)
        if not os.path.exists(out) or os.path.getsize(out) < 1000: raise RuntimeError("الفيديو المنزّل فارغ أو تالف.")
    finally:
        if held: POOL.release(held)
        for aid in art_ids:
            try: gh.req("DELETE", f"/repos/{repo}/actions/artifacts/{aid}", tries=1, timeout=30)
            except Exception: pass
        for aid in assets:
            try: gh.req("DELETE", f"/repos/{repo}/releases/assets/{aid}", tries=1, timeout=30)
            except Exception: pass
        for p in tmp:
            try: os.remove(p)
            except OSError: pass
