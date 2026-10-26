# -*- coding: utf-8 -*-
"""SA Motion Studio — subscription platform: users, sessions, plans/quotas, ownership, admin API, durable media.
Installed into the studio's Flask app by `install(host)` (host = the app module)."""
import os, re, sys, struct, json, time, hmac, hashlib, base64, secrets, threading, shutil, subprocess, traceback
from flask import has_request_context, request, jsonify, g, redirect, make_response, send_file, abort, Response

import sa_store
import sa_pages
import sa_cloud

COLLS = ["users", "media", "tr", "usage", "audit", "settings", "state", "sessions"]
ALPHA_ID = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ALPHA_PW = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
DAY = 86400

FEATURES = {
    "upload": "رفع الملفات", "code": "محرر الكود والقوالب", "render": "رندر الفيديو", "still": "لقطات ثابتة", "cloud": "رندر سحابي موزّع (سريع)",
    "transcribe": "تفريغ الصوت ومزامنة الكلمات", "cut": "قص الصمت", "sfx": "مؤثرات صوتية", "music": "موسيقى خلفية",
    "tts": "TTS عبر API (متقدم — بدون واجهة)", "hd": "جودة عالية (أكثر من 1080p)",
}
QUOTA_LABELS = {
    "renders_day": "عدد الرندرات يومياً", "max_duration": "أقصى مدة للفيديو (ثانية)", "storage_mb": "مساحة التخزين (MB)",
    "tts_chars_day": "حروف TTS يومياً", "concurrent": "عمليات رندر متزامنة", "max_devices": "عدد الأجهزة المتزامنة", "asr_min_day": "دقائق التفريغ يومياً", "stills_day": "اللقطات يومياً",
}
DEFAULT_PLANS = {
    "basic": {"label": "أساسي", "features": ["upload", "code", "render", "still", "sfx", "cloud"],
              "quotas": {"renders_day": 5, "max_duration": 60, "storage_mb": 300, "tts_chars_day": 0, "asr_min_day": 0, "stills_day": 40, "concurrent": 1, "max_devices": 1}},
    "pro": {"label": "احترافي", "features": ["upload", "code", "render", "still", "sfx", "music", "cloud", "transcribe", "cut", "tts"],
            "quotas": {"renders_day": 20, "max_duration": 180, "storage_mb": 1500, "tts_chars_day": 20000, "asr_min_day": 60, "stills_day": 200, "concurrent": 2, "max_devices": 1}},
    "vip": {"label": "VIP", "features": list(FEATURES), "quotas": {"renders_day": 80, "max_duration": 600, "storage_mb": 5000, "tts_chars_day": 100000, "asr_min_day": 300, "stills_day": 600, "concurrent": 3, "max_devices": 2}},
}
DEFAULT_SETTINGS = {"site_name": "SA Motion Studio", "public_url": "", "maintenance": False, "maintenance_msg": "الموقع تحت الصيانة، عُد بعد قليل.",
                    "max_cloud": 12, "cloud_slots": 15, "sec_per_machine": 10, "default_plan": "pro", "welcome": "", "share_kicks": 6}
USER_PLAIN = {"minimax_group": r"[A-Za-z0-9_\-]{4,40}", "minimax_base": r"https://[A-Za-z0-9\.\-]{3,80}(:\d{2,5})?", "minimax_model": r"[A-Za-z0-9_\.\-:/]{1,60}",
              "openai_base": r"https://[A-Za-z0-9\.\-]{3,80}(:\d{2,5})?(/[A-Za-z0-9_\.\-/]{0,60})?", "openai_model": r"[A-Za-z0-9_\.\-:/]{1,60}"}
USER_KEYS = ("freesound_key", "groq_key", "elevenlabs_key", "minimax_key", "openai_key") + tuple(USER_PLAIN)
USER_KEY_UI = ("elevenlabs_key", "freesound_key", "groq_key")
SECRET_KEYS = ["freesound_key", "elevenlabs_key", "minimax_key", "openai_key", "groq_key"]
PLAIN_KEYS = ["minimax_group", "minimax_base", "openai_base", "openai_model", "tts_default", "minimax_model", "elevenlabs_model"]

P = None  # singleton

_orig_thread_init = threading.Thread.__init__


def _thread_init(self, *a, **k):
    _orig_thread_init(self, *a, **k)
    try:
        self._sa_uid = P.cur_uid() if P else ""
    except Exception:
        self._sa_uid = ""


threading.Thread.__init__ = _thread_init


