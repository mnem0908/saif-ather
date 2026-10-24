# -*- coding: utf-8 -*-
"""SA Motion Studio — durable encrypted storage.

Everything that must survive restarts / hand-overs (users, subscriptions, media, transcripts, settings, audit)
is kept in ONE logical database that is
  * encrypted with AES-256-GCM (key derived from the secret SA_MASTER; nothing readable ever leaves the server),
  * mirrored to two independent places: a GitHub branch (`vault`) + release assets, and a Telegram channel (optional),
  * merged record-by-record (last writer wins per record), so two overlapping studio instances can never lose data.
Large files (uploaded media) are encrypted in 15 MB chunks and stored on Telegram and/or GitHub release assets;
the local disk is only a cache that can be wiped at any time.
"""
import os, io, json, time, hmac, hashlib, base64, threading, secrets, re, tempfile, traceback
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"SAV1"
CHUNK = 15 * 1024 * 1024
TOMB_TTL = 30 * 86400


def now_ms():
    return int(time.time() * 1000)


class Crypt:
    def __init__(self, master: str):
        if not master or len(master) < 12:
            raise ValueError("SA_MASTER must be at least 12 characters")
        k = hashlib.scrypt(master.encode(), salt=b"sa-motion-studio/vault/v1", n=2 ** 15, r=8, p=1, dklen=32, maxmem=128 * 1024 * 1024)
        self._enc = hmac.new(k, b"vault-enc", hashlib.sha256).digest()
        self.sign_key = hmac.new(k, b"session-sign", hashlib.sha256).digest()
        self.aes = AESGCM(self._enc)

    def seal(self, data: bytes, aad: bytes = b"") -> bytes:
        n = os.urandom(12)
        return MAGIC + n + self.aes.encrypt(n, data, aad)

    def open(self, blob: bytes, aad: bytes = b"") -> bytes:
        if not blob or blob[:4] != MAGIC:
            raise ValueError("not a vault blob")
        return self.aes.decrypt(blob[4:16], blob[16:], aad)


class Http:
    """tiny retrying wrapper"""

    @staticmethod
    def call(method, url, tries=3, timeout=60, **kw):
        last = None
        for i in range(tries):
            try:
                r = requests.request(method, url, timeout=timeout, **kw)
                if r.status_code in (429, 500, 502, 503, 504) and i < tries - 1:
                    time.sleep(min(10, 1.5 * (i + 1)) + (float(r.headers.get("retry-after", 0) or 0) if r.status_code == 429 else 0))
                    continue
                return r
            except requests.RequestException as e:
                last = type(e).__name__   # never include the URL (Telegram bot tokens live in it)
                time.sleep(1.2 * (i + 1))
        raise RuntimeError(f"network: {last}")