def hash_pw(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "s1$%s$%s" % (base64.b64encode(salt).decode(), base64.b64encode(h).decode())


def check_pw(pw: str, stored: str) -> bool:
    try:
        _, s, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


DUMMY = hash_pw("dummy-password-for-timing")


def gen_id():
    return "SA-" + "".join(secrets.choice(ALPHA_ID) for _ in range(6))


def gen_pw():
    r = "".join(secrets.choice(ALPHA_PW) for _ in range(12))
    return "-".join([r[:4], r[4:8], r[8:]])


def norm_id(s):
    return re.sub(r"\s+", "", (s or "")).upper()


def norm_pw(s):
    return re.sub(r"[\s-]+", "", s or "") if re.fullmatch(r"[A-Za-z0-9\-\s]{12,16}", s or "") and "-" in (s or "") else (s or "").strip()


def today():
    return time.strftime("%Y%m%d", time.gmtime())


def b64u(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def unb64u(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class Platform:
    def __init__(self, host, vault):
        self.h, self.v, self.db = host, vault, vault.db
        self.started = time.time()
        self.fails = {}
        self.hits = {}
        self.fl = threading.Lock()
        self.sync_lock = threading.Lock()
        self._media_sig = {}
        self.sign_key = vault.crypt.sign_key

    # ------------------------------------------------------------------ settings
    def settings(self):
        s = dict(DEFAULT_SETTINGS)
        s.update(self.db.get("settings", "main", {}) or {})
        return s

    def setting(self, k, default=""):
        if k in USER_KEYS:  # a subscriber's own key (if any) wins over the site key — for that subscriber only
            uk = self.user_key(k)
            if uk:
                return uk
        return self.settings().get(k, default)

    def cur_uid(self):
        try:
            if has_request_context():
                u = getattr(g, "user", None)
                return u["id"] if u else ""
        except Exception:
            pass
        return getattr(threading.current_thread(), "_sa_uid", "") or ""

    def user_key(self, k):
        uid = self.cur_uid()
        if not uid:
            return ""
        return ((self.db.get("state", "keys:" + uid) or {}).get(k) or "").strip()

    def plans(self):
        p = self.db.get("settings", "plans")
        if p and p.get("plans"):
            return p["plans"]
        return DEFAULT_PLANS

    # ------------------------------------------------------------------ users
    def user_rec(self, uid):
        return self.db.get("users", uid)

    def status_of(self, u):
        if u.get("status") == "suspended":
            return "suspended"
        if u.get("role") == "admin":
            return "active"
        if not u.get("expires"):
            return "pending"
        return "expired" if time.time() > u["expires"] else "active"

    def features(self, u):
        if u.get("role") == "admin":
            return list(FEATURES)
        if u.get("features") is not None:
            return list(u["features"])
        return list((self.plans().get(u.get("plan")) or {}).get("features", []))

    def quotas(self, u):
        base = dict((self.plans().get(u.get("plan")) or {}).get("quotas", {}))
        base.update(u.get("quotas") or {})
        if u.get("role") == "admin":
            base = {k: 10 ** 9 for k in QUOTA_LABELS}
            base["max_devices"] = 5
        return base

    def usage(self, uid, day=None):
        return self.db.get("usage", f"{uid}:{day or today()}", {}) or {}

    def bump(self, uid, **kw):
        k = f"{uid}:{today()}"
        with self.db.lk:
            r = dict(self.db.get("usage", k, {}) or {})
            for a, b in kw.items():
                r[a] = r.get(a, 0) + b
            self.db.put("usage", k, r)
            u = self.user_rec(uid)
            if u:
                t = dict(u.get("totals") or {})
                for a, b in kw.items():
                    t[a] = t.get(a, 0) + b
                self.db.put("users", uid, {**u, "totals": t})

    def storage_used(self, uid):
        return sum(int(m.get("size", 0)) for m in self.h.MEDIA.values() if m.get("owner") == uid)

    def audit(self, ev, uid="", actor="", detail="", ip=""):
        k = "%013d-%s" % (int(time.time() * 1000), secrets.token_hex(2))
        self.db.put("audit", k, {"t": time.time(), "uid": uid, "actor": actor, "ev": ev, "detail": str(detail)[:300], "ip": ip})

    def create_user(self, name, days, plan, features=None, quotas=None, start="now", note="", actor="admin", role="user"):
        while True:
            uid = gen_id()
            if not self.db.get("users", uid) and uid not in self.db.c.get("users", {}):
                break
        pw = gen_pw()
        days = max(0, min(3650, int(days)))
        exp = (time.time() + days * DAY) if start == "now" else 0
        rec = {"id": uid, "name": (name or "")[:60], "role": role, "pw": hash_pw(pw), "created": time.time(), "expires": exp, "days": days,
               "start": start, "status": "active", "plan": plan if plan in self.plans() else self.setting("default_plan", "pro"),
               "features": features, "quotas": quotas or {}, "sv": 1, "note": (note or "")[:300], "last_login": 0, "logins": 0,
               "devices": [], "created_by": actor, "totals": {}}
        self.db.put("users", uid, rec)
        self.audit("create_user", uid, actor, f"{days}d plan={rec['plan']}")
        return rec, pw

    def ensure_admin(self):
        pw = os.environ.get("ADMIN_PASS", "").strip()
        if not pw:
            return False
        cur = self.db.get("users", "ADMIN")
        if not cur or not check_pw(pw, cur.get("pw", "")):
            rec = {"id": "ADMIN", "name": "المدير", "email": (os.environ.get("ADMIN_EMAIL", "").strip().lower() or (cur or {}).get("email", "")), "role": "admin", "pw": hash_pw(pw), "created": (cur or {}).get("created", time.time()), "expires": 0,
                   "status": "active", "plan": "vip", "features": None, "quotas": {}, "sv": ((cur or {}).get("sv", 0) + 1), "devices": (cur or {}).get("devices", []),
                   "logins": (cur or {}).get("logins", 0), "last_login": (cur or {}).get("last_login", 0), "totals": (cur or {}).get("totals", {})}
            self.db.put("users", "ADMIN", rec)
            self.audit("admin_password_synced", "ADMIN", "system", "from ADMIN_PASS secret")
        em = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        cur = self.db.get("users", "ADMIN")
        if em and cur and cur.get("email") != em:
            self.db.put("users", "ADMIN", {**cur, "email": em})
        return True

    # ------------------------------------------------------------------ sessions
    # sessions: every login creates a server-side session; the signed cookie only points to it.
    def make_cookie(self, u, sid, days=14):
        body = "%s|%d|%d|%s" % (u["id"], u.get("sv", 1), int(time.time() + days * DAY), sid)
        p = b64u(body.encode())
        return p + "." + b64u(hmac.new(self.sign_key, p.encode(), hashlib.sha256).digest())

    def read_session(self, c):
        """-> (user, sid, reason). reason in (None, 'invalid', 'kicked', 'revoked')"""
        try:
            p, sig = c.split(".")
            if not hmac.compare_digest(b64u(hmac.new(self.sign_key, p.encode(), hashlib.sha256).digest()), sig):
                return None, None, "invalid"
            uid, sv, exp, sid = unb64u(p).decode().split("|")
            if time.time() > int(exp):
                return None, None, "invalid"
            u = self.user_rec(uid)
            if not u or int(sv) != u.get("sv", 1):
                return None, None, "revoked"
            s = self.db.get("sessions", sid)
            if not s or s.get("uid") != uid:
                return None, None, "revoked"
            if s.get("revoked"):
                return None, None, ("kicked" if s.get("why") == "kicked" else "revoked")
            if time.time() > s.get("exp", 0):
                return None, None, "invalid"
            return u, sid, None
        except Exception:
            return None, None, "invalid"

    def read_cookie(self, c):
        return self.read_session(c)[0]

    def touch(self, sid):
        s = self.db.get("sessions", sid)
        if s and time.time() - s.get("last", 0) > 600:
            self.db.put("sessions", sid, {**s, "last": time.time(), "ip": self.ip()})

    def sessions_of(self, uid):
        now = time.time()
        rows = [(k, v) for k, v in self.db.all("sessions").items() if v.get("uid") == uid and not v.get("revoked") and v.get("exp", 0) > now]
        return sorted(rows, key=lambda kv: kv[1].get("last", 0))

    def revoke_session(self, sid, why="revoked"):
        s = self.db.get("sessions", sid)
        if s and not s.get("revoked"):
            self.db.put("sessions", sid, {**s, "revoked": time.time(), "why": why})

    def open_session(self, u, days, old_sid=None):
        """create a session, enforcing the per-subscriber device limit (oldest session is kicked)."""
        uid = u["id"]
        if old_sid:
            s = self.db.get("sessions", old_sid)
            if s and s.get("uid") == uid:
                self.revoke_session(old_sid, "relogin")
        limit = max(1, int(self.quotas(u).get("max_devices", 1) or 1))
        act = self.sessions_of(uid)
        kicked = 0
        while len(act) >= limit:
            sid0, _ = act.pop(0)
            self.revoke_session(sid0, "kicked"); kicked += 1
        sid = secrets.token_urlsafe(12)
        now = time.time()
        ua = (request.headers.get("User-Agent") or "")[:120]
        self.db.put("sessions", sid, {"uid": uid, "created": now, "last": now, "exp": now + days * DAY, "ip": self.ip(), "ua": ua})
        if kicked and u.get("role") != "admin":
            cur = self.user_rec(uid) or u
            ks = [t for t in (cur.get("kicks") or []) if now - t < 2 * DAY] + [now] * kicked
            upd = {**cur, "kicks": ks[-60:]}
            lim = int(self.setting("share_kicks", 6) or 0)
            k24 = len([t for t in ks if now - t < DAY])
            if lim and k24 >= lim and cur.get("status") != "suspended":
                upd.update(status="suspended", sv=cur.get("sv", 1) + 1, flag="sharing",
                           note=((cur.get("note") or "") + " | إيقاف تلقائي: اشتباه مشاركة الحساب").strip(" |")[:300])
                self.audit("auto_suspend", uid, "system", f"{k24} kicks/24h", self.ip())
            else:
                self.audit("session_kick", uid, "system", f"{kicked} old session(s) ended", self.ip())
            self.db.put("users", uid, upd)
        return sid

    def sweep_sessions(self):
        now = time.time()
        if now - getattr(self, "_sw", 0) < 3600:
            return
        self._sw = now
        for k, v in list(self.db.all("sessions").items()):
            if v.get("exp", 0) < now - DAY or (v.get("revoked") and now - v["revoked"] > 2 * DAY):
                self.db.delete("sessions", k)

    # ---- TOTP (RFC 6238, stdlib only) for the administrator
    @staticmethod
    def totp_code(secret, counter):
        key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
        h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
        o = h[-1] & 15
        return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)

    def totp_verify(self, secret, code, last=0):
        code = re.sub(r"\D", "", code or "")
        if len(code) != 6:
            return 0
        c0 = int(time.time() // 30)
        for c in (c0, c0 - 1, c0 + 1):
            if c > last and hmac.compare_digest(self.totp_code(secret, c), code):
                return c
        return 0

    def ip(self):
        return (request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "?")[:45]

    def rate(self, key, limit, window):
        """sliding-window counter; True when the caller is over the limit (counts this call)."""
        now = time.time()
        with self.fl:
            arr = [t for t in self.hits.get(key, []) if now - t < window]
            arr.append(now)
            self.hits[key] = arr
            if len(self.hits) > 20000:
                for k in list(self.hits)[:5000]:
                    self.hits.pop(k, None)
            return len(arr) > limit

    def throttled(self, key, limit, window):
        now = time.time()
        with self.fl:
            arr = [t for t in self.fails.get(key, []) if now - t < window]
            self.fails[key] = arr
            return (int(window - (now - arr[0])) + 1) if len(arr) >= limit else 0

    def fail(self, key):
        with self.fl:
            self.fails.setdefault(key, []).append(time.time())

    # ------------------------------------------------------------------ current user helpers
    def me(self):
        return getattr(g, "user", None)

    def uid(self):
        u = self.me()
        return u["id"] if u else ""

    def is_admin(self):
        u = self.me()
        return bool(u and u.get("role") == "admin")

    def can(self, feat):
        u = self.me()
        return bool(u and feat in self.features(u))

    def job_ok(self, jid):
        j = self.h.JOBS.get(jid)
        return (not j) or self.is_admin() or j.get("owner") == self.uid()

    def public_job(self, j):
        out = {k: v for k, v in j.items() if not k.startswith("_")}
        if isinstance(out.get("result"), dict):
            out["result"] = {k: v for k, v in out["result"].items() if k != "locs"}
        return out

    def public_user(self, u):
        st = self.status_of(u)
        us = self.usage(u["id"])
        q = self.quotas(u)
        return {"id": u["id"], "name": u.get("name", ""), "role": u.get("role"), "plan": u.get("plan"), "plan_label": (self.plans().get(u.get("plan")) or {}).get("label", u.get("plan")),
                "status": st, "expires": u.get("expires", 0), "days_left": (None if u.get("role") == "admin" else (max(0, int((u["expires"] - time.time()) / DAY + 0.999)) if u.get("expires") else u.get("days"))),
                "features": self.features(u), "quotas": q, "usage": us, "storage_used_mb": round(self.storage_used(u["id"]) / 1e6, 1)}

    # ------------------------------------------------------------------ guards used by the studio code
    def narration_guard(self, d, lines):
        """code-driven narration (export const NARRATION): feature + daily characters; remembers the plan's max length in d"""
        u = self.me()
        if not u:
            return "يجب تسجيل الدخول", 401
        feats, q = self.features(u), self.quotas(u)
        d["_maxsec"] = 900 if u.get("role") == "admin" else int(q.get("max_duration", 60))
        if u.get("role") == "admin":
            return None
        if "tts" not in feats:
            return "الصوت الناطق من الكود (NARRATION) غير مفعّل في اشتراكك.", 403
        chars = sum(len(x["text"]) for x in lines)
        left = q.get("tts_chars_day", 0) - self.usage(u["id"]).get("tts_chars", 0)
        if chars > max(left, 0):
            return f"حصة الصوت اليومية المتبقية {max(left, 0)} حرف والنص في الكود {chars} حرفاً.", 429
        return None

    def guard_render(self, d, w, h, fps, frames, mode):
        u = self.me()
        if not u:
            return "يجب تسجيل الدخول", 401
        feats, q = self.features(u), self.quotas(u)
        need = "still" if mode == "still" else "render"
        if need not in feats:
            return "هذه الميزة غير مفعّلة في اشتراكك.", 403
        if max(w, h) > 1920 and "hd" not in feats:
            return "الدقة العالية (أكثر من 1080p) غير مفعّلة في اشتراكك.", 403
        if mode != "still" and frames / fps > q.get("max_duration", 60) + 0.01:
            return f"أقصى مدة مسموحة في اشتراكك {q.get('max_duration')} ثانية.", 403
        us = self.usage(u["id"])
        if mode == "still":
            if us.get("stills", 0) >= q.get("stills_day", 40):
                return "استنفدت حصة اللقطات اليومية.", 429
        elif us.get("renders", 0) >= q.get("renders_day", 5):
            return f"استنفدت حصة الرندر اليومية ({q.get('renders_day')}). تتجدد منتصف الليل (UTC).", 429
        s = d.get("sfx") or {}
        s["enabled"] = bool(s.get("enabled")) and "sfx" in feats
        d["sfx"] = s
        mu = d.get("music") or {}
        mu["enabled"] = bool(mu.get("enabled")) and "music" in feats
        d["music"] = mu
        d["_allow"] = {"sfx": "sfx" in feats, "music": "music" in feats}   # server-side only: code-driven SFX/MUSIC may auto-enable just within the plan
        if "cloud" not in feats:
            d["cloud"] = False
        d["owner"] = u["id"]
        return None

    def busy_reason(self, d):
        """concurrency policy: cloud renders run in parallel (1 per user), local renders are serialized"""
        h = self.h
        now = time.time()
        active = [j for j in list(h.JOBS.values()) if j.get("status") == "processing" and j.get("kind") == "render" and now - j.get("created", now) < 4 * 3600]
        cloud = h.cloud_enabled() and d.get("cloud", True) is not False and d.get("mode") != "still"
        if cloud:
            mine = [j for j in active if j.get("owner") == self.uid() and j.get("cloud")]
            lim = int(self.quotas(self.me()).get("concurrent", 1) or 1)
            if len(mine) >= lim:
                return f"لديك {len(mine)} عمليات رندر قيد التنفيذ (المسموح {lim} في وقت واحد). انتظر حتى تنتهي إحداها."
            if len([j for j in active if j.get("cloud")]) >= int(self.setting("max_cloud", 12)):
                return "الخادم مشغول حالياً بعدة عمليات رندر، حاول بعد دقائق."
            if any(not j.get("cloud") for j in active):
                return "يوجد رندر محلي قيد التنفيذ، انتظر قليلاً."
            return None
        return "يوجد رندر قيد التنفيذ، انتظر حتى ينتهي" if active else None

    def render_started(self, jid, mode):
        self.bump(self.uid(), **({"stills": 1} if mode == "still" else {"renders": 1}))
        self.audit("render" if mode != "still" else "still", self.uid(), "", jid, self.ip())

    def upload_guard(self, size_bytes):
        u = self.me()
        q = self.quotas(u)
        if (self.storage_used(u["id"]) + size_bytes) / 1e6 > q.get("storage_mb", 300):
            return f"تجاوزت مساحة التخزين المسموحة ({q.get('storage_mb')}MB). احذف ملفات من المكتبة."
        return None

    def can_asr(self, name):
        u = self.me()
        rec = self.h.MEDIA.get(name) or {}
        mins = float(rec.get("duration", 0)) / 60
        us = self.usage(u["id"])
        if us.get("asr_min", 0) + mins > self.quotas(u).get("asr_min_day", 0) + 0.001:
            return "استنفدت حصة دقائق التفريغ اليومية."
        self.bump(u["id"], asr_min=round(mins, 2))
        return None

    # ------------------------------------------------------------------ media (durable)
    def owns(self, name):
        rec = self.h.MEDIA.get(name)
        return bool(rec) and (rec.get("owner") == self.uid() or self.is_admin())

    def media_access(self, name):
        """returns None if OK (file present locally, restored from the vault if needed) or an error text"""
        name = os.path.basename(name or "")
        rec = self.h.MEDIA.get(name)
        if not rec or not self.owns(name):
            return "الملف غير موجود في مكتبتك. ارفعه مرة أخرى."
        if self.ensure_local(name):
            return None
        return "MEDIA_MISSING: تعذّرت استعادة الملف من التخزين الآمن" + (f" ({rec.get('backup_err')})" if rec.get("backup_err") else "") + ". ارفعه مرة أخرى."

    def ensure_local(self, name):
        h, W = self.h, self.h.W
        path = f"{W}/public/{name}"
        rec = h.MEDIA.get(name) or {}
        if os.path.exists(path) and os.path.getsize(path) > 0:
            rec["used"] = time.time()
            return True
        locs = rec.get("locs")
        if not locs:
            return False
        with self.sync_lock:
            if os.path.exists(path):
                return True
            try:
                self.v.get_blob(name, locs, path)
                base = name.rsplit(".", 1)[0]
                if rec.get("has_audio"):
                    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", f"{W}/uploads/{base}_asr.wav"], capture_output=True)
                rec["used"] = time.time()
                print(f"vault: restored {name} ({locs.get('size', 0) // 1024}KB)", flush=True)
                return True
            except Exception as e:
                rec["backup_err"] = str(e)[:120]
                print("vault: restore failed", name, e, flush=True)
                return False

    def media_created(self, rec, owner):
        """called by finalize_media for every new media file (upload, cut, TTS)"""
        h = self.h
        rec["owner"] = owner or "ADMIN"
        try:
            rec["size"] = os.path.getsize(f"{h.W}/public/{rec['file']}")
        except OSError:
            rec["size"] = 0
        u = self.user_rec(rec["owner"])
        if u and (self.storage_used(rec["owner"]) + rec["size"]) / 1e6 > self.quotas(u).get("storage_mb", 300) + 0.5:
            try: os.remove(f"{h.W}/public/{rec['file']}")
            except OSError: pass
            raise RuntimeError("تجاوزت مساحة التخزين المسموحة. احذف ملفات من المكتبة أولاً.")
        rec["backed"] = False
        threading.Thread(target=self._backup, args=(rec["file"], rec), daemon=True).start()

    def _backup(self, name, rec=None):
        h = self.h
        time.sleep(0.6)
        rec = h.MEDIA.get(name) or rec
        if not rec or not os.path.exists(f"{h.W}/public/{name}"):
            return
        for attempt in range(3):
            try:
                locs = self.v.put_blob(name, f"{h.W}/public/{name}")
                rec["locs"], rec["backed"] = locs, True
                rec.pop("backup_err", None)
                break
            except Exception as e:
                rec["backup_err"] = str(e)[:150]
                time.sleep(4 * (attempt + 1))
        h.save_meta(h.MEDIA)

    def sync_media(self, media):
        """host.save_meta hook: mirror MEDIA -> DB (media + tr collections)"""
        for name, rec in list(media.items()):
            slim = {k: v for k, v in rec.items() if k not in ("words", "segments", "used")}
            sig = hashlib.md5(json.dumps(slim, sort_keys=True, default=str).encode()).hexdigest()
            if self._media_sig.get(name) != sig:
                self.db.put("media", name, slim)
                self._media_sig[name] = sig
            if rec.get("words") or rec.get("segments"):
                tsig = hashlib.md5(json.dumps([rec.get("words"), rec.get("segments")], default=str).encode()).hexdigest()
                if self._media_sig.get("tr:" + name) != tsig:
                    self.db.put("tr", name, {"words": rec.get("words") or [], "segments": rec.get("segments") or []})
                    self._media_sig["tr:" + name] = tsig

    def load_media(self):
        """DB -> host.MEDIA (called at startup and after pulls)"""
        h = self.h
        n = 0
        for name, rec in self.db.all("media").items():
            cur = h.MEDIA.get(name)
            r = {k: v for k, v in rec.items() if not k.startswith("_")}
            if cur:
                r = {**r, "used": cur.get("used", 0)}
            tr = self.db.get("tr", name)
            if tr:
                r["words"], r["segments"] = tr.get("words", []), tr.get("segments", [])
            h.MEDIA[name] = r
            self._media_sig[name] = hashlib.md5(json.dumps({k: v for k, v in r.items() if k not in ("words", "segments", "used")}, sort_keys=True, default=str).encode()).hexdigest()
            n += 1
        for name in [k for k in h.MEDIA if k not in self.db.c.get("media", {}) or (self.db.c["media"][k].get("_x"))]:
            if h.MEDIA[name].get("locs") or h.MEDIA[name].get("owner"):
                if name in self.db.c.get("media", {}):  # deleted elsewhere
                    h.MEDIA.pop(name, None)
        return n

    def delete_media(self, name, purge=True):
        h = self.h
        rec = h.MEDIA.pop(name, None)
        base = name.rsplit(".", 1)[0]
        for f in (f"{h.W}/public/{name}", f"{h.W}/uploads/{base}_asr.wav"):
            try:
                os.remove(f)
            except Exception:
                pass
        self.db.delete("media", name)
        self.db.delete("tr", name)
        self._media_sig.pop(name, None)
        if rec and rec.get("locs") and purge:
            threading.Thread(target=self.v.del_blob, args=(rec["locs"],), daemon=True).start()
        try:
            h.save_meta(h.MEDIA)
        except Exception:
            pass


# ====================================================================== installation
def install(host):
    global P
    vault = sa_store.from_env(os.path.join(host.W, "vault"))
    P = Platform(host, vault)
    host.PLATFORM = P
    app = host.app
    try:
        vault.start(COLLS, interval=int(os.environ.get("SA_SYNC_SECONDS", "45")))
    except Exception:
        traceback.print_exc()
    P.admin_ready = P.ensure_admin()
    # stored plans (first boot)
    if not vault.db.get("settings", "plans"):
        vault.db.put("settings", "plans", {"plans": DEFAULT_PLANS})
    if not vault.db.get("settings", "main"):
        s = dict(DEFAULT_SETTINGS)
        repo = os.environ.get("GH_REPO", "")
        if "/" in repo:
            o, r = repo.split("/", 1)
            s["public_url"] = f"https://{o.lower()}.github.io/{r}/"
        vault.db.put("settings", "main", s)
    vault.db.flush(force=True)
    P.load_media()
    host.save_meta_orig = host.save_meta

    def save_meta_hook(m):
        host.save_meta_orig(m)
        try:
            P.sync_media(m)
        except Exception:
            traceback.print_exc()
    host.save_meta = save_meta_hook
    threading.Thread(target=_pull_loop, daemon=True).start()
    register(app)
    import sa_tts
    sa_tts.register(app, P)
    print(f"🔐 المنصة جاهزة: مستخدمون={len(vault.db.all('users'))} · وسائط={len(host.MEDIA)} · تخزين={'GitHub' if vault.gh else ''}{'+Telegram' if vault.tg else ''}", flush=True)
    return P


def _pull_loop():
    while True:
        time.sleep(60)
        try:
            if P.db.pull():
                P.load_media()
        except Exception:
            traceback.print_exc()


FEATURE_OF = {"/api/transcribe": "transcribe", "/api/segments": "transcribe", "/api/cut_silence": "cut", "/api/upload": "upload", "/api/tts": "tts", "/api/tts/voices": "tts"}
HEAVY = {"/api/render", "/api/tts", "/api/transcribe", "/api/cut_silence"}
OPEN_PATHS = {"/api/health", "/icon.svg", "/login", "/api/login", "/favicon.ico"}


def jerr(msg, code=400):
    return jsonify({"error": msg}), code


def register(app):
    host = P.h

    @app.before_request
    def _gate():
        path = request.path
        if path in OPEN_PATHS:
            return None
        if not P.admin_ready:
            return Response("ADMIN_PASS غير مضبوط. أضفه كسر في GitHub ثم أعد التشغيل.", 503, {"Content-Type": "text/plain; charset=utf-8"})
        ip = P.ip()
        if P.rate(f"ipall:{ip}", 1500, 60):
            return jerr("طلبات كثيرة جداً. تمهّل قليلاً.", 429)
        u, sid, why = P.read_session(request.cookies.get("sa_s", ""))
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            org = request.headers.get("Origin")
            if org and re.sub(r"^https?://", "", org) != request.host:
                return jerr("origin", 403)
            if request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
                return jerr("origin", 403)
        if not u:
            msg = "تم تسجيل الدخول بهذا الحساب من جهاز آخر، لذلك أُنهيت جلستك هنا." if why == "kicked" else "auth"
            if path.startswith("/api/"):
                return jerr(msg, 401)
            return redirect("/login" + ("?e=kicked" if why == "kicked" else ""))
        st = P.status_of(u)
        if st != "active":
            if path.startswith("/api/"):
                return jerr({"suspended": "الحساب موقوف.", "expired": "انتهى اشتراكك. تواصل مع المدير للتجديد.", "pending": "الحساب غير مفعّل."}[st], 403) if path != "/api/me" else None
            if path != "/logout" and path != "/api/logout":
                resp = redirect("/login?e=" + st)
                resp.delete_cookie("sa_s")
                return resp
        g.user = u
        g.sid = sid
        P.touch(sid)
        if P.rate(f"u:{u['id']}", 900, 60) or (path in HEAVY and P.rate(f"heavy:{u['id']}", 40, 60)):
            return jerr("عمليات كثيرة في وقت قصير. انتظر دقيقة.", 429)
        if P.setting("maintenance") and u.get("role") != "admin" and path not in ("/api/me", "/api/logout"):
            return jerr(P.setting("maintenance_msg"), 503)
        if path.startswith("/admin") or path.startswith("/api/admin"):
            if u.get("role") != "admin":
                return jerr("forbidden", 403) if path.startswith("/api/") else Response("Not Found", 404, {"Content-Type": "text/plain"})
        ft = FEATURE_OF.get(path)
        if ft and not P.can(ft):
            return jerr("هذه الميزة غير مفعّلة في اشتراكك.", 403)
        if path in ("/api/fs_test", "/api/cleanup", "/api/storage", "/api/diag") and u.get("role") != "admin":
            return jerr("forbidden", 403)
        return None

    @app.after_request
    def _hdr(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        resp.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                                "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
                                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
        if request.path.startswith("/api/") and not request.path.startswith("/api/video") and not request.path.startswith("/api/still"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---- pages & session
    @app.route("/login")
    def login_page():
        return Response(sa_pages.LOGIN.replace("__SITE__", P.setting("site_name")), mimetype="text/html")

    @app.route("/api/login", methods=["POST"])
    def api_login():
        d = request.get_json(silent=True) or {}
        raw = (d.get("id") or "").strip()
        uid, pw = norm_id(raw), (d.get("password") or "")
        ip = P.ip()
        if "@" in raw:  # the administrator can sign in with the e-mail address
            em = raw.lower()
            adm = P.db.get("users", "ADMIN")
            uid = "ADMIN" if adm and adm.get("email") and adm["email"] == em else "NOBODY@" + em[:40]
        for key, lim, win in ((f"ip:{ip}", 25, 600), (f"idip:{uid}:{ip}", 6, 900), (f"id:{uid}", 40, 3600)):
            wait = P.throttled(key, lim, win)
            if wait:
                return jerr(f"محاولات كثيرة. حاول بعد {wait // 60 + 1} دقيقة.", 429)
        u = P.user_rec(uid) if uid else None
        if P.rate(f"loginpost:{ip}", 60, 600):
            return jerr("محاولات كثيرة. حاول بعد قليل.", 429)
        pw_try = [pw.strip(), re.sub(r"[\s]+", "", pw)]
        flat = re.sub(r"[\s-]+", "", pw)
        if len(flat) == 12 and flat.isalnum():  # tolerate a pasted password without its dashes
            pw_try.append("-".join([flat[:4], flat[4:8], flat[8:]]))
        ok = False
        h = (u or {}).get("pw") or DUMMY
        for cand in dict.fromkeys(pw_try):
            ok = check_pw(cand, h) or ok
        if not (u and ok):
            P.fail(f"ip:{ip}"); P.fail(f"idip:{uid}:{ip}"); P.fail(f"id:{uid}")
            if len(P.fails.get(f"idip:{uid}:{ip}", [])) <= 3:
                P.audit("login_fail", uid, "", "bad credentials", ip)
            return jerr("المعرّف أو كلمة المرور غير صحيحة.", 401)
        st = P.status_of(u)
        if st == "suspended":
            return jerr("هذا الحساب موقوف. تواصل مع المدير.", 403)
        if u.get("role") == "admin":
            if P.throttled(f"admin:{ip}", 8, 1800):
                return jerr("محاولات كثيرة على حساب المدير. حاول لاحقاً.", 429)
            tot = u.get("totp")
            if tot and os.environ.get("ADMIN_2FA_OFF") != "1":
                code = (d.get("totp") or "").strip()
                if not code:
                    return jsonify({"need_totp": True})
                used = P.totp_verify(tot, code, int(u.get("totp_last", 0)))
                if not used:
                    P.fail(f"admin:{ip}"); P.fail(f"ip:{ip}")
                    P.audit("admin_2fa_fail", uid, "", "bad code", ip)
                    return jerr("رمز التحقق غير صحيح.", 401)
                u = P.db.put("users", uid, {**u, "totp_last": used})
        if st == "pending":  # subscription starts at first login
            u = dict(u); u["expires"] = time.time() + int(u.get("days", 30)) * DAY
        elif st == "expired":
            return jerr("انتهى اشتراكك بتاريخ " + time.strftime("%Y-%m-%d", time.gmtime(u["expires"])) + ". تواصل مع المدير للتجديد.", 403)
        dev = (u.get("devices") or [])
        ua = (request.headers.get("User-Agent") or "")[:90]
        dev = [x for x in dev if not (x.get("ip") == ip and x.get("ua") == ua)]
        dev.insert(0, {"ip": ip, "ua": ua, "t": time.time()})
        u = P.db.put("users", uid, {**u, "last_login": time.time(), "logins": u.get("logins", 0) + 1, "devices": dev[:12]})
        P.audit("login", uid, "", ua[:60], ip)
        P.sweep_sessions()
        adm = u.get("role") == "admin"
        days = 0.5 if adm else 14
        old = (P.read_session(request.cookies.get("sa_s", "")) or (None, None, None))[1]
        sid = P.open_session(u, days, old)
        u = P.user_rec(uid) or u
        if u.get("status") == "suspended":  # the kick limit just tripped
            return jerr("تم إيقاف الحساب تلقائياً بسبب اشتباه مشاركته بين عدة أشخاص. تواصل مع المدير.", 403)
        resp = jsonify({"ok": True, "admin": adm})
        sec = request.is_secure or request.headers.get("X-Forwarded-Proto") == "https"
        resp.set_cookie("sa_s", P.make_cookie(u, sid, days), max_age=int(days * DAY), httponly=True, samesite="Lax", secure=sec, path="/")
        return resp

    @app.route("/api/logout", methods=["POST"])
    @app.route("/logout")
    def api_logout():
        resp = redirect("/login") if request.method == "GET" else jsonify({"ok": True})
        _u, _sid, _w = P.read_session(request.cookies.get("sa_s", ""))
        if _sid: P.revoke_session(_sid, "logout")
        resp.delete_cookie("sa_s", path="/")
        return resp

    @app.route("/api/mykeys", methods=["GET", "PUT"])
    def api_mykeys():
        uid = P.uid()
        cur = dict(P.db.get("state", "keys:" + uid) or {})
        check = None
        if request.method == "PUT":
            d = request.get_json(silent=True) or {}
            ev = (d.get("elevenlabs_key") or "").strip() if isinstance(d.get("elevenlabs_key"), str) else ""
            if ev and ev != "-":  # refuse to store a key ElevenLabs does not recognise (it would silently override the site key)
                if P.rate(f"keyput:{uid}", 10, 60):
                    return jerr("تمهّل قليلاً", 429)
                try:
                    import sa_eleven
                    pr0 = sa_eleven.probe(ev)
                    if not pr0["valid"] and not any("تعذّر الاتصال" in n for n in pr0["notes"]):
                        return jerr(sa_eleven.summary(pr0) + " — لم يُحفظ. تأكد من نسخ المفتاح كاملاً من ElevenLabs.", 400)
                except Exception:
                    pass
            for k in USER_KEY_UI:
                if k in d and isinstance(d[k], str):
                    v = d[k].strip()
                    if not v:
                        cur.pop(k, None)
                    elif re.fullmatch(r"[A-Za-z0-9_\-\.]{8,200}", v):
                        cur[k] = v
                    else:
                        return jerr("صيغة المفتاح غير صحيحة (أحرف وأرقام وشرطات فقط).", 400)
            for k, rx in USER_PLAIN.items():
                if k in d and isinstance(d[k], str):
                    v = d[k].strip().rstrip("/")
                    if not v:
                        cur.pop(k, None)
                    elif re.fullmatch(rx, v):
                        cur[k] = v
                    else:
                        return jerr(f"قيمة غير صحيحة: {k}", 400)
            P.db.put("state", "keys:" + uid, cur)
            P.audit("mykeys", uid, "", ",".join(sorted(cur)), P.ip())
            check = None
            if d.get("elevenlabs_key"):  # validate immediately so the subscriber knows if the key was recognised
                try:
                    import sa_eleven
                    pr = sa_eleven.probe(cur.get("elevenlabs_key", ""))
                    check = {"ok": pr["valid"], "msg": sa_eleven.summary(pr), "caps": pr["caps"]}
                except Exception as e:
                    check = {"ok": False, "msg": "تعذّر فحص المفتاح: " + str(e)[:100]}
        site = P.settings()
        return jsonify({"check": check if request.method == "PUT" else None,
                        "keys": {k: {"set": bool(cur.get(k)), "tail": (cur.get(k) or "")[-4:]} for k in USER_KEY_UI},
                        "plain": {k: cur.get(k, "") for k in USER_PLAIN},
                        "platform": {k.replace("_key", ""): bool(site.get(k)) for k in USER_KEY_UI}})

    @app.route("/api/mykeys/test/<prov>", methods=["POST"])
    def api_mykeys_test(prov):
        if prov not in ("elevenlabs", "freesound", "groq", "minimax", "openai"):
            return jerr("bad", 400)
        if P.rate(f"keytest:{P.uid()}", 12, 60):
            return jerr("تمهّل قليلاً", 429)
        import sa_tts
        try:
            return jsonify(sa_tts.test_provider(P, prov))
        except Exception as e:
            return jsonify({"ok": False, "msg": re.sub(r"(token|key|api_key)=[^&\s)']+", r"\1=***", str(e))[:160]})

    @app.route("/api/me")
    def api_me():
        u = P.me()
        if not u:
            u = P.read_cookie(request.cookies.get("sa_s", ""))
            if not u:
                return jerr("auth", 401)
        d = P.public_user(u)
        d["site"] = P.setting("site_name")
        d["keys"] = {"freesound": bool(P.setting("freesound_key")), "tts": P_tts_providers()}
        return jsonify(d)

    def P_tts_providers():
        try:
            import sa_tts
            return sa_tts.available(P)
        except Exception:
            return []

    @app.route("/api/state", methods=["GET", "PUT"])
    def api_state():
        uid = P.uid()
        if request.method == "GET":
            return jsonify(P.db.get("state", uid, {}) or {})
        d = request.get_json(silent=True) or {}
        code = str(d.get("code", ""))[:400000]
        cfg = d.get("cfg") if isinstance(d.get("cfg"), dict) else {}
        P.db.put("state", uid, {"code": code, "cfg": cfg, "t": time.time()})
        return jsonify({"ok": True})

    # ---- media (replaces the studio's global library)
    @app.route("/api/media")
    def media_list():
        out = []
        for m in P.h.MEDIA.values():
            if m.get("owner") != P.uid() and not (P.is_admin() and request.args.get("all")):
                continue
            r = {k: v for k, v in m.items() if k not in ("locs",)}
            r["cached"] = os.path.exists(f"{P.h.W}/public/{m['file']}")
            r["backed"] = bool(m.get("locs"))
            out.append(r)
        return jsonify({"items": sorted(out, key=lambda x: -x.get("created", 0))})

    @app.route("/api/media/<name>", methods=["DELETE"])
    def media_delete(name):
        name = os.path.basename(name)
        if not re.fullmatch(r"m_[a-z0-9_]+\.(mp4|m4a)", name) or not P.owns(name):
            return jerr("not found", 404)
        P.delete_media(name)
        P.audit("media_delete", P.uid(), "", name, P.ip())
        return jsonify({"ok": True})

    @app.route("/api/media/<name>/file")
    def media_file(name):
        name = os.path.basename(name)
        if not P.owns(name) or P.media_access(name):
            abort(404)
        return send_file(f"{P.h.W}/public/{name}", conditional=True)

    # ---- admin
    register_admin(app)


def _user_row(u):
    st = P.status_of(u)
    us = P.usage(u["id"])
    q = P.quotas(u)
    return {"id": u["id"], "name": u.get("name", ""), "role": u.get("role"), "plan": u.get("plan"), "status": st, "created": u.get("created"),
            "expires": u.get("expires", 0), "days": u.get("days"), "start": u.get("start"), "last_login": u.get("last_login", 0), "logins": u.get("logins", 0),
            "features": P.features(u), "custom_features": u.get("features") is not None, "quotas": q, "custom_quotas": u.get("quotas") or {},
            "usage": us, "totals": u.get("totals", {}), "note": u.get("note", ""), "flag": u.get("flag", ""),
            "sessions": len(P.sessions_of(u["id"])), "kicks24": len([t for t in (u.get("kicks") or []) if time.time() - t < DAY]), "storage_mb": round(P.storage_used(u["id"]) / 1e6, 1),
            "days_left": None if u.get("role") == "admin" else (int((u["expires"] - time.time()) // DAY) if u.get("expires") else None)}


def _message(rec, pw, base):
    s = P.settings()
    exp = rec.get("expires")
    plan = (P.plans().get(rec["plan"]) or {}).get("label", rec["plan"])
    feats = "، ".join(FEATURES[f] for f in P.features(rec) if f in FEATURES)
    lines = [f"🎬 {s['site_name']}", f"🔗 الرابط: {s.get('public_url') or base}", f"🆔 المعرّف: {rec['id']}", f"🔑 كلمة المرور: {pw}",
             f"📅 المدة: {rec.get('days')} يوم" + (f" (تنتهي {time.strftime('%Y-%m-%d', time.gmtime(exp))})" if exp else " (تبدأ عند أول دخول)"), f"⭐ الباقة: {plan}", f"✅ المزايا: {feats}"]
    if s.get("welcome"):
        lines.append(s["welcome"])
    return "\n".join(lines)


def register_admin(app):
    host = P.h
    db = P.db

    def A():
        return P.uid()

    @app.route("/admin")
    def admin_page():
        return Response(sa_pages.ADMIN.replace("__SITE__", P.setting("site_name")), mimetype="text/html")

    @app.route("/api/admin/meta")
    def adm_meta():
        return jsonify({"features": FEATURES, "quota_labels": QUOTA_LABELS, "plans": P.plans(), "settings": _safe_settings()})

    def _safe_settings():
        s = P.settings()
        out = {k: v for k, v in s.items() if k not in SECRET_KEYS}
        for k in SECRET_KEYS:
            v = s.get(k, "")
            out[k] = {"set": bool(v), "tail": v[-4:] if v else ""}
        return out

    @app.route("/api/admin/overview")
    def adm_overview():
        users = [u for u in db.all("users").values() if u.get("role") != "admin"]
        now = time.time()
        stc = {"active": 0, "expired": 0, "suspended": 0, "pending": 0, "expiring": 0}
        for u in users:
            st = P.status_of(u)
            stc[st] += 1
            if st == "active" and u.get("expires") and u["expires"] - now < 3 * DAY:
                stc["expiring"] += 1
        td = today()
        renders = sum(v.get("renders", 0) for k, v in db.all("usage").items() if k.endswith(":" + td))
        tts = sum(v.get("tts_chars", 0) for k, v in db.all("usage").items() if k.endswith(":" + td))
        jobs = [j for j in host.JOBS.values() if j.get("status") == "processing"]
        media = list(host.MEDIA.values())
        aud = sorted(db.all("audit").items(), reverse=True)[:12]
        top = sorted(users, key=lambda u: -(u.get("totals", {}).get("renders", 0)))[:5]
        pool = sa_cloud.POOL
        try: cap = int(P.setting("cloud_slots", 15))
        except Exception: cap = 15
        live = []
        for j in list(host.JOBS.values()):
            if j.get("status") == "processing":
                live.append({"id": j.get("id"), "owner": j.get("owner"), "kind": j.get("kind"), "cloud": bool(j.get("cloud")), "stage": j.get("stage"),
                             "progress": j.get("progress"), "details": j.get("details"), "age": int(now - j.get("created", now)), "run_url": j.get("run_url")})
        sus = sorted([{"id": u["id"], "name": u.get("name", ""), "kicks24": len([t for t in (u.get("kicks") or []) if now - t < DAY]), "status": P.status_of(u)}
                      for u in users if any(now - t < DAY for t in (u.get("kicks") or []))], key=lambda r: -r["kicks24"])[:8]
        fails24 = sum(1 for v in db.all("audit").values() if v.get("ev") in ("login_fail", "admin_2fa_fail") and now - v.get("t", 0) < DAY)
        return jsonify({"alerts": {"sharing": sus, "fails24": fails24, "twofa": bool((db.get("users", "ADMIN") or {}).get("totp"))}, "cloud": {"used": pool.used, "cap": cap, "queued": max(0, len(pool.q)), "jobs": live[:30]}, "users": len(users), "status": stc, "renders_today": renders, "tts_today": tts, "running": len(jobs),
                        "media": {"count": len(media), "mb": round(sum(m.get("size", 0) for m in media) / 1e6, 1), "backed": sum(1 for m in media if m.get("locs"))},
                        "storage": P.v.status(), "instance": {"run": os.environ.get("GITHUB_RUN_ID", "local"), "uptime": int(now - P.started), "version": host.VERSION, "cloud": host.cloud_enabled(), "repo": host.GH_REPO},
                        "recent": [dict(v, id=k) for k, v in aud], "top": [{"id": u["id"], "name": u.get("name"), "renders": u.get("totals", {}).get("renders", 0)} for u in top]})

    @app.route("/api/admin/users", methods=["GET", "POST"])
    def adm_users():
        if request.method == "GET":
            q = (request.args.get("q") or "").strip().lower()
            st = request.args.get("status") or ""
            rows = []
            for u in db.all("users").values():
                if u.get("role") == "admin":
                    continue
                r = _user_row(u)
                if q and q not in (u["id"].lower() + " " + (u.get("name") or "").lower() + " " + (u.get("note") or "").lower()):
                    continue
                if st and r["status"] != st and not (st == "expiring" and r["status"] == "active" and r["days_left"] is not None and r["days_left"] < 3):
                    continue
                rows.append(r)
            rows.sort(key=lambda r: -(r["created"] or 0))
            return jsonify({"items": rows})
        d = request.get_json(silent=True) or {}
        try:
            days = int(d.get("days", 30))
            count = max(1, min(50, int(d.get("count", 1))))
        except Exception:
            return jerr("قيم غير صالحة")
        feats = d.get("features") if isinstance(d.get("features"), list) else None
        if feats is not None:
            feats = [f for f in feats if f in FEATURES]
        quotas = {k: int(v) for k, v in (d.get("quotas") or {}).items() if k in QUOTA_LABELS and str(v).lstrip("-").isdigit()}
        out = []
        base = request.host_url.rstrip("/")
        for i in range(count):
            nm = d.get("name", "")
            rec, pw = P.create_user((nm + (f" {i + 1}" if count > 1 and nm else "")), days, d.get("plan"), feats, quotas, d.get("start", "now"), d.get("note", ""), actor=A())
            out.append({"id": rec["id"], "password": pw, "message": _message(rec, pw, base), "expires": rec["expires"]})
        db.flush()
        return jsonify({"created": out})

    @app.route("/api/admin/users/<uid>", methods=["GET", "PATCH", "DELETE"])
    def adm_user(uid):
        uid = norm_id(uid)
        u = db.get("users", uid)
        if not u or u.get("role") == "admin":
            return jerr("not found", 404)
        if request.method == "GET":
            days = [time.strftime("%Y%m%d", time.gmtime(time.time() - i * DAY)) for i in range(30)]
            hist = [{"day": d, **(P.usage(uid, d))} for d in days]
            jobs = [{"id": k, "kind": j.get("kind"), "status": j.get("status"), "created": j.get("created"), "error": (j.get("error") or "")[:120]} for k, j in host.JOBS.items() if j.get("owner") == uid]
            media = [{"file": m["file"], "original": m.get("original"), "type": m.get("type"), "duration": m.get("duration"), "size": m.get("size", 0), "backed": bool(m.get("locs")), "created": m.get("created")} for m in host.MEDIA.values() if m.get("owner") == uid]
            aud = [dict(v, id=k) for k, v in sorted(db.all("audit").items(), reverse=True) if v.get("uid") == uid][:60]
            return jsonify({"user": _user_row(u), "history": hist, "jobs": jobs[-20:], "media": media, "devices": u.get("devices", []), "audit": aud})
        if request.method == "DELETE":
            purge = request.args.get("purge", "1") != "0"
            for m in [m["file"] for m in host.MEDIA.values() if m.get("owner") == uid]:
                if purge:
                    P.delete_media(m)
            db.delete("users", uid)
            db.delete("state", "keys:" + uid)
            for k0, v0 in list(db.all("sessions").items()):
                if v0.get("uid") == uid: db.delete("sessions", k0)
            P.audit("delete_user", uid, A(), "purge" if purge else "keep media")
            db.flush()
            return jsonify({"ok": True})
        d = request.get_json(silent=True) or {}
        upd = {}
        if "name" in d: upd["name"] = str(d["name"])[:60]
        if "note" in d: upd["note"] = str(d["note"])[:300]
        if d.get("plan") in P.plans(): upd["plan"] = d["plan"]
        if "features" in d:
            upd["features"] = None if d["features"] is None else [f for f in d["features"] if f in FEATURES]
        if "quotas" in d and isinstance(d["quotas"], dict):
            upd["quotas"] = {k: int(v) for k, v in d["quotas"].items() if k in QUOTA_LABELS and str(v).lstrip("-").isdigit()}
        if d.get("status") in ("active", "suspended"):
            upd["status"] = d["status"]
            if d["status"] == "suspended":
                upd["sv"] = u.get("sv", 1) + 1
        if "expires" in d and str(d["expires"]).isdigit():
            upd["expires"] = int(d["expires"])
        db.put("users", uid, {**u, **upd})
        P.audit("edit_user", uid, A(), ",".join(upd.keys()))
        return jsonify({"ok": True, "user": _user_row(db.get("users", uid))})

    @app.route("/api/admin/users/<uid>/extend", methods=["POST"])
    def adm_extend(uid):
        uid = norm_id(uid)
        u = db.get("users", uid)
        d = request.get_json(silent=True) or {}
        if not u: return jerr("not found", 404)
        try: days = int(d.get("days"))
        except Exception: return jerr("عدد الأيام غير صالح")
        if u.get("expires"):
            base = max(time.time(), u["expires"]) if days > 0 else u["expires"]
            u = db.put("users", uid, {**u, "expires": base + days * DAY, "status": "active" if u.get("status") != "suspended" else "suspended"})
        else:
            u = db.put("users", uid, {**u, "days": max(0, int(u.get("days", 0)) + days)})
        P.audit("extend", uid, A(), f"{days:+d}d")
        return jsonify({"ok": True, "user": _user_row(u)})

    @app.route("/api/admin/users/<uid>/reset", methods=["POST"])
    def adm_reset(uid):
        uid = norm_id(uid)
        u = db.get("users", uid)
        if not u or u.get("role") == "admin": return jerr("not found", 404)
        pw = gen_pw()
        u = db.put("users", uid, {**u, "pw": hash_pw(pw), "sv": u.get("sv", 1) + 1})
        P.audit("reset_pw", uid, A())
        return jsonify({"id": uid, "password": pw, "message": _message(u, pw, request.host_url.rstrip("/"))})

    @app.route("/api/admin/users/<uid>/logout", methods=["POST"])
    def adm_force_logout(uid):
        uid = norm_id(uid)
        u = db.get("users", uid)
        if not u: return jerr("not found", 404)
        db.put("users", uid, {**u, "sv": u.get("sv", 1) + 1})
        P.audit("force_logout", uid, A())
        return jsonify({"ok": True})

    @app.route("/api/admin/users/<uid>/sessions")
    def adm_sessions(uid):
        uid = norm_id(uid)
        return jsonify({"items": [dict(v, id=k) for k, v in reversed(P.sessions_of(uid))]})

    @app.route("/api/admin/sessions/<sid>/revoke", methods=["POST"])
    def adm_revoke(sid):
        s = db.get("sessions", sid)
        if not s: return jerr("غير موجودة", 404)
        P.revoke_session(sid, "admin")
        P.audit("session_revoke", s.get("uid", ""), A(), sid[:6])
        return jsonify({"ok": True})

    @app.route("/api/admin/users/<uid>/unflag", methods=["POST"])
    def adm_unflag(uid):
        uid = norm_id(uid); u = db.get("users", uid)
        if not u: return jerr("غير موجود", 404)
        db.put("users", uid, {**u, "kicks": [], "flag": ""})
        P.audit("unflag", uid, A())
        return jsonify({"ok": True})

    @app.route("/api/admin/2fa", methods=["GET", "POST", "DELETE"])
    def adm_2fa():
        u = db.get("users", "ADMIN") or {}
        if request.method == "GET":
            return jsonify({"enabled": bool(u.get("totp")), "forced_off": os.environ.get("ADMIN_2FA_OFF") == "1"})
        d = request.get_json(silent=True) or {}
        if request.method == "POST":
            if d.get("action") == "setup":
                sec = base64.b32encode(os.urandom(20)).decode().rstrip("=")
                db.put("users", "ADMIN", {**u, "totp_pending": sec})
                site = P.setting("site_name").replace(" ", "")
                return jsonify({"secret": sec, "uri": f"otpauth://totp/{site}:admin?secret={sec}&issuer={site}&digits=6&period=30"})
            if d.get("action") == "enable":
                sec = u.get("totp_pending")
                c = P.totp_verify(sec, d.get("code", "")) if sec else 0
                if not c: return jerr("الرمز غير صحيح. تأكد من ساعة الهاتف وأعد المحاولة.", 400)
                db.put("users", "ADMIN", {**u, "totp": sec, "totp_pending": None, "totp_last": c, "sv": u.get("sv", 1)})
                P.audit("admin_2fa_on", "ADMIN", A())
                return jsonify({"ok": True})
        if request.method == "DELETE":
            c = P.totp_verify(u.get("totp", ""), (request.args.get("code") or d.get("code") or ""), int(u.get("totp_last", 0))) if u.get("totp") else 1
            if not c: return jerr("الرمز غير صحيح.", 400)
            db.put("users", "ADMIN", {**u, "totp": None, "totp_pending": None})
            P.audit("admin_2fa_off", "ADMIN", A())
            return jsonify({"ok": True})
        return jerr("bad request", 400)

    @app.route("/api/admin/audit")
    def adm_audit():
        uid = norm_id(request.args.get("uid", ""))
        ev = request.args.get("ev", "")
        rows = [dict(v, id=k) for k, v in sorted(db.all("audit").items(), reverse=True)]
        if uid: rows = [r for r in rows if r.get("uid") == uid]
        if ev: rows = [r for r in rows if r.get("ev") == ev]
        return jsonify({"items": rows[:300]})

    @app.route("/api/admin/settings", methods=["GET", "PUT"])
    def adm_settings():
        if request.method == "GET":
            return jsonify(_safe_settings())
        d = request.get_json(silent=True) or {}
        cur = dict(db.get("settings", "main", {}) or {})
        for k in ("site_name", "public_url", "maintenance_msg", "welcome", "default_plan"):
            if k in d: cur[k] = str(d[k])[:300]
        if "maintenance" in d: cur["maintenance"] = bool(d["maintenance"])
        if "max_cloud" in d:
            try: cur["max_cloud"] = max(1, min(30, int(d["max_cloud"])))
            except Exception: pass
        if "share_kicks" in d:
            try: cur["share_kicks"] = max(0, min(50, int(d["share_kicks"])))
            except Exception: pass
        if "sec_per_machine" in d:
            try: cur["sec_per_machine"] = max(2, min(120, int(d["sec_per_machine"])))
            except Exception: pass
        if "cloud_slots" in d:
            try: cur["cloud_slots"] = max(4, min(19, int(d["cloud_slots"])))
            except Exception: pass
        for k in PLAIN_KEYS:
            if k in d: cur[k] = str(d[k]).strip()[:200]
        changed = []
        for k in SECRET_KEYS:
            if k in d and isinstance(d[k], str) and d[k].strip() and not d[k].startswith("•"):
                cur[k] = d[k].strip(); changed.append(k)
            elif d.get(k) == "":
                cur.pop(k, None); changed.append(k + "(removed)")
        db.put("settings", "main", cur)
        P.audit("settings", "", A(), ",".join(changed) or "updated")
        db.flush()
        return jsonify({"ok": True, "settings": _safe_settings()})

    @app.route("/api/admin/plans", methods=["PUT"])
    def adm_plans():
        d = request.get_json(silent=True) or {}
        plans = {}
        for k, v in (d.get("plans") or {}).items():
            if not re.fullmatch(r"[a-z0-9_]{2,20}", k): continue
            plans[k] = {"label": str(v.get("label", k))[:30], "features": [f for f in v.get("features", []) if f in FEATURES],
                        "quotas": {a: int(b) for a, b in (v.get("quotas") or {}).items() if a in QUOTA_LABELS and str(b).lstrip("-").isdigit()}}
        if not plans: return jerr("لا باقات")
        db.put("settings", "plans", {"plans": plans})
        P.audit("plans", "", A(), ",".join(plans))
        db.flush()
        return jsonify({"ok": True, "plans": plans})

    @app.route("/api/admin/test/<prov>", methods=["POST"])
    def adm_test(prov):
        try:
            import sa_tts
            return jsonify(sa_tts.test_provider(P, prov))
        except Exception as e:
            return jsonify({"ok": False, "msg": f"{type(e).__name__}: {e}"})

    @app.route("/api/admin/storage")
    def adm_storage():
        st = P.v.status()
        media = list(host.MEDIA.values())
        st["media"] = {"count": len(media), "bytes": sum(m.get("size", 0) for m in media), "backed": sum(1 for m in media if m.get("locs")),
                       "unbacked": [{"file": m["file"], "err": m.get("backup_err", ""), "owner": m.get("owner")} for m in media if not m.get("locs")][:50],
                       "cached": sum(1 for m in media if os.path.exists(f"{host.W}/public/{m['file']}"))}
        st["backends"] = {"github": bool(P.v.gh), "telegram": bool(P.v.tg)}
        return jsonify(st)

    @app.route("/api/admin/storage/<act>", methods=["POST"])
    def adm_storage_act(act):
        if act == "sync":
            errs = db.flush(force=True, tg=True)
            n = db.pull()
            P.load_media()
            P.audit("storage_sync", "", A(), "; ".join(errs)[:200])
            return jsonify({"ok": not errs, "errors": errs, "merged": n})
        if act == "selftest":
            return jsonify(P.v.self_test())
        if act == "rebackup":
            todo = [n for n, m in host.MEDIA.items() if not m.get("locs") and os.path.exists(f"{host.W}/public/{n}")]
            for n in todo:
                threading.Thread(target=P._backup, args=(n,), daemon=True).start()
            return jsonify({"started": len(todo)})
        if act == "restore_tg":
            ok = db.restore_from_tg()
            P.load_media()
            return jsonify({"ok": ok})
        return jerr("unknown", 404)

    @app.route("/api/admin/backup")
    def adm_backup():
        with db.lk:
            raw = json.dumps(db.c, ensure_ascii=False, separators=(",", ":")).encode()
        blob = P.v.crypt.seal(raw, aad=b"bundle")
        P.audit("backup_download", "", A(), "", P.ip())
        return Response(blob, mimetype="application/octet-stream", headers={"Content-Disposition": f"attachment; filename=sa-backup-{time.strftime('%Y%m%d-%H%M')}.enc"})

    @app.route("/api/admin/jobs")
    def adm_jobs():
        rows = [{"id": k, "owner": j.get("owner"), "kind": j.get("kind"), "status": j.get("status"), "stage": j.get("stage"), "progress": j.get("progress"), "created": j.get("created"), "error": (j.get("error") or "")[:160]}
                for k, j in host.JOBS.items()]
        return jsonify({"items": sorted(rows, key=lambda r: -(r["created"] or 0))[:80]})