class GitHubBackend:
    name = "gh"

    def __init__(self, token, repo, api="https://api.github.com", uploads="https://uploads.github.com", branch="vault", tag="vault"):
        self.token, self.repo, self.api, self.uploads, self.branch, self.tag = token, repo, api.rstrip("/"), uploads.rstrip("/"), branch, tag
        self._rid = None
        self._lock = threading.Lock()
        self._branch_ok = False
        self.etags = {}

    def h(self, accept="application/vnd.github+json"):
        return {"Authorization": f"Bearer {self.token}", "Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "sa-motion-vault"}

    def req(self, method, path, **kw):
        return Http.call(method, self.api + path, headers=self.h(), **kw)

    def ensure_branch(self):
        if self._branch_ok:
            return
        r = self.req("GET", f"/repos/{self.repo}/git/ref/heads/{self.branch}")
        if r.status_code == 200:
            self._branch_ok = True
            return
        info = self.req("GET", f"/repos/{self.repo}")
        if info.status_code != 200:
            raise RuntimeError(f"repo access HTTP {info.status_code}")
        base = info.json().get("default_branch", "main")
        ref = self.req("GET", f"/repos/{self.repo}/git/ref/heads/{base}")
        if ref.status_code != 200:
            raise RuntimeError(f"base ref HTTP {ref.status_code}")
        sha = ref.json()["object"]["sha"]
        c = self.req("POST", f"/repos/{self.repo}/git/refs", json={"ref": f"refs/heads/{self.branch}", "sha": sha})
        if c.status_code not in (201, 422):
            raise RuntimeError(f"create branch HTTP {c.status_code} {c.text[:120]}")
        self._branch_ok = True

    # ---- small files (database shards) on the vault branch
    def get_file(self, path, conditional=False):
        """conditional=True: answers (None, '304') when unchanged — 304 replies do not count against the API rate limit"""
        self.ensure_branch()
        hdr = self.h()
        if conditional and self.etags.get(path):
            hdr["If-None-Match"] = self.etags[path]
        r = Http.call("GET", f"{self.api}/repos/{self.repo}/contents/{path}", params={"ref": self.branch}, headers=hdr)
        if r.status_code == 304:
            return None, "304"
        if r.status_code == 404:
            return None, None
        if r.status_code != 200:
            raise RuntimeError(f"get {path} HTTP {r.status_code}")
        if r.headers.get("etag"):
            self.etags[path] = r.headers["etag"]
        j = r.json()
        sha = j["sha"]
        if j.get("content"):
            return base64.b64decode(j["content"]), sha
        b = self.req("GET", f"/repos/{self.repo}/git/blobs/{sha}")
        if b.status_code != 200:
            raise RuntimeError(f"blob HTTP {b.status_code}")
        return base64.b64decode(b.json()["content"]), sha

    def put_file(self, path, data, sha=None, msg="vault"):
        self.ensure_branch()
        body = {"message": msg, "content": base64.b64encode(data).decode(), "branch": self.branch}
        if sha:
            body["sha"] = sha
        r = self.req("PUT", f"/repos/{self.repo}/contents/{path}", json=body)
        if r.status_code in (409, 422):
            raise ConflictError(path)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"put {path} HTTP {r.status_code} {r.text[:150]}")
        return r.json()["content"]["sha"]

    # ---- big blobs as release assets
    def release_id(self):
        with self._lock:
            if self._rid:
                return self._rid
            r = self.req("GET", f"/repos/{self.repo}/releases/tags/{self.tag}")
            if r.status_code == 200:
                self._rid = r.json()["id"]
                return self._rid
            c = self.req("POST", f"/repos/{self.repo}/releases", json={"tag_name": self.tag, "name": "SA vault (encrypted)", "body": "Encrypted storage. Do not delete.", "prerelease": True, "draft": False})
            if c.status_code not in (200, 201):
                raise RuntimeError(f"release HTTP {c.status_code} {c.text[:120]}")
            self._rid = c.json()["id"]
            return self._rid

    def put_blob(self, name, data):
        rid = self.release_id()
        r = Http.call("POST", f"{self.uploads}/repos/{self.repo}/releases/{rid}/assets", params={"name": name}, timeout=300,
                      headers={**self.h(), "Content-Type": "application/octet-stream"}, data=data)
        if r.status_code == 422:  # name already exists -> replace
            self.del_blob({"name": name})
            r = Http.call("POST", f"{self.uploads}/repos/{self.repo}/releases/{rid}/assets", params={"name": name}, timeout=300,
                          headers={**self.h(), "Content-Type": "application/octet-stream"}, data=data)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"asset upload HTTP {r.status_code} {r.text[:120]}")
        return {"id": r.json()["id"], "name": name}

    def get_blob(self, loc):
        r = Http.call("GET", f"{self.api}/repos/{self.repo}/releases/assets/{loc['id']}", timeout=300,
                      headers=self.h("application/octet-stream"))
        if r.status_code != 200:
            raise RuntimeError(f"asset HTTP {r.status_code}")
        return r.content

    def del_blob(self, loc):
        aid = loc.get("id")
        if not aid and loc.get("name"):
            rid = self.release_id()
            r = self.req("GET", f"/repos/{self.repo}/releases/{rid}/assets", params={"per_page": 100})
            for a in (r.json() if r.status_code == 200 else []):
                if a.get("name") == loc["name"]:
                    aid = a["id"]
        if aid:
            self.req("DELETE", f"/repos/{self.repo}/releases/assets/{aid}")

    def check(self):
        self.ensure_branch()
        self.release_id()
        return True


class ConflictError(Exception):
    pass


class TelegramBackend:
    name = "tg"

    def __init__(self, token, chat, api="https://api.telegram.org"):
        self.token, self.chat, self.api = token, str(chat), api.rstrip("/")

    def url(self, m):
        return f"{self.api}/bot{self.token}/{m}"

    def call(self, m, **kw):
        r = Http.call("POST", self.url(m), **kw)
        try:
            j = r.json()
        except Exception:
            raise RuntimeError(f"telegram {m} HTTP {r.status_code}")
        if not j.get("ok"):
            raise RuntimeError(f"telegram {m}: {j.get('description', r.status_code)}")
        return j["result"]

    def put_blob(self, name, data, caption=""):
        res = self.call("sendDocument", timeout=300, data={"chat_id": self.chat, "caption": caption[:200], "disable_notification": "true"},
                        files={"document": (name, data, "application/octet-stream")})
        d = res.get("document") or {}
        return {"fid": d.get("file_id"), "mid": res.get("message_id")}

    def get_blob(self, loc):
        f = self.call("getFile", data={"file_id": loc["fid"]})
        r = Http.call("GET", f"{self.api}/file/bot{self.token}/{f['file_path']}", timeout=300)
        if r.status_code != 200:
            raise RuntimeError(f"telegram file HTTP {r.status_code}")
        return r.content

    def del_blob(self, loc):
        if loc.get("mid"):
            try:
                self.call("deleteMessage", data={"chat_id": self.chat, "message_id": loc["mid"]})
            except Exception:
                pass

    def pin(self, mid):
        self.call("pinChatMessage", data={"chat_id": self.chat, "message_id": mid, "disable_notification": "true"})

    def pinned_file(self):
        c = self.call("getChat", data={"chat_id": self.chat})
        p = c.get("pinned_message") or {}
        d = p.get("document") or {}
        return d.get("file_id")

    def check(self):
        self.call("getChat", data={"chat_id": self.chat})
        return True


def merge_coll(a: dict, b: dict) -> dict:
    """record-wise last-writer-wins"""
    out = dict(a)
    for k, rb in b.items():
        ra = out.get(k)
        if ra is None or (rb.get("_v", 0) > ra.get("_v", 0)):
            out[k] = rb
    return out


class DB:
    """Collections of id -> record. Persisted encrypted: local cache + GitHub + Telegram bundle."""

    def __init__(self, vault, local_dir):
        self.vault, self.dir = vault, local_dir
        os.makedirs(local_dir, exist_ok=True)
        self.c = {}            # coll -> {id: rec}
        self.dirty = set()
        self.dver = {}
        self.lk = threading.RLock()
        self.shas = {}
        self.last_sync = 0
        self.last_tg = 0
        self.loaded_from = []

    # ---------- access
    def get(self, coll, rid, default=None):
        with self.lk:
            r = self.c.get(coll, {}).get(rid)
            return default if (r is None or r.get("_x")) else r

    def all(self, coll):
        with self.lk:
            return {k: v for k, v in self.c.get(coll, {}).items() if not v.get("_x")}

    def put(self, coll, rid, rec):
        with self.lk:
            cur = self.c.setdefault(coll, {}).get(rid)
            rec = dict(rec)
            rec["_v"] = max(now_ms(), (cur or {}).get("_v", 0) + 1)
            rec.pop("_x", None)
            self.c[coll][rid] = rec
            self.dirty.add(coll)
            self.dver[coll] = self.dver.get(coll, 0) + 1
            return rec

    def update(self, coll, rid, **kw):
        with self.lk:
            r = dict(self.get(coll, rid) or {})
            r.update(kw)
            return self.put(coll, rid, r)

    def delete(self, coll, rid):
        with self.lk:
            cur = self.c.setdefault(coll, {}).get(rid)
            self.c[coll][rid] = {"_x": 1, "_v": max(now_ms(), (cur or {}).get("_v", 0) + 1)}
            self.dirty.add(coll)
            self.dver[coll] = self.dver.get(coll, 0) + 1

    # ---------- (de)serialisation
    def _seal_coll(self, coll):
        raw = json.dumps(self.c.get(coll, {}), ensure_ascii=False, separators=(",", ":")).encode()
        return self.vault.crypt.seal(raw, aad=("coll:" + coll).encode())

    def _open_coll(self, coll, blob):
        return json.loads(self.vault.crypt.open(blob, aad=("coll:" + coll).encode()))

    def _local_path(self, coll):
        return os.path.join(self.dir, f"{coll}.enc")

    def gc(self):
        cut = (time.time() - TOMB_TTL) * 1000
        for coll, recs in self.c.items():
            for k in [k for k, v in recs.items() if v.get("_x") and v.get("_v", 0) < cut]:
                recs.pop(k, None)
        a = self.c.get("audit", {})
        if len(a) > 3000:
            for k in sorted(a)[: len(a) - 2500]:
                a.pop(k, None)

    # ---------- load
    def load(self, colls):
        """merge: local cache + GitHub shards + Telegram bundle"""
        with self.lk:
            for coll in colls:
                got = {}
                p = self._local_path(coll)
                if os.path.exists(p):
                    try:
                        got = merge_coll(got, self._open_coll(coll, open(p, "rb").read()))
                        self.loaded_from.append(f"local:{coll}")
                    except Exception as e:
                        print("vault: local shard unreadable", coll, e, flush=True)
                gh = self.vault.gh
                if gh:
                    try:
                        blob, sha = gh.get_file(f"vault/{coll}.enc")
                        if blob:
                            got = merge_coll(got, self._open_coll(coll, blob))
                            self.shas[coll] = sha
                            self.loaded_from.append(f"gh:{coll}")
                    except Exception as e:
                        print("vault: github load failed", coll, e, flush=True)
                self.c[coll] = merge_coll(self.c.get(coll, {}), got)
            if not self.loaded_from and self.vault.tg:
                self.restore_from_tg()
            self.gc()

    def restore_from_tg(self):
        try:
            fid = self.vault.tg.pinned_file()
            if not fid:
                return False
            blob = self.vault.tg.get_blob({"fid": fid})
            bundle = json.loads(self.vault.crypt.open(blob, aad=b"bundle"))
            for coll, recs in bundle.items():
                self.c[coll] = merge_coll(self.c.get(coll, {}), recs)
                self.dirty.add(coll)
            self.loaded_from.append("tg:bundle")
            print("vault: restored database from the Telegram channel", flush=True)
            return True
        except Exception as e:
            print("vault: telegram restore failed:", e, flush=True)
            return False

    # ---------- save / sync
    def flush(self, force=False, tg=False):
        """write dirty shards locally + to GitHub (merging on conflicts); bundle to Telegram at most every 10 min"""
        errs = []
        with self.lk:
            todo = list(self.c) if force else list(self.dirty)
            ver = {c: self.dver.get(c, 0) for c in todo}
            seals = {}
            for coll in todo:
                try:
                    seals[coll] = self._seal_coll(coll)
                    tmp = self._local_path(coll) + ".tmp"
                    open(tmp, "wb").write(seals[coll])
                    os.replace(tmp, self._local_path(coll))
                except Exception as e:
                    errs.append(f"local {coll}: {e}")
        gh = self.vault.gh
        for coll in todo:
            if not gh:
                with self.lk:
                    if self.dver.get(coll, 0) == ver[coll]:
                        self.dirty.discard(coll)
                continue
            ok = False
            blob = seals.get(coll)
            for attempt in range(4):
                try:
                    if blob is None:
                        with self.lk:
                            blob = self._seal_coll(coll)
                    self.shas[coll] = gh.put_file(f"vault/{coll}.enc", blob, sha=self.shas.get(coll), msg=f"vault {coll}")
                    ok = True
                    break
                except ConflictError:
                    try:  # someone else wrote: merge and retry
                        rb, sha = gh.get_file(f"vault/{coll}.enc")
                        with self.lk:
                            if rb:
                                self.c[coll] = merge_coll(self.c.get(coll, {}), self._open_coll(coll, rb))
                            self.shas[coll] = sha
                            blob = self._seal_coll(coll)
                    except Exception as e:
                        errs.append(f"gh merge {coll}: {e}")
                        break
                except Exception as e:
                    errs.append(f"gh {coll}: {e}")
                    break
            if ok:
                with self.lk:
                    if self.dver.get(coll, 0) == ver[coll]:
                        self.dirty.discard(coll)
                self.vault.mark("gh", True)
            else:
                self.vault.mark("gh", False, errs[-1] if errs else "conflict")
        if self.vault.tg and (tg or not self.last_tg or (self.dirty or todo) and time.time() - self.last_tg > 600):
            try:
                self.push_tg()
            except Exception as e:
                errs.append(f"tg: {e}")
                self.vault.mark("tg", False, str(e))
        return errs

    def push_tg(self):
        with self.lk:
            raw = json.dumps(self.c, ensure_ascii=False, separators=(",", ":")).encode()
        blob = self.vault.crypt.seal(raw, aad=b"bundle")
        if len(blob) > 19 * 1024 * 1024:
            raise RuntimeError("database bundle too large for Telegram (>19MB)")
        tg = self.vault.tg
        loc = tg.put_blob(f"sa-db-{time.strftime('%Y%m%d-%H%M')}.enc", blob, caption="SA encrypted DB snapshot")
        try:
            tg.pin(loc["mid"])
        except Exception as e:
            print("vault: pin failed (give the bot 'Pin messages' right):", e, flush=True)
        old = self.vault.state.get("tg_last_mid")
        if old and old != loc["mid"]:
            tg.del_blob({"mid": old})
        self.vault.state["tg_last_mid"] = loc["mid"]
        self.last_tg = time.time()
        self.vault.mark("tg", True)

    def pull(self):
        """merge remote changes into memory (called periodically)"""
        gh = self.vault.gh
        if not gh:
            return 0
        changed = 0
        for coll in list(self.c):
            try:
                if coll in self.dirty:
                    continue
                blob, sha = gh.get_file(f"vault/{coll}.enc", conditional=True)
                if sha == "304":
                    self.vault.mark("gh", True)
                    continue
                if blob and sha != self.shas.get(coll):
                    remote = self._open_coll(coll, blob)
                    with self.lk:
                        before = self.c.get(coll, {})
                        merged = merge_coll(before, remote)
                        if merged != before:
                            self.c[coll] = merged
                            changed += 1
                        self.shas[coll] = sha
                self.vault.mark("gh", True)
            except Exception as e:
                self.vault.mark("gh", False, str(e))
                break
        return changed


class Vault:
    def __init__(self, master, local_dir, gh=None, tg=None):
        self.crypt = Crypt(master)
        self.gh, self.tg = gh, tg
        self.dir = local_dir
        os.makedirs(local_dir, exist_ok=True)
        self.blobdir = os.path.join(local_dir, "blobs")
        os.makedirs(self.blobdir, exist_ok=True)
        self.health = {"gh": {"enabled": bool(gh), "ok": None, "last_ok": 0, "err": ""}, "tg": {"enabled": bool(tg), "ok": None, "last_ok": 0, "err": ""}}
        self.state = {}
        self.db = DB(self, os.path.join(local_dir, "db"))
        self._stop = False
        self._thr = None

    def mark(self, which, ok, err=""):
        h = self.health[which]
        h["ok"] = ok
        if ok:
            h["last_ok"] = time.time()
            h["err"] = ""
        else:
            h["err"] = str(err)[:200]

    # ---------- blobs
    def put_blob(self, bid, path):
        """encrypt a local file in chunks and store it on every configured backend. returns locator dict"""
        h = hashlib.sha256()
        locs = {"n": 0, "size": 0, "tg": [], "gh": []}
        errs = []
        with open(path, "rb") as f:
            i = 0
            while True:
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                h.update(chunk)
                sealed = self.crypt.seal(chunk, aad=f"{bid}:{i}".encode())
                nm = f"{bid}.{i:04d}.bin"
                stored = 0
                if self.tg:
                    try:
                        locs["tg"].append(self.tg.put_blob(nm, sealed, caption=f"blob {bid}#{i}"))
                        self.mark("tg", True)
                        stored += 1
                    except Exception as e:
                        locs["tg"].append(None)
                        errs.append(f"tg: {e}")
                        self.mark("tg", False, e)
                if self.gh:
                    try:
                        locs["gh"].append(self.gh.put_blob(nm, sealed))
                        self.mark("gh", True)
                        stored += 1
                    except Exception as e:
                        locs["gh"].append(None)
                        errs.append(f"gh: {e}")
                        self.mark("gh", False, e)
                if not stored:
                    raise RuntimeError("could not store chunk anywhere: " + "; ".join(errs[-2:]))
                locs["size"] += len(chunk)
                i += 1
        locs["n"] = i
        locs["sha"] = h.hexdigest()
        if not self.tg:
            locs.pop("tg")
        if not self.gh:
            locs.pop("gh")
        # keep a local encrypted copy too (fast restore on this instance); it is only a cache
        return locs

    def get_blob(self, bid, locs, dest):
        h = hashlib.sha256()
        tmp = dest + ".part"
        try:
            with open(tmp, "wb") as out:
                for i in range(locs["n"]):
                    data, last = None, None
                    for be, key in ((self.tg, "tg"), (self.gh, "gh")):
                        arr = locs.get(key) or []
                        if be and i < len(arr) and arr[i]:
                            try:
                                data = self.crypt.open(be.get_blob(arr[i]), aad=f"{bid}:{i}".encode())
                                break
                            except Exception as e:
                                last = e
                    if data is None:
                        raise RuntimeError(f"chunk {i} unavailable: {last}")
                    h.update(data)
                    out.write(data)
            if locs.get("sha") and h.hexdigest() != locs["sha"]:
                raise RuntimeError("checksum mismatch")
            os.replace(tmp, dest)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def del_blob(self, locs):
        for key, be in (("tg", self.tg), ("gh", self.gh)):
            for l in (locs.get(key) or []):
                if be and l:
                    try:
                        be.del_blob(l)
                    except Exception:
                        pass

    # ---------- lifecycle
    def start(self, colls, interval=45):
        self.db.load(colls)
        for c in colls:
            self.db.c.setdefault(c, {})
        self.db.flush(force=True, tg=True)
        self._thr = threading.Thread(target=self._loop, args=(interval,), daemon=True)
        self._thr.start()

    def _loop(self, interval):
        n = 0
        while not self._stop:
            time.sleep(interval)
            n += 1
            try:
                self.db.pull()
                self.db.flush()
                if n % 40 == 0:
                    with self.db.lk:
                        self.db.gc()
                        self.db.dirty.update(self.db.c.keys())
            except Exception:
                traceback.print_exc()

    def status(self):
        d = {k: dict(v) for k, v in self.health.items()}
        d["loaded_from"] = list(self.db.loaded_from)
        d["pending"] = sorted(self.db.dirty)
        d["records"] = {k: len([1 for v in r.values() if not v.get("_x")]) for k, r in self.db.c.items()}
        sz = 0
        for c in self.db.c:
            p = self.db._local_path(c)
            if os.path.exists(p):
                sz += os.path.getsize(p)
        d["db_bytes"] = sz
        return d

    def self_test(self):
        """write+read a probe on every backend; returns report"""
        rep = {}
        probe = os.urandom(64)
        sealed = self.crypt.seal(probe, aad=b"probe")
        if self.gh:
            try:
                loc = self.gh.put_blob("probe.bin", sealed)
                ok = self.crypt.open(self.gh.get_blob(loc), aad=b"probe") == probe
                self.gh.del_blob(loc)
                rep["gh"] = "ok" if ok else "mismatch"
            except Exception as e:
                rep["gh"] = "fail: " + str(e)[:150]
        if self.tg:
            try:
                loc = self.tg.put_blob("probe.bin", sealed, caption="probe")
                ok = self.crypt.open(self.tg.get_blob(loc), aad=b"probe") == probe
                self.tg.del_blob(loc)
                rep["tg"] = "ok" if ok else "mismatch"
            except Exception as e:
                rep["tg"] = "fail: " + str(e)[:150]
        return rep


def from_env(local_dir, env=os.environ):
    master = env.get("SA_MASTER", "").strip()
    if not master:
        raise RuntimeError("SA_MASTER secret is missing")
    gh = None
    if env.get("GH_TOKEN") and env.get("GH_REPO"):
        gh = GitHubBackend(env["GH_TOKEN"], env["GH_REPO"], env.get("GH_API_URL", "https://api.github.com"), env.get("GH_UPLOADS_URL", "https://uploads.github.com"))
    tg = None
    if env.get("TG_BOT_TOKEN") and env.get("TG_STORAGE_CHAT"):
        tg = TelegramBackend(env["TG_BOT_TOKEN"], env["TG_STORAGE_CHAT"], env.get("TG_API_URL", "https://api.telegram.org"))
    return Vault(master, local_dir, gh=gh, tg=tg)
