# -*- coding: utf-8 -*-
# ============================================================================
#  SA Motion Studio v11.0  —  Subscription Platform (Colab / Codespaces / أي سيرفر)
#  الواجهة + التفريغ + قص الصمت + المؤثرات هنا، والرندر الثقيل موزّع على أجهزة GitHub Actions (متوازي).
#  يعمل في أي بيئة تلقائياً مع إصلاح الصلاحيات، المسارات، والرندر بدون أخطاء.
# ============================================================================
import os, sys, re, time, subprocess, json, urllib.request, shutil, hashlib, platform, socket

# تحديد مسار العمل بذكاء: إذا كنا في Colab نستخدم /content/sa-workspace، وإلا نستخدم مجلد المشروع الحالي في GitHub/Lightning
if os.path.isdir("/content"):
    BASE = "/content"
    W = f"{BASE}/sa-workspace"
else:
    W = os.path.abspath(os.path.dirname(__file__) if "__file__" in locals() else os.getcwd())
    BASE = W

os.makedirs(W, exist_ok=True)
SUDO = "" if (hasattr(os, "geteuid") and os.geteuid() == 0) else "sudo -n "

def sh(cmd, cwd=None, timeout=None):
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        print("⏱ انتهت مهلة أمر:", cmd[:80], flush=True)
        return 124, "timeout"
APT = "-o DPkg::Lock::Timeout=90 -o Acquire::Retries=2 -o Acquire::http::Timeout=25 -o Acquire::https::Timeout=25 "


print("🎬 جاري بناء وتجهيز SA Motion Studio v11.0 ...")
for pat in ["python3 [a]pp.py"] + ([] if os.environ.get("SA_NO_TUNNEL") else ["[c]loudflared tunnel"]) + ["[r]ender.cjs", "[c]hrome-headless-shell"]:
    subprocess.run(["pkill", "-f", pat], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

# ===================== اعتماديات النظام =====================
print("📦 فحص وتثبيت اعتماديات النظام ...")
PKGS = ["ffmpeg", "fonts-noto-core", "fonts-noto-color-emoji", "fonts-hosny-amiri", "libnss3", "libatk-bridge2.0-0",
        "libgbm1", "libxkbcommon0", "libasound2", "libasound2t64", "libcups2", "libxcomposite1", "libxdamage1",
        "libxrandr2", "libpango-1.0-0", "libcairo2"]
def dpkg_has(p):
    return subprocess.run(["dpkg", "-s", p], capture_output=True).returncode == 0
ALT = {"libasound2": ["libasound2", "libasound2t64"], "libasound2t64": ["libasound2", "libasound2t64"]}
need, seen = [], set()
for p in PKGS:
    grp = tuple(ALT.get(p, [p]))
    if grp in seen: continue
    seen.add(grp)
    if not any(dpkg_has(x) for x in grp): need.append(grp)
if need:
    print("   حزم ناقصة:", " ".join(g[0] for g in need), flush=True)
    sh(f"{SUDO}apt-get {APT}update -qq", timeout=180)
    for grp in need:
        for p in grp:
            rc, _ = sh(f"{SUDO}DEBIAN_FRONTEND=noninteractive apt-get {APT}install -y -qq --no-install-recommends {p}", timeout=240)
            print("   ", p, "✓" if rc == 0 else "✗", flush=True)
            if rc == 0: break
    sh("fc-cache -f", timeout=120)

import importlib.util
if not all(importlib.util.find_spec(m) for m in ("flask", "requests", "faster_whisper", "cryptography")):
    print("🐍 تثبيت مكتبات Python (flask, requests, faster-whisper) ...")
    sh(f"{sys.executable} -m pip install -q --disable-pip-version-check flask requests cryptography 'faster-whisper==1.1.1'", timeout=900)

def node_major():
    try:
        v = subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.strip()
        return int(v.lstrip("v").split(".")[0])
    except Exception:
        return 0
if node_major() < 18:
    print("🟢 ترقية Node.js إلى الإصدار 20 ...")
    sh(f"curl -fsSL https://deb.nodesource.com/setup_20.x | {SUDO}bash - && {SUDO}apt-get {APT}install -y -qq nodejs", timeout=420)
print("Node:", subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.strip())

for d in ['src', 'out', 'public', 'public/audio', 'uploads', 'sfx_cache']:
    os.makedirs(f'{W}/{d}', exist_ok=True)
os.chdir(W)

# ===================== Remotion + React 19 =====================
def pv(name):
    try: return json.load(open(f"node_modules/{name}/package.json"))["version"]
    except Exception: return None

if not os.path.exists("package.json"): sh("npm init -y")
FLAGS = "--no-audit --no-fund --loglevel=error --legacy-peer-deps"
if not pv("remotion"): sh(f"npm install {FLAGS} remotion@4", timeout=900)
ver = pv("remotion")
RPK = ["@remotion/cli", "@remotion/bundler", "@remotion/renderer", "@remotion/google-fonts", "@remotion/transitions"]
react_ok = all((pv(p) or "0").split(".")[0] == "19" for p in ("react", "react-dom"))
if ver and (not react_ok or any(pv(p) != ver for p in RPK)):
    print("⚙️  تثبيت حزم Remotion وReact 19 (قد يستغرق دقيقة) ...")
    shutil.rmtree("node_modules/.cache", ignore_errors=True)
    rc, out = sh(f"npm install {FLAGS} " + " ".join(f"{p}@{ver}" for p in RPK) + " react@19 react-dom@19")
    if rc != 0: print(out[-1500:])
print("🌐 التأكد من متصفح الرندر ...", flush=True)
sh("npx remotion browser ensure", timeout=600)
print("Remotion:", pv("remotion"), "| React:", pv("react"), "| esbuild:", pv("esbuild"))

open('tsconfig.json', 'w').write(json.dumps({
    "compilerOptions": {"target": "ES2020", "module": "ESNext", "moduleResolution": "node", "jsx": "react-jsx",
        "strict": False, "noEmit": True, "lib": ["DOM", "ES2020"], "esModuleInterop": True, "skipLibCheck": True,
        "resolveJsonModule": True}, "include": ["src"], "exclude": ["remotion.config.ts", "node_modules"]}, indent=2))
open('remotion.config.ts', 'w').write(
    "import { Config } from '@remotion/cli/config';\n"
    "Config.setVideoImageFormat('jpeg');\n"
    "Config.setJpegQuality(92);\n"
    "Config.setChromiumOpenGlRenderer('swangle');\n"
    "Config.setBrowserExecutable(null);\n"
)

# ===================== مكتبة المؤثرات (تُولَّد محلياً) =====================
SYNTH = {
    "whoosh": "anoisesrc=d=0.9:c=pink:a=0.6,bandpass=f=1000:width_type=o:w=2.5,afade=t=in:d=0.45:curve=qsin,afade=t=out:st=0.45:d=0.45:curve=qsin,volume=4",
    "pop":    "aevalsrc='0.8*sin(2*PI*(450+1000*exp(-30*t))*t)*exp(-16*t)':d=0.25,volume=1.8",
    "impact": "aevalsrc='0.95*sin(2*PI*50*t*(1+2.5*exp(-10*t)))*exp(-3*t)+0.3*(random(0)-0.5)*exp(-22*t)':d=1.4,lowpass=f=600,volume=2.4",
    "rise":   "aevalsrc='0.3*sin(2*PI*(200+900*t*t)*t)+0.12*(random(0)-0.5)*t':d=1.4,afade=t=in:d=1.2:curve=exp,afade=t=out:st=1.3:d=0.1,volume=2.2",
    "ding":   "aevalsrc='0.5*sin(2*PI*1320*t)*exp(-5*t)+0.25*sin(2*PI*1980*t)*exp(-7*t)':d=0.9",
    "typing": "anoisesrc=d=0.5:c=white:a=0.3,highpass=f=2000,apulsator=hz=14,afade=t=out:st=0.4:d=0.1",
    "click":  "aevalsrc='0.8*sin(2*PI*1800*t)*exp(-90*t)':d=0.08,volume=1.6",
    "bass":   "aevalsrc='0.9*sin(2*PI*55*t)*exp(-2.5*t)':d=1.5,lowpass=f=200,volume=2",
    "glitch": "anoisesrc=d=0.35:c=white:a=0.5,apulsator=hz=30,bandpass=f=3000,afade=t=out:st=0.25:d=0.1",
    "shine":  "aevalsrc='0.4*sin(2*PI*2093*t)*exp(-6*t)+0.3*sin(2*PI*3136*t)*exp(-8*t)+0.2*sin(2*PI*4186*t)*exp(-10*t)':d=1.0",
    "tick":   "aevalsrc='0.7*sin(2*PI*1000*t)*exp(-120*t)':d=0.06,volume=1.5",
}
sig = hashlib.md5(json.dumps(SYNTH, sort_keys=True).encode()).hexdigest()
sigf = f"{W}/public/audio/.sig"
stale = (not os.path.exists(sigf)) or open(sigf).read() != sig
for k, f in SYNTH.items():
    p = f"{W}/public/audio/{k}.mp3"
    if stale or not os.path.exists(p):
        rc, out = sh(f'ffmpeg -y -v error -f lavfi -i "{f}" -ar 48000 -ac 2 -b:a 192k "{p}"')
        if rc != 0: print("تعذر توليد المؤثر", k, out[-200:])
open(sigf, "w").write(sig)
open(f"{W}/sfx_synth.json", "w").write(json.dumps(SYNTH))

# ===================== سكربت الرندر + فاحص الكود =====================
RENDER_JS = r'''const path = require("path");
const fs = require("fs");
const { bundle } = require("@remotion/bundler");
const { renderMedia, renderStill, selectComposition } = require("@remotion/renderer");
const spec = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const emit = (o) => process.stdout.write("@@" + JSON.stringify(o) + "\n");
const chromiumOptions = { gl: "swangle", disableWebSecurity: true, enableMultiProcessOnLinux: true };
const onBrowserLog = (l) => { if (l && (l.type === "error" || l.type === "warning")) emit({ stage: "log", text: String(l.text).slice(0, 600) }); };
(async () => {
  let serveUrl = null;
  try {
    let lastB = -1;
    serveUrl = await bundle({
      entryPoint: path.join(spec.root, "src", "index.ts"), publicDir: spec.publicDir, rootDir: spec.root,
      onProgress: (p) => { const v = Math.round(p); if (v !== lastB) { lastB = v; emit({ stage: "bundle", progress: v }); } },
    });
    emit({ stage: "compose" });
    const composition = await selectComposition({ serveUrl, id: "MainVideo", inputProps: spec.props, chromiumOptions, timeoutInMilliseconds: 180000, onBrowserLog });
    if (spec.mode === "still") {
      await renderStill({ composition, serveUrl, output: spec.output, frame: Math.min(spec.frame, composition.durationInFrames - 1),
        inputProps: spec.props, imageFormat: "jpeg", jpegQuality: 92, chromiumOptions, timeoutInMilliseconds: 180000, onBrowserLog, overwrite: true });
    } else {
      let last = -1; const total = composition.durationInFrames;
      await renderMedia({ composition, serveUrl, codec: "h264", outputLocation: spec.output, inputProps: spec.props,
        crf: spec.crf, x264Preset: spec.preset, pixelFormat: "yuv420p", imageFormat: "jpeg", jpegQuality: 92,
        concurrency: spec.concurrency, enforceAudioTrack: true, audioCodec: "aac", chromiumOptions,
        timeoutInMilliseconds: 180000, onBrowserLog, overwrite: true,
        onProgress: ({ progress, renderedFrames, encodedFrames, stitchStage }) => {
          const v = Math.floor(progress * 100);
          if (v !== last) { last = v; emit({ stage: "render", progress, rendered: renderedFrames, encoded: encodedFrames, total, stitch: stitchStage }); }
        } });
    }
    emit({ stage: "done" });
  } catch (e) {
    emit({ stage: "error", text: String((e && (e.stack || e.message)) || e).slice(0, 6000) }); process.exitCode = 1;
  } finally {
    if (serveUrl) { try { fs.rmSync(serveUrl, { recursive: true, force: true }); } catch (_) {} }
    setTimeout(() => process.exit(process.exitCode || 0), 300);
  }
})();
'''
open('render.cjs', 'w', encoding='utf-8').write(RENDER_JS)

CHECK_JS = r'''const fs = require("fs");
let esbuild = null;
try { esbuild = require("esbuild"); } catch (e) {}
if (!esbuild) { console.log(JSON.stringify({ ok: true, skipped: true })); process.exit(0); }
const code = fs.readFileSync(process.argv[2], "utf8");
try {
  esbuild.transformSync(code, { loader: "tsx", jsx: "automatic", logLevel: "silent" });
  console.log(JSON.stringify({ ok: true }));
} catch (e) {
  const errs = (e.errors || []).map((x) => ({ text: x.text, line: x.location ? x.location.line : 0, col: x.location ? x.location.column : 0, lineText: x.location ? x.location.lineText : "" }));
  console.log(JSON.stringify({ ok: false, errors: errs.length ? errs : [{ text: String(e.message || e).slice(0, 300), line: 0, col: 0, lineText: "" }] }));
}
'''
open('check.cjs', 'w', encoding='utf-8').write(CHECK_JS)

ICON = r'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff7a2f"/><stop offset="1" stop-color="#e8321f"/></linearGradient></defs><rect width="64" height="64" rx="16" fill="url(#g)"/><path d="M24 18 L47 32 L24 46 Z" fill="#fff"/></svg>'''
open('public/icon.svg', 'w', encoding='utf-8').write(ICON)

# ===================== الواجهة =====================
HTML = r'''<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>SA Motion Studio</title><link rel="icon" href="/icon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Readex+Pro:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
<noscript><link href="https://fonts.googleapis.com/css2?family=Readex+Pro:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"></noscript>
<style>
:root{--bg:#fbf7f3;--s1:#ffffff;--s2:#f6f0ea;--s3:#ece3db;--line:#e7ddd4;--t1:#241a16;--t2:#6b5d54;--t3:#9b8d83;--ac:#e8431f;--ac2:#c2370f;--ok:#16a05a;--err:#d92d20;--warn:#d97a00;--r:16px;--grad:linear-gradient(135deg,#ff7a2f,#e8321f);--sh:0 1px 2px rgba(60,30,10,.05),0 8px 24px rgba(60,30,10,.06)}
*{box-sizing:border-box;margin:0;padding:0}html,body{height:100%}
body{font-family:'Readex Pro',system-ui,sans-serif;background:var(--bg);color:var(--t1);display:flex;flex-direction:column;overflow:hidden;font-size:14px;-webkit-tap-highlight-color:transparent}
button,input,select,textarea{font-family:inherit;font-size:inherit;color:inherit}
.ic{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex-shrink:0}
.top{height:58px;flex-shrink:0;display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid var(--line);gap:10px}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;min-width:0;white-space:nowrap}.brand img{width:30px}
.brand small{color:var(--t3);font-size:11px;border:1px solid var(--line);padding:2px 8px;border-radius:20px}
.tright{display:flex;align-items:center;gap:8px;flex-shrink:0}
.iconbtn{display:inline-flex;align-items:center;gap:6px;background:var(--s1);border:1px solid var(--line);border-radius:20px;padding:6px 12px;font-size:12px;color:var(--t2);cursor:pointer}.iconbtn:hover{border-color:var(--ac);color:var(--t1)}.iconbtn .ic{width:15px;height:15px}
.status{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--t2);background:var(--s1);border:1px solid var(--line);padding:6px 12px;border-radius:20px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok)}.dot.busy{animation:pl 1s infinite}@keyframes pl{50%{opacity:.3}}
.app{flex:1;display:grid;grid-template-columns:350px 1fr 440px;min-height:0}
.panel{display:flex;flex-direction:column;min-height:0;min-width:0;border-left:1px solid var(--line)}.panel:last-child{border-left:none}
.scroll{overflow-y:auto;padding:14px;flex:1;-webkit-overflow-scrolling:touch}
.ph{height:44px;flex-shrink:0;display:flex;align-items:center;gap:8px;padding:0 16px;border-bottom:1px solid var(--line);font-size:12px;color:var(--t2)}.ph .ic{color:var(--ac);width:16px;height:16px}
.card{background:var(--s1);border:1px solid var(--line);border-radius:var(--r);padding:14px;margin-bottom:12px}
.card h3{font-size:13px;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:8px}.card h3 b{color:var(--ac);font-family:'JetBrains Mono',monospace;font-size:11px}.card h3 .ic{color:var(--ac2);width:16px;height:16px}
label.l{display:flex;justify-content:space-between;font-size:12px;color:var(--t2);margin:10px 0 5px}
.in{width:100%;background:var(--s2);border:1px solid var(--line);border-radius:10px;padding:9px 11px;outline:none}.in:focus{border-color:var(--ac)}
.row{display:flex;gap:8px}.row>*{flex:1;min-width:0}
.chips{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}
.chip{background:var(--s2);border:1px solid var(--line);border-radius:10px;padding:9px 6px;cursor:pointer;font-size:12px;text-align:center}.chip.on{border-color:var(--ac);background:rgba(255,106,61,.08)}
.qk{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}.qc{background:var(--s2);border:1px solid var(--line);border-radius:20px;padding:4px 11px;cursor:pointer;font-size:11.5px;color:var(--t2)}.qc:hover,.qc.on{border-color:var(--ac);color:var(--t1)}
.stepper{display:flex;gap:6px;direction:ltr;align-items:stretch}.stepper .in{text-align:center;min-width:0;flex:1;font-family:'JetBrains Mono',monospace}
.sbtn{width:40px;flex:none;background:var(--s3);border:1px solid var(--line);border-radius:10px;cursor:pointer;font-size:18px;line-height:1;display:flex;align-items:center;justify-content:center}.sbtn:hover{border-color:var(--ac)}.sbtn:active{background:var(--ac);color:#1a0f0a}
.drop{border:1.5px dashed #3a3c45;border-radius:var(--r);padding:20px 12px;text-align:center;cursor:pointer;color:var(--t2);font-size:12px}
.drop:hover,.drop.drag{border-color:var(--ac)}.drop b{display:block;color:var(--t1);margin-bottom:4px}
.btn{border:none;border-radius:11px;padding:10px 14px;font-weight:500;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:8px;width:100%;margin-top:8px}
.btn:disabled{opacity:.4;cursor:not-allowed}.b1{background:var(--ac);color:#1a0f0a;font-weight:600}.b2{background:var(--s3);border:1px solid var(--line)}
.b3{background:var(--t1);color:#15161b;text-decoration:none;font-weight:600}
.switch{display:flex;align-items:center;justify-content:space-between;padding:6px 0;font-size:13px}
.tg{width:40px;height:22px;border-radius:20px;background:var(--s3);position:relative;cursor:pointer;flex-shrink:0}
.tg::after{content:'';position:absolute;top:3px;right:3px;width:16px;height:16px;border-radius:50%;background:var(--t2);transition:.2s}
.tg.on{background:var(--ac)}.tg.on::after{right:21px;background:#fff}
input[type=range]{width:100%;accent-color:var(--ac)}
.lib{display:flex;flex-direction:column;gap:6px;margin-top:10px}
.mi{display:flex;align-items:center;gap:8px;background:var(--s2);border:1px solid var(--line);border-radius:10px;padding:8px 10px;font-size:12px}
.mi.on{border-color:var(--ac)}.mi .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mi button{background:var(--s3);border:none;border-radius:7px;padding:4px 9px;cursor:pointer;font-size:11px}.mi .del{color:var(--err)}
.transcript{max-height:220px;overflow-y:auto;background:var(--s2);border-radius:10px;padding:8px 12px;font-size:13px;line-height:1.9;display:none;margin-top:10px}
.seg{padding:4px 0;border-bottom:1px solid var(--line)}.seg time{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--ac2);margin-left:8px}
.hint{font-size:11px;color:var(--t3);margin-top:8px;line-height:1.7}.hint code{color:var(--ac2);font-family:'JetBrains Mono',monospace}
.sep{height:1px;background:var(--line);margin:12px 0 2px}
.tpls{display:flex;gap:6px;overflow-x:auto;padding:10px 12px;border-bottom:1px solid var(--line);flex-shrink:0;align-items:center}
.tpl{flex-shrink:0;background:var(--s1);border:1px solid var(--line);border-radius:20px;padding:6px 14px;font-size:12px;cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;gap:6px}.tpl:hover{border-color:var(--ac)}.tpl .ic{width:14px;height:14px}
.tpl.act{border-color:var(--ac2);color:var(--ac2);margin-right:auto}
textarea.code{flex:1;background:#0d0e11;border:none;outline:none;resize:none;padding:16px;font-family:'JetBrains Mono',monospace;font-size:13px;line-height:1.65;color:#ddd6cb;white-space:pre;overflow:auto;tab-size:2;direction:ltr}
.edbar{height:28px;flex-shrink:0;display:flex;align-items:center;justify-content:space-between;padding:0 14px;border-top:1px solid var(--line);font-family:'JetBrains Mono',monospace;font-size:10.5px;color:var(--t3);direction:ltr}
.stage{flex:1;min-height:240px;display:flex;align-items:center;justify-content:center;padding:16px;position:relative;background:#0d0e11}
.stage video,.stage img{max-width:100%;max-height:100%;border-radius:12px;display:none;background:#000}
.empty{color:var(--t3);font-size:13px;text-align:center}
.ov{position:absolute;inset:0;background:rgba(13,14,17,.94);display:none;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:24px;z-index:5}
.pct{font-family:'JetBrains Mono',monospace;font-size:32px}.bar{width:100%;max-width:300px;height:3px;background:var(--s3);border-radius:9px;overflow:hidden}
.fill{height:100%;width:0;background:var(--ac);transition:width .4s}.ov .d{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--t2);text-align:center}
.actions{display:flex;gap:10px;padding:4px 16px 0;border-top:1px solid var(--line)}.actions .btn{margin-top:10px}
.timebox{padding:10px 16px 12px}
.tb-h{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--t2);margin-bottom:6px;gap:8px}.tb-h span:last-child{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--ac2);direction:ltr}
.timebox .stepper{margin-top:8px}.timebox .stepper .btn{margin-top:0;width:auto;flex:1.4;padding:8px 12px}
.log{height:160px;flex-shrink:0;overflow-y:auto;padding:10px 14px;font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.7;border-top:1px solid var(--line);direction:ltr;text-align:left;white-space:pre-wrap;word-break:break-word;background:var(--s1)}
.log .e{color:var(--err)}.log .s{color:var(--ok)}.log .i{color:var(--t2)}.log .h{color:var(--ac2)}
.nav{display:none}
@media (max-width:900px){
 .app{display:block;position:relative}.panel{position:absolute;inset:0;border:none;display:none}.panel.act{display:flex}
 .top{padding:0 12px;height:54px}.iconbtn span{display:none}.iconbtn{padding:7px 9px}.brand small{display:none}
 .nav{display:flex;flex-shrink:0;height:calc(62px + env(safe-area-inset-bottom));padding-bottom:env(safe-area-inset-bottom);border-top:1px solid var(--line);background:var(--s1)}
 .nav button{flex:1;background:none;border:none;color:var(--t3);cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;font-size:11px;position:relative;transition:color .2s}
 .nav button .ic{width:22px;height:22px}
 .nav button.on{color:var(--ac)}.nav button.on::before{content:'';position:absolute;top:0;left:28%;right:28%;height:2px;background:var(--ac);border-radius:0 0 3px 3px}
 .in,.btn{font-size:16px}.log{height:130px}}

.top{height:60px;background:#fff;border-bottom:1px solid var(--line);box-shadow:0 2px 14px rgba(60,30,10,.05);padding:0 20px;position:relative;z-index:30}
.brand{flex:1;min-width:0;font-size:16px;font-weight:700;color:var(--t1);gap:10px}.brand img{width:34px;height:34px;flex-shrink:0}.brand .bn{overflow:hidden;text-overflow:ellipsis;background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
.brand small{color:var(--ac);border-color:rgba(232,67,31,.3);background:rgba(232,67,31,.06);font-weight:600}
.tright{gap:10px}.status{background:#fff;border-radius:22px;padding:6px 14px;color:var(--t2);font-weight:500}
.iconbtn{background:#fff;color:var(--t1);border-radius:22px;padding:7px 14px;font-weight:500}.iconbtn:hover{border-color:var(--ac);color:var(--ac)}
.menuwrap{position:relative}.iconbtn.acc{background:var(--s2);max-width:190px}.iconbtn.acc .nm2{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.menu{position:absolute;top:calc(100% + 8px);left:0;min-width:230px;background:#fff;border:1px solid var(--line);border-radius:16px;box-shadow:0 18px 50px rgba(80,35,10,.18);padding:8px;display:none;z-index:60}.menu.on{display:block}
.menu .mhead{padding:10px 12px 12px;border-bottom:1px solid var(--line);margin-bottom:6px;font-size:12.5px;color:var(--t2);line-height:1.8;white-space:normal;display:block!important;border-radius:0;background:none;border-left:0;border-right:0;border-top:0}
.menu .mi2{display:flex;align-items:center;gap:10px;width:100%;padding:10px 12px;border:none;background:none;border-radius:10px;cursor:pointer;color:var(--t1);font-size:13.5px;text-decoration:none;text-align:right}
.menu .mi2:hover{background:var(--s2)}.menu .mi2.dg{color:var(--err)}.menu .mi2 .ic{width:17px;height:17px;color:var(--ac)}
.ph{background:var(--s2);color:var(--t1);font-weight:600;border-bottom:1px solid var(--line)}
.card{box-shadow:var(--sh)}.card h3{font-size:14px}.card h3 b{background:var(--grad);color:#fff;border-radius:7px;padding:2px 7px;font-size:11px}.card h3 .ic{color:var(--ac)}
.b1{background:var(--grad);color:#fff;font-weight:600;box-shadow:0 6px 18px rgba(232,67,31,.28)}.b1:hover:not(:disabled){filter:brightness(1.06)}
.b2{background:#fff;color:var(--t1)}.b2:hover:not(:disabled){border-color:var(--ac);color:var(--ac)}
.b3{background:var(--t1);color:#fff}
.in{background:#fff}.in:focus{box-shadow:0 0 0 3px rgba(232,67,31,.14)}
.chip{background:#fff}.chip.on{background:rgba(232,67,31,.07);color:var(--ac2);font-weight:600}
.qc{background:#fff}.qc:hover,.qc.on{color:var(--ac2);background:rgba(232,67,31,.07)}
.tpl{background:#fff}.tpl:hover{color:var(--ac)}.tpl.act{border-color:var(--ac);color:var(--ac2);background:rgba(232,67,31,.06)}
.drop{border-color:#d8c9bd;background:var(--s2)}.drop:hover,.drop.drag{background:rgba(232,67,31,.05)}
.mi{background:#fff}.mi button{background:var(--s2)}
.sbtn{background:#fff}.tg{background:#d9cfc6}.tg::after{background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.25)}.tg.on{background:var(--ac)}
.transcript{background:var(--s2)}.hint code{color:var(--ac2)}.seg time{color:var(--ac2)}
textarea.code{background:#fffdfb;color:#3b2a22}.edbar{background:#fff}
.stage{background:#f0e8e0}.stage video,.stage img{box-shadow:0 14px 40px rgba(60,30,10,.22)}
.ov{background:rgba(255,250,246,.96)}.fill{background:var(--grad)}.bar{background:var(--s3)}
.actions,.timebox{background:#fff}.actions{position:relative;z-index:2;padding-bottom:8px}.log{background:#fffdfb;color:#4a3a31}.log .i{color:var(--t2)}.log .h{color:var(--ac2)}.log .s{color:var(--ok)}
.nav{background:#fff}.nav button.on{color:var(--ac)}
.mdl{position:fixed;inset:0;background:rgba(36,26,22,.5);display:none;align-items:center;justify-content:center;z-index:90;padding:16px}.mdl.on{display:flex}
.mdl .bx{background:#fff;border-radius:20px;max-width:460px;width:100%;padding:22px;box-shadow:0 30px 80px rgba(80,35,10,.3);max-height:92vh;overflow-y:auto}
.mdl h2{font-size:16px;margin-bottom:6px}.mdl .sub{color:var(--t2);font-size:12px;line-height:1.8;margin-bottom:10px}.mdl .kr{margin-top:12px}
.mdl .kr label{display:flex;justify-content:space-between;font-size:12px;color:var(--t2);margin-bottom:5px}.mdl .kr .st{font-size:11px}
@media (max-width:900px){.top{padding:0 12px;height:56px}.brand{font-size:15px}.brand img{width:30px;height:30px}.status #stxt{display:none}.status{padding:8px}.iconbtn.acc .nm2{display:none}.iconbtn.acc{padding:8px 10px}.menu{left:-6px;min-width:215px}}
</style></head><body>
<div class="top"><div class="brand"><img src="/icon.svg" alt=""><span class="bn">SA Motion Studio</span></div>
<div class="tright"><div class="status"><span class="dot" id="dot"></span><span id="stxt">جاهز</span></div>
<div class="menuwrap"><button class="iconbtn acc" id="menuBtn" type="button" aria-label="القائمة"><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/></svg><span class="nm2" id="acctN">حسابي</span><svg class="ic" viewBox="0 0 24 24" style="width:14px;height:14px"><path d="M6 9l6 6 6-6"/></svg></button>
<div class="menu" id="menu"><div class="mhead" id="acct"></div>
<button class="mi2" id="keysBtn" type="button"><svg class="ic" viewBox="0 0 24 24"><circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3"/></svg>مفاتيحي الخاصة (API)</button>
<button class="mi2" id="diagBtn" type="button"><svg class="ic" viewBox="0 0 24 24"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg>فحص النظام</button>
<button class="mi2" id="cleanBtn" type="button"><svg class="ic" viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>تنظيف الملفات المؤقتة</button>
<a class="mi2" id="adminBtn" href="/admin" style="display:none"><svg class="ic" viewBox="0 0 24 24"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/></svg>لوحة الإدارة</a>
<a class="mi2 dg" href="/logout"><svg class="ic" viewBox="0 0 24 24"><path d="M9 4H5v16h4M16 8l4 4-4 4M20 12H9"/></svg>تسجيل الخروج</a></div></div></div></div>
<div class="mdl" id="keysMdl"><div class="bx"><h2>🔑 مفاتيحي الخاصة</h2><div class="sub">أضف مفاتيحك الشخصية لتُستخدم بدل مفاتيح الموقع في حسابك فقط. تُحفظ مشفّرة ولا تظهر لأحد.</div>
<div class="kr"><label><span>Gemini — صوت التعليق (TTS)</span><span class="st" id="kgm_st"></span></label><input class="in" id="kgm" dir="ltr" type="password" autocomplete="off" placeholder="AIza..."></div>
<div class="hint" style="margin:6px 0 8px;line-height:1.9">مفتاح Gemini API من Google AI Studio. يولّد التعليق الصوتي بأصوات كثيرة ويقرأ العربية بحسب سياق النص.</div>
<div class="kr" style="margin-top:8px"><label><span>Freesound — المؤثرات والموسيقى</span><span class="st" id="kf_st"></span></label><input class="in" id="kf" dir="ltr" type="password" autocomplete="off" placeholder="الصق API Key"></div>
<details class="kr"><summary style="cursor:pointer;color:var(--t3);font-size:12px">مفاتيح اختيارية</summary>
<label style="margin-top:8px"><span>Groq (تفريغ + صوت عربي)</span><span class="st" id="kg_st"></span></label><input class="in" id="kg" dir="ltr" type="password" autocomplete="off" placeholder="gsk_...">
<label style="margin-top:8px"><span>OpenAI أو أي خدمة متوافقة — المفتاح</span><span class="st" id="ko_st"></span></label><input class="in" id="ko" dir="ltr" type="password" autocomplete="off" placeholder="sk-...">
<input class="in" id="kob" dir="ltr" autocomplete="off" placeholder="عنوان الخدمة (اختياري) https://api.openai.com/v1" style="margin-top:6px">
<input class="in" id="kom" dir="ltr" autocomplete="off" placeholder="الموديل (اختياري) gpt-4o-mini-tts" style="margin-top:6px"></details>
<div class="hint" id="kmsg"></div>
<div class="row" style="margin-top:12px"><button class="btn b1" id="kSave" type="button" style="margin:0">حفظ</button><button class="btn b2" id="kTest" type="button" style="margin:0">اختبار المحفوظ</button><button class="btn b2" id="kClose" type="button" style="margin:0">إغلاق</button></div></div></div>
<div class="app">
<div class="panel act" id="p-setup"><div class="ph"><svg class="ic" viewBox="0 0 24 24"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg>الإعداد والوسائط</div><div class="scroll">
 <div class="card"><h3><b>01</b>المقاس والتوقيت</h3>
  <div class="chips" id="presets"><div class="chip on" data-w="1080" data-h="1920">ريلز 9:16</div><div class="chip" data-w="1920" data-h="1080">يوتيوب 16:9</div>
  <div class="chip" data-w="1080" data-h="1080">مربع 1:1</div><div class="chip" data-w="1080" data-h="1350">منشور 4:5</div></div>
  <div class="row"><div><label class="l">العرض</label><input class="in" id="w" inputmode="numeric" value="1080" dir="ltr"></div><div><label class="l">الارتفاع</label><input class="in" id="h" inputmode="numeric" value="1920" dir="ltr"></div></div>
  <div class="row"><div><label class="l">FPS</label><select class="in" id="fps"><option>24</option><option selected>30</option><option>60</option></select></div>
  <div><label class="l">الجودة</label><select class="in" id="q"><option value="23|veryfast">سريع (معاينة)</option><option value="18|medium" selected>عالية</option><option value="15|slow">ممتازة</option></select></div></div>
  <label class="l">المدة (بالثواني) <span id="durSec" style="font-family:'JetBrains Mono',monospace;direction:ltr"></span></label>
  <div class="stepper"><button class="sbtn" type="button" data-step="-1" aria-label="أنقص ثانية">−</button><input class="in" id="dur" inputmode="decimal" autocomplete="off" value="10" dir="ltr"><button class="sbtn" type="button" data-step="1" aria-label="زد ثانية">+</button></div>
  <div class="qk" id="qk"><span class="qc" data-v="5">5ث</span><span class="qc" data-v="10">10ث</span><span class="qc" data-v="15">15ث</span><span class="qc" data-v="30">30ث</span><span class="qc" data-v="60">60ث</span><span class="qc" data-v="media" id="qMedia" style="display:none">طول الملف</span></div>
  <div class="hint" id="durHint">بدون GPU: 30fps أسرع بمرتين من 60fps.</div></div>
 <div class="card"><h3><b>02</b>مكتبة الوسائط</h3>
  <div class="drop" id="drop"><b>اضغط أو اسحب الملفات (يمكن رفع فيديو + صوت معاً)</b>MP3 · WAV · M4A · MP4 · MOV · WEBM</div><input type="file" id="file" accept="audio/*,video/*" multiple hidden>
  <div class="hint" id="minfo"></div><div class="lib" id="lib"></div>
  <div class="switch">دمج صوت الملف تلقائياً<div class="tg on" id="voiceTg"></div></div>
  <div class="switch">رندر سريع موزّع<div class="tg on" id="cloudTg"></div></div>
  <div class="row"><select class="in" id="lang"><option value="">كشف تلقائي</option><option value="ar">عربي</option><option value="en">English</option></select>
  <select class="in" id="model"><option value="small">سريع</option><option value="medium" selected>دقيق</option><option value="large-v3">الأدق</option></select></div>
  <label class="l">كلمات في السطر <span id="mwv">3</span></label><input type="range" id="mw" min="1" max="8" value="3">
  <button class="btn b1" id="trBtn" type="button" disabled>تفريغ الصوت ومزامنة الكلمات</button>
  <div class="transcript" id="trBox"></div>
  <button class="btn b2" id="srtBtn" type="button" style="display:none">تحميل SRT</button>
  <div class="sep"></div>
  <label class="l">حساسية الصمت <span id="thv">-35dB</span></label><input type="range" id="th" min="-50" max="-20" value="-35">
  <label class="l">أقل مدة صمت للقص <span id="msv">0.45ث</span></label><input type="range" id="msil" min="0.15" max="2" step="0.05" value="0.45">
  <button class="btn b2" id="cutBtn" type="button" disabled>قص الصمت (Jump Cut)</button>
  <div class="hint">كلما رفعت الحساسية (نحو -20dB) قُصّ صمت أكثر. بعد القص أعد تفريغ الصوت.</div></div>
 <div class="card" id="audioCard"><h3><b>03</b>الصوت والمؤثرات</h3>
  <div class="switch" id="sfxRow">مؤثرات صوتية<div class="tg on" id="sfxTg"></div></div>
  <div class="switch" id="musicRow">موسيقى خلفية<div class="tg" id="musicTg"></div></div>
  <div id="musicOpts" style="display:none"><label class="l">نمط الموسيقى</label><select class="in" id="musicStyle"><option value="chill">هادئ</option><option value="upbeat">حماسي</option><option value="cinematic">سينمائي</option><option value="lofi">لو-فاي</option></select></div>
  <div class="hint">المزامنة ذكية: اكتب في الكود مؤثراً عند ثانية أو كلمة محددة وسيُوضع بدقة (مثال أدناه). يمكنك أيضاً كتابة <code>export const SFX = [{ t: 1.2, kind: "pop" }]</code> في الكود للتحكم اليدوي. الأنواع: whoosh · pop · impact · rise · ding · typing · click · bass · glitch · shine · tick</div></div>
</div></div>
<div class="panel" id="p-code"><div class="ph"><svg class="ic" viewBox="0 0 24 24"><path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/></svg>Motion.tsx</div>
 <div class="tpls"><div class="tpl" data-t="showcase">عرض بانتقالات</div><div class="tpl" data-t="captions">ترجمة تيك توك</div><div class="tpl" data-t="videoedit">مونتاج احترافي</div>
 <div class="tpl act" id="checkBtn"><svg class="ic" viewBox="0 0 24 24"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/></svg>فحص وإصلاح</div></div>
 <textarea class="code" id="code" spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off"></textarea>
 <div class="edbar"><span id="pos">Ln 1</span><span id="saved"></span><span>Ctrl+S · Ctrl+Enter render</span></div></div>
<div class="panel" id="p-out"><div class="ph"><svg class="ic" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M10 9l5 3-5 3z"/></svg>المعاينة والتصدير</div>
 <div class="stage"><div class="empty" id="empty">سيظهر الفيديو هنا بعد الرندر</div><video id="vid" controls playsinline></video><img id="still" alt="">
  <div class="ov" id="ov"><div class="pct" id="ovP">0%</div><div class="bar"><div class="fill" id="ovF"></div></div><div id="ovT">جاري التحضير</div><div class="d" id="ovD"></div>
  <button class="btn b2" id="cancelBtn" type="button" style="width:auto">إلغاء</button></div></div>
 <div class="actions"><button class="btn b1" id="renderBtn" type="button"><svg class="ic" viewBox="0 0 24 24"><path d="M7 4l13 8-13 8z"/></svg>رندر الفيديو</button><a class="btn b3" id="dl" style="display:none"><svg class="ic" viewBox="0 0 24 24"><path d="M12 4v11M7 11l5 5 5-5M5 20h14"/></svg>تحميل MP4</a></div>
 <div class="timebox"><div class="tb-h"><span>لقطة عند ثانية محددة</span><span id="stillInfo">—</span></div>
  <input type="range" id="stillR" min="0" max="10" step="0.01" value="1">
  <div class="stepper"><button class="sbtn" type="button" id="stPrev" aria-label="إطار سابق">‹</button><input class="in" id="stillT" inputmode="decimal" autocomplete="off" value="1" dir="ltr"><button class="sbtn" type="button" id="stNext" aria-label="إطار تالي">›</button>
  <button class="btn b2" id="stillBtn" type="button"><svg class="ic" viewBox="0 0 24 24"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>لقطة</button></div></div>
 <div class="log" id="log"></div></div>
</div>
<div class="nav" id="nav">
 <button type="button" data-p="setup" class="on"><svg class="ic" viewBox="0 0 24 24"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg>الإعداد</button>
 <button type="button" data-p="code"><svg class="ic" viewBox="0 0 24 24"><path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/></svg>الكود</button>
 <button type="button" data-p="out"><svg class="ic" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M10 9l5 3-5 3z"/></svg>المعاينة</button>
</div>
<script>
const $=id=>document.getElementById(id);
const S={media:null,sel:[],words:[],segments:[],job:null,gpu:null};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const clamp=(x,a,b)=>Math.min(b,Math.max(a,x));
const lsGet=k=>{try{return localStorage.getItem(k)}catch(e){return null}};
const lsSet=(k,v)=>{try{localStorage.setItem(k,v)}catch(e){}};
function num(v,d){if(v==null)return d;let s=String(v).trim().replace(/[\u0660-\u0669]/g,c=>c.charCodeAt(0)-0x660).replace(/[\u06F0-\u06F9]/g,c=>c.charCodeAt(0)-0x6F0).replace(/[\u066B\u066C,\u060C]/g,'.').replace(/[^\d.\-]/g,'');
 const p=s.split('.');if(p.length>2)s=p[0]+'.'+p.slice(1).join('');const n=parseFloat(s);return isFinite(n)?n:d}
const fmtT=t=>{const m=Math.floor(t/60),s=t-m*60;return String(m).padStart(2,'0')+':'+s.toFixed(2).padStart(5,'0')};
function log(m,t='i'){const d=document.createElement('div');d.className=t;d.textContent=`[${new Date().toLocaleTimeString('en-GB')}] ${m}`;$('log').appendChild(d);while($('log').childNodes.length>400)$('log').removeChild($('log').firstChild);$('log').scrollTop=1e9}
function status(t,b){$('stxt').textContent=t;$('dot').style.background=b?'var(--warn)':'var(--ok)';$('dot').classList.toggle('busy',!!b)}
function go(p){if(innerWidth>900)return;document.querySelectorAll('.panel').forEach(x=>x.classList.toggle('act',x.id==='p-'+p));document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('on',b.dataset.p===p))}
document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>go(b.dataset.p));
async function api(u,opt){let r;try{r=await fetch(u,opt)}catch(e){throw new Error('تعذّر الاتصال بالخادم — تأكد أن الخادم ما زال يعمل')}
 if(r.status===401){const j401=await r.json().catch(()=>({}));location.href='/login'+(/جهاز آخر/.test(j401.error||'')?'?e=kicked':'');throw new Error('انتهت الجلسة')}
 if(!r.ok&&/json/.test(r.headers.get('content-type')||'')){let j={};try{j=await r.clone().json()}catch(e){}if(j.error)throw new Error(j.error)}
 if(!r.ok){let t='';try{t=await r.text()}catch(e){}if(/^\s*<(!doctype|html)/i.test(t))t='خطأ داخلي في الخادم (HTTP '+r.status+')';throw new Error((t||('HTTP '+r.status)).slice(0,4000))}return r}
const postJ=(u,b)=>api(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
function waitJob(id,onp){return new Promise((ok,no)=>{let f=0;const tick=async()=>{
 try{const r=await fetch('/api/job/'+id);if(r.status===401){location.href='/login';return}const j=await r.json();f=0;
  if(j.status==='done'){ok(j.result);return}
  if(j.status==='error'){const e=new Error(j.error||'خطأ');e.logs=j.logs;no(e);return}
  onp&&onp(j)}catch(e){if(++f>60){no(new Error('انقطع الاتصال بالخادم'));return}}
 setTimeout(tick,1000)};tick()})}
const CFG_IDS=['w','h','fps','q','dur','lang','model','mw','th','msil','stillT','musicStyle'];
function saveCfg(){const c={};CFG_IDS.forEach(i=>c[i]=$(i).value);c.voice=$('voiceTg').classList.contains('on');c.cloud=$('cloudTg').classList.contains('on');c.sfx=$('sfxTg').classList.contains('on');c.music=$('musicTg').classList.contains('on');lsSet('sa_cfg',JSON.stringify(c));pushState()}
function loadCfg(){try{const c=JSON.parse(lsGet('sa_cfg')||'{}');CFG_IDS.forEach(i=>{if(c[i]!=null&&c[i]!=='')$(i).value=c[i]});
 if(c.voice===false)$('voiceTg').classList.remove('on');if(c.cloud===false)$('cloudTg').classList.remove('on');if(c.sfx===false)$('sfxTg').classList.remove('on');if(c.music)$('musicTg').classList.add('on');$('musicOpts').style.display=$('musicTg').classList.contains('on')?'block':'none'}catch(e){}}
function getFps(){return clamp(Math.round(num($('fps').value,30)),1,120)}
function getDur(){return clamp(num($('dur').value,10),0.5,900)}
function totalFrames(){return Math.max(1,Math.round(getDur()*getFps()))}
function syncTime(fromStillText){
 const fps=getFps(),dur=getDur(),frames=totalFrames(),mx=(frames-1)/fps;
 $('durSec').textContent=fmtT(dur);
 $('durHint').textContent=`${frames} إطار · ${dur.toFixed(2)}ث @${fps}fps`+(S.gpu===false?' · بدون GPU: 30fps أسرع بمرتين من 60fps.':'');
 const r=$('stillR');r.max=String(mx);r.step=String(1/fps);
 const t=clamp(num($('stillT').value,0),0,mx);
 if(!fromStillText&&num($('stillT').value,0)!==t)$('stillT').value=String(Math.round(t*100)/100);
 r.value=String(t);$('stillInfo').textContent=`إطار ${Math.round(t*fps)} / ${frames-1} · ${fmtT(t)}`;
 document.querySelectorAll('#qk .qc').forEach(q=>q.classList.toggle('on',q.dataset.v!=='media'&&Math.abs(+q.dataset.v-dur)<0.005||(q.dataset.v==='media'&&S.media&&Math.abs(S.media.duration-dur)<0.01)));
}
function setDur(v){$('dur').value=String(Math.round(clamp(v,0.5,900)*100)/100);syncTime();saveCfg()}
$('dur').addEventListener('input',()=>{syncTime();saveCfg()});
$('dur').addEventListener('change',()=>setDur(getDur()));
$('dur').addEventListener('keydown',e=>{if(e.key==='ArrowUp'){e.preventDefault();setDur(getDur()+1)}else if(e.key==='ArrowDown'){e.preventDefault();setDur(getDur()-1)}});
document.querySelectorAll('.stepper [data-step]').forEach(b=>b.onclick=()=>setDur(getDur()+(+b.dataset.step)));
document.querySelectorAll('#qk .qc').forEach(q=>q.onclick=()=>{if(q.dataset.v==='media'){if(S.media)setDur(S.media.duration)}else setDur(+q.dataset.v)});
$('fps').onchange=()=>{syncTime();saveCfg()};
function setStill(t){const fps=getFps(),mx=(totalFrames()-1)/fps;$('stillT').value=String(Math.round(clamp(t,0,mx)*100)/100);syncTime();saveCfg()}
$('stillR').addEventListener('input',()=>{$('stillT').value=String(Math.round(+$('stillR').value*100)/100);syncTime(true);saveCfg()});
$('stillT').addEventListener('input',()=>{syncTime(true);saveCfg()});
$('stillT').addEventListener('change',()=>setStill(num($('stillT').value,0)));
$('stillT').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();setStill(num($('stillT').value,0));$('stillBtn').click()}});
$('stPrev').onclick=()=>setStill(num($('stillT').value,0)-1/getFps());
$('stNext').onclick=()=>setStill(num($('stillT').value,0)+1/getFps());
function markPreset(){document.querySelectorAll('#presets .chip').forEach(c=>c.classList.toggle('on',+c.dataset.w===num($('w').value,0)&&+c.dataset.h===num($('h').value,0)))}
document.querySelectorAll('#presets .chip').forEach(c=>c.onclick=()=>{$('w').value=c.dataset.w;$('h').value=c.dataset.h;markPreset();saveCfg()});
['w','h'].forEach(i=>$(i).addEventListener('input',()=>{markPreset();saveCfg()}));
$('q').onchange=saveCfg;$('lang').onchange=saveCfg;$('model').onchange=saveCfg;
['sfxTg','musicTg','voiceTg','cloudTg'].forEach(id=>$(id).onclick=()=>{const f={sfxTg:'sfx',musicTg:'music',cloudTg:'cloud'}[id];if(f&&!hasF(f)){log('هذه الميزة غير مفعّلة في اشتراكك','e');return}$(id).classList.toggle('on');$('musicOpts').style.display=$('musicTg').classList.contains('on')?'block':'none';saveCfg()});
$('musicStyle').onchange=saveCfg;
$('th').oninput=()=>{$('thv').textContent=$('th').value+'dB';saveCfg()};
$('msil').oninput=()=>{$('msv').textContent=(+$('msil').value).toFixed(2)+'ث';saveCfg()};
let rgT;$('mw').oninput=()=>{$('mwv').textContent=$('mw').value;saveCfg();clearTimeout(rgT);rgT=setTimeout(regroup,350)};
const code=$('code');
let psT;function pushState(){clearTimeout(psT);psT=setTimeout(()=>{try{fetch('/api/state',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:code.value,cfg:JSON.parse(lsGet('sa_cfg')||'{}')})}).catch(()=>{})}catch(e){}},3000)}
function save(){lsSet('code',code.value);pushState();$('saved').textContent='saved';setTimeout(()=>$('saved').textContent='',1200)}
let st;code.addEventListener('input',()=>{clearTimeout(st);st=setTimeout(save,700)});
const updPos=()=>$('pos').textContent='Ln '+code.value.slice(0,code.selectionStart).split('\n').length;
code.addEventListener('keyup',updPos);code.addEventListener('click',updPos);
code.addEventListener('keydown',e=>{
 if((e.ctrlKey||e.metaKey)&&e.key==='s'){e.preventDefault();save()}
 else if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();$('renderBtn').click()}
 else if(e.key==='Tab'){e.preventDefault();code.setRangeText('  ',code.selectionStart,code.selectionEnd,'end')}});
async function loadTpl(n){try{const t=await (await api('/api/template/'+n)).text();if(!t.trim()||/^\s*<(!doctype|html)/i.test(t))throw new Error('قالب غير صالح');code.value=t;save();log('تم تحميل القالب: '+n,'h')}catch(e){log('فشل تحميل القالب: '+e.message,'e')}}
document.querySelectorAll('.tpl[data-t]').forEach(t=>t.onclick=()=>{if(code.value.trim()&&!confirm('استبدال الكود الحالي؟'))return;loadTpl(t.dataset.t)});
$('checkBtn').onclick=async()=>{if(!code.value.trim())return log('الكود فارغ','e');status('فحص',1);
 try{const r=await (await postJ('/api/check',{code:code.value})).json();
  if(r.notes&&r.notes.length){code.value=r.code;save();r.notes.forEach(n=>log('إصلاح: '+n,'h'))}
  if(r.ok)log('الكود سليم ✓','s');else log(r.error||'الكود يحتوي على أخطاء','e')}catch(e){log('فشل الفحص: '+e.message,'e')}status('جاهز')};
(async function initCode(){let sv=lsGet('code');
 if(!(sv&&sv.trim()&&/export/.test(sv))){try{const st=await (await fetch('/api/state')).json();if(st.code&&/export/.test(st.code)){sv=st.code;if(st.cfg&&Object.keys(st.cfg).length){lsSet('sa_cfg',JSON.stringify(st.cfg));loadCfg();syncTime()}}}catch(e){}}
 if(sv&&sv.trim()&&!/^\s*<(!doctype|html)/i.test(sv)&&/export/.test(sv))code.value=sv;else loadTpl('showcase')})();
async function refreshLib(){let L=[];try{L=(await (await api('/api/media')).json()).items}catch(e){log('تعذّر جلب المكتبة: '+e.message,'e')}
 $('lib').innerHTML=L.map(m=>{const k=S.sel.findIndex(x=>x.file===m.file);return `<div class="mi ${k>=0?'on':''}"><span>${m.type==='video'?'🎬':'🎵'}</span><span class="nm" title="${esc(m.original)}">${esc(m.original)} · ${m.duration.toFixed(1)}ث</span><button type="button" data-u="${esc(m.file)}">${k>=0?'✓ '+(k+1)+' · إلغاء':'＋ استخدام'}</button><button type="button" class="del" data-d="${esc(m.file)}">حذف</button></div>`}).join('')||'<div class="hint">لا توجد ملفات</div>';
 S.sel=S.sel.map(x=>L.find(y=>y.file===x.file)||x);
 $('lib').querySelectorAll('[data-u]').forEach(b=>b.onclick=()=>toggleMedia(L.find(x=>x.file===b.dataset.u)));
 $('lib').querySelectorAll('[data-d]').forEach(b=>b.onclick=async()=>{if(!confirm('حذف الملف نهائياً؟'))return;
  try{await api('/api/media/'+encodeURIComponent(b.dataset.d),{method:'DELETE'})}catch(e){return log('فشل الحذف: '+e.message,'e')}
  S.sel=S.sel.filter(x=>x.file!==b.dataset.d);if(S.media&&S.media.file===b.dataset.d){S.media=null}applySel(false);
  log('تم الحذف','s');refreshLib()});
 return L}
function clearMedia(){S.sel=[];S.media=null;S.words=[];S.segments=[];lsSet('sa_media','');lsSet('sa_sel','[]');$('trBox').style.display='none';$('srtBtn').style.display='none';$('trBtn').disabled=true;$('cutBtn').disabled=true;$('minfo').textContent='';$('qMedia').style.display='none';syncTime()}
// الاختيار المتعدد: فيديو + صوت (أو أكثر من مقطع) يُرسلون كلهم للرندر — لا يُستبدل ملف بآخر
function toggleMedia(r){if(!r)return;const k=S.sel.findIndex(x=>x.file===r.file);
 if(k>=0)S.sel.splice(k,1);else{if(S.sel.length>=6)return log('الحد الأقصى 6 ملفات في المشروع الواحد','e');S.sel.push(r)}
 applySel(true)}
function addMedia(r){if(!r)return;if(!S.sel.some(x=>x.file===r.file)&&S.sel.length<6)S.sel.push(r);else S.sel=S.sel.map(x=>x.file===r.file?r:x);applySel(true)}
function replaceMedia(oldFile,r){S.sel=S.sel.map(x=>x.file===oldFile?r:x);applySel(true)}
function applySel(setDuration){
 const au=S.sel.find(x=>x.type==='audio'),vd=S.sel.find(x=>x.type==='video');
 const sp=au||vd||null;                 // مصدر الكلام (للتفريغ والمدة): الصوت المرفوع أولاً وإلا صوت الفيديو
 const changed=(S.media&&S.media.file)!==(sp&&sp.file);
 S.media=sp;lsSet('sa_media',sp?sp.file:'');lsSet('sa_sel',JSON.stringify(S.sel.map(x=>x.file)));
 if(changed||!sp){S.words=sp&&sp.words||[];S.segments=sp&&sp.segments||[]}
 if(!sp){$('trBox').style.display='none';$('srtBtn').style.display='none';$('trBtn').disabled=true;$('cutBtn').disabled=true;$('minfo').textContent='';$('qMedia').style.display='none';syncTime();refreshLib();return}
 const parts=S.sel.map((x,i)=>`${i+1}) ${x.type==='video'?'🎬':'🎵'} ${x.original} · ${x.duration.toFixed(1)}ث`);
 $('minfo').textContent=(S.sel.length>1?'المحدد معاً — ':'المحدد: ')+parts.join('  +  ')+(vd&&au?'  ← الصورة من الفيديو والصوت من الملف الصوتي':'');
 $('qMedia').style.display='inline-block';
 if(setDuration!==false)setDur(sp.duration);
 if(vd&&vd.width){$('w').value=vd.width;$('h').value=vd.height;markPreset();saveCfg()}
 $('trBtn').disabled=!sp.has_audio||!hasF('transcribe');$('cutBtn').disabled=!sp.has_audio||!hasF('cut');
 if(S.segments.length)showTr();else{$('trBox').style.display='none';$('srtBtn').style.display='none'}
 syncTime();refreshLib()}
function useMedia(r,setDuration){if(!r)return;addMedia(r)}
const drop=$('drop');drop.onclick=()=>$('file').click();
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,v=>{v.preventDefault();drop.classList.add('drag')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,v=>{v.preventDefault();drop.classList.remove('drag')}));
drop.addEventListener('drop',async e=>{for(const f of [...e.dataTransfer.files])await upload(f)});
$('file').onchange=async e=>{const fl=[...e.target.files];e.target.value='';for(const f of fl)await upload(f)};
async function upload(f){const CH=8*1024*1024,total=Math.max(1,Math.ceil(f.size/CH));const uid=Math.random().toString(36).slice(2,14)+Date.now().toString(36);
 status('رفع',1);let jid=null;
 try{for(let i=0;i<total;i++){const fd=new FormData();fd.append('uid',uid);fd.append('idx',i);fd.append('total',total);fd.append('size',CH);fd.append('name',f.name);fd.append('chunk',f.slice(i*CH,(i+1)*CH));
   let r,tries=0;while(true){try{r=await fetch('/api/upload',{method:'POST',body:fd});if(r.ok)break;if([401,403,429].includes(r.status)){const j=await r.json().catch(()=>({}));if(r.status===401)location.href='/login';throw {fatal:(j.error||await r.text().catch(()=>'')||'غير مسموح')}}}catch(e){if(e&&e.fatal)throw new Error(e.fatal)}if(++tries>4)throw new Error('فشل رفع الجزء '+(i+1)+' من '+total);await new Promise(z=>setTimeout(z,1500))}
   const j=await r.json();if(j.job_id)jid=j.job_id;$('minfo').textContent=`رفع ${Math.round((i+1)/total*100)}%`}
  if(!jid)throw new Error('لم يبدأ الخادم معالجة الملف');
  const r=await waitJob(jid,j=>$('minfo').textContent=`${j.stage||''} ${j.progress||0}%`);addMedia(r);log('تم الرفع وإضافته للمشروع: '+r.original,'s');
 }catch(e){log('فشل الرفع: '+e.message,'e');$('minfo').textContent='فشل الرفع'}status('جاهز')}
$('cutBtn').onclick=async()=>{if(!S.media)return;status('قص الصمت',1);$('cutBtn').disabled=true;
 try{const r=await postJ('/api/cut_silence',{file:S.media.file,th:num($('th').value,-35),min_sil:num($('msil').value,0.45)});
  const res=await waitJob((await r.json()).job_id,j=>$('cutBtn').textContent=`${j.stage} ${j.progress||0}%`);
  replaceMedia(S.media.file,res);log(`تم القص: ${res.removed.toFixed(1)}ث صمت حُذفت. فرّغ الصوت من جديد.`,'s')}catch(e){log('فشل القص: '+e.message,'e')}
 $('cutBtn').textContent='قص الصمت (Jump Cut)';$('cutBtn').disabled=!(S.media&&S.media.has_audio&&hasF('cut'));status('جاهز')};
async function regroup(){if(!S.words.length)return;try{S.segments=(await (await postJ('/api/segments',{words:S.words,max_words:+$('mw').value,file:S.media&&S.media.file})).json()).segments;showTr()}catch(e){log('فشل إعادة التقسيم: '+e.message,'e')}}
function showTr(){$('trBox').innerHTML=S.segments.map(s=>`<div class="seg"><time>${s.start.toFixed(2)}</time>${esc(s.text)}</div>`).join('');$('trBox').style.display='block';$('srtBtn').style.display=S.segments.length?'flex':'none'}
async function doTranscribe(){if(!S.media||!hasF('transcribe'))return;$('trBtn').disabled=true;status('تفريغ',1);
 try{const r=await postJ('/api/transcribe',{file:S.media.file,lang:$('lang').value,model:$('model').value,max_words:+$('mw').value});
  const res=await waitJob((await r.json()).job_id,p=>$('trBtn').textContent=`${p.stage||''} ${p.progress||0}%`);
  S.words=res.words;S.segments=res.segments;S.media.words=res.words;S.media.segments=res.segments;showTr();log(`تم التفريغ: ${res.words.length} كلمة · ${res.language} · ${res.device}`,'s')}
 catch(e){log('فشل التفريغ: '+e.message,'e')}$('trBtn').disabled=false;$('trBtn').textContent='إعادة التفريغ';status('جاهز')}
$('trBtn').onclick=doTranscribe;
$('srtBtn').onclick=()=>{const f=t=>{const ms=Math.max(0,Math.round(t*1000)),p=(n,l=2)=>String(n).padStart(l,'0');return `${p(Math.floor(ms/3600000))}:${p(Math.floor(ms%3600000/60000))}:${p(Math.floor(ms%60000/1000))},${p(ms%1000,3)}`};
 const txt=S.segments.map((s,i)=>`${i+1}\n${f(s.start)} --> ${f(s.end)}\n${s.text}\n`).join('\n');const a=document.createElement('a');
 a.href=URL.createObjectURL(new Blob(['\ufeff'+txt],{type:'text/plain;charset=utf-8'}));a.download='captions.srt';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),4000)};
function busy(on){$('renderBtn').disabled=on;$('stillBtn').disabled=on}
async function runJob(mode){if(S.job||S.starting)return;if(!code.value.trim())return log('الكود فارغ','e');save();
 if(mode==='video'&&!S.sel.length&&/mediaSrc|videoSrc|mediaUrl|segments|Captions|Kinetic|clips/.test(code.value)&&!confirm('لم تختر ملفاً (فيديو/صوت) بينما التصميم يعتمد عليه، وقد يخرج الفيديو أسود/فارغاً.\nهل تريد المتابعة؟'))return;
 if(mode==='video'&&S.media&&!S.segments.length&&hasF('transcribe')&&/segments|Captions|Kinetic|words/.test(code.value)){S.starting=true;busy(true);log('لا يوجد تفريغ للصوت — سأفرّغه تلقائياً قبل الرندر لتظهر الترجمة','h');try{await doTranscribe()}catch(e){}S.starting=false;busy(false)}
 const fps=getFps(),dur=getDur(),frames=totalFrames(),[crf,preset]=$('q').value.split('|');
 const w=clamp(Math.round(num($('w').value,1080)),64,4096),h=clamp(Math.round(num($('h').value,1920)),64,4096);
 const t=clamp(num($('stillT').value,0),0,(frames-1)/fps);
 const body={mode,time:t,code:code.value,config:{width:w,height:h,fps,frames,crf:+crf,preset},
  media:S.media,medias:S.sel,words:S.words,segments:S.segments,voice:$('voiceTg').classList.contains('on'),cloud:$('cloudTg').classList.contains('on'),
  sfx:{enabled:$('sfxTg').classList.contains('on')},music:{enabled:$('musicTg').classList.contains('on'),style:$('musicStyle').value}};
 S.starting=true;busy(true);$('ov').style.display='flex';$('ovF').style.width='0';$('ovP').textContent='0%';$('ovT').textContent='جاري التحضير';$('ovD').textContent='';$('cancelBtn').disabled=false;status(mode==='still'?'لقطة':'رندر',1);go('out');
 log(mode==='still'?`لقطة عند ${t.toFixed(2)}s (إطار ${Math.round(t*fps)})`:`رندر ${w}×${h} @${fps}fps · ${frames} إطار · ${dur.toFixed(2)}ث`,'h');const t0=Date.now();
 try{const r=await postJ('/api/render',body);const {job_id}=await r.json();S.job=job_id;S.starting=false;
  const res=await waitJob(job_id,j=>{const p=j.progress||0;$('ovT').textContent=j.stage||'';$('ovF').style.width=p+'%';$('ovP').textContent=p+'%';$('ovD').textContent=j.details||''});
  if(res.notes&&res.notes.length&&res.fixed_code){code.value=res.fixed_code;save();res.notes.forEach(n=>log('إصلاح تلقائي: '+n,'h'))}
  (res.warnings||[]).forEach(w=>log('تنبيه: '+w,'h'));
  if(mode==='still'){const im=$('still');im.src=res.url+'?t='+Date.now();im.style.display='block';$('vid').style.display='none';$('empty').style.display='none';log('اللقطة جاهزة','s')}
  else{const v=$('vid');v.src=res.url+'?t='+Date.now();v.addEventListener('loadeddata',()=>{if(v.paused&&v.currentTime<0.05)v.currentTime=Math.min(0.7,(v.duration||1)/3)},{once:true});v.style.display='block';$('still').style.display='none';$('empty').style.display='none';v.play().catch(()=>{});
   $('dl').href=res.url+'?dl=1';$('dl').style.display='flex';(res.sfx_used||[]).forEach(s=>log(`مؤثر ${s.kind} @${s.t.toFixed(2)}s ← ${s.source}`,'i'));if(res.audio){const a=res.audio;if(a.sfx)log(`🔊 مؤثرات: ${a.sfx.count} (${a.sfx.plan}) · Freesound ${a.sfx.freesound} · محلي ${a.sfx.local}`,'h');if(a.music)log(`🎵 موسيقى: ${a.music.source}${a.music.prompt?' · «'+a.music.prompt.slice(0,50)+'»':''}`,'h');if((a.auto_enabled||[]).length)log('⚙ فُعّلت تلقائياً من الكود: '+a.auto_enabled.join('، '),'i');if(a.voice&&a.voice.narration)log(`🎙 صوت مولّد من الكود (${a.voice.narration.provider}) · ${a.voice.narration.seconds}ث · ${a.voice.narration.words} كلمة — مدمج ومتزامن`,'s');else if(a.voice)log(a.voice.mixed?'🎤 صوت المقطع الأصلي: مدمج':'🎤 صوت المقطع لم يُدمج: '+a.voice.why,a.voice.mixed?'s':'h');if(a.sync)log('🎯 مزامنة ذكية: '+a.sync,'h');if(a.mean_db!=null)log(`مستوى الصوت النهائي ${a.mean_db} dB`,'i')}
   log(`اكتمل في ${((Date.now()-t0)/1000).toFixed(0)}ث · ${res.size_mb}MB`,'s')}
 }catch(e){log(e.message,'e');(e.logs||[]).forEach(l=>log('console: '+l,'e'));if(/MEDIA_MISSING/.test(e.message)){clearMedia();refreshLib()}}
 $('ov').style.display='none';busy(false);status('جاهز');S.job=null;S.starting=false}
$('renderBtn').onclick=()=>runJob('video');$('stillBtn').onclick=()=>runJob('still');
$('cancelBtn').onclick=()=>{if(S.job){$('cancelBtn').disabled=true;$('ovT').textContent='جارٍ الإلغاء...';fetch('/api/cancel/'+S.job,{method:'POST'}).catch(()=>{})}};
$('cleanBtn').onclick=async()=>{if(!confirm('تنظيف الملفات المؤقتة والفيديوهات المصدّرة القديمة؟'))return;
 const wipe=confirm('هل تريد أيضاً حذف الوسائط المرفوعة (المقاطع والصوت) من المكتبة؟\nموافق = احذفها · إلغاء = أبقِها');
 status('تنظيف',1);try{const r=await (await postJ('/api/cleanup',{media:wipe})).json();log(`تم التنظيف: تحرير ${r.freed_mb}MB · ${r.removed} عنصر`,'s');if(wipe)clearMedia();refreshLib()}catch(e){log('فشل التنظيف: '+e.message,'e')}status('جاهز')};
$('diagBtn').onclick=async()=>{status('فحص النظام',1);
 try{const d=await (await api('/api/diag')).json();
  
  log(`Remotion ${d.remotion} · React ${d.react}/${d.react_dom} · esbuild ${d.esbuild} · Chrome: ${d.chrome?'جاهز':'غير مثبت'}`,d.chrome?'s':'e');
  log(`Whisper: ${d.whisper?'جاهز':'غير مثبت'} · GPU: ${d.gpu?'نعم':'لا'} · CPU: ${d.cpus} · القرص الحر: ${d.disk_free_gb}GB · ملفات: ${d.media}`,d.whisper?'s':'e')}
 catch(e){log('فشل فحص النظام: '+e.message,'e')}status('جاهز')};

let ME=null;const hasF=f=>!ME||(ME.features||[]).includes(f);
function applyMe(){const m=ME;if(!m)return;const ac=$('acct');ac.style.display='inline-flex';
 const dl=m.role==='admin'?'مدير':(m.days_left==null?'':m.days_left+' يوم');ac.innerHTML='<b>'+esc(m.name||m.id)+'</b><br>'+esc(m.plan_label||'')+(dl?' · متبقي '+esc(String(dl)):'');$('acctN').textContent=(m.name||m.id);if(m.role!=='admin'&&m.days_left!=null&&m.days_left<=3)ac.style.color='var(--warn)';
 if(m.role==='admin'){$('adminBtn').style.display='inline-flex'}else{$('cleanBtn').style.display='none';$('diagBtn').style.display='none'}
 const q=m.quotas||{},u=m.usage||{};ac.title=`الباقة: ${m.plan_label} · رندر اليوم ${u.renders||0}/${q.renders_day} · التخزين ${m.storage_used_mb}/${q.storage_mb}MB`;
 [['sfxTg','sfx'],['musicTg','music'],['cloudTg','cloud']].forEach(([id,f])=>{if(!hasF(f)){$(id).classList.remove('on');$(id).parentElement.style.opacity='.4';$(id).title='غير مفعّل في اشتراكك'}});
 if(!hasF('upload')){$('drop').style.opacity='.4';$('drop').style.pointerEvents='none'}
 if(!hasF('transcribe')){$('trBtn').disabled=true;$('trBtn').title='غير مفعّل في اشتراكك'}if(!hasF('cut')){$('cutBtn').disabled=true;$('cutBtn').title='غير مفعّل في اشتراكك'}
 if(!hasF('render'))$('renderBtn').disabled=true;if(!hasF('still'))$('stillBtn').disabled=true;
 $('musicOpts').style.display=$('musicTg').classList.contains('on')?'block':'none'}
api('/api/me').then(r=>r.json()).then(m=>{ME=m;applyMe();if(m.status==='active'&&m.days_left!=null&&m.days_left<=3&&m.role!=='admin')log(`⏳ ينتهي اشتراكك خلال ${m.days_left} يوم — تواصل مع المدير للتجديد`,'h')}).catch(()=>{});

async function loadKeys(){try{const r=await (await api('/api/mykeys')).json();[['kgm','gemini_key','kgm_st'],['kf','freesound_key','kf_st'],['kg','groq_key','kg_st'],['ko','openai_key','ko_st']].forEach(([i,k,st])=>{$(i).value='';$(st).innerHTML=r.keys[k].set?'<span style="color:var(--ok)">مفتاحك محفوظ ••••'+esc(r.keys[k].tail)+'</span>':(r.platform[k.replace('_key','')]?'<span style="color:var(--t3)">يُستخدم مفتاح الموقع</span>':'<span style="color:var(--warn)">غير مضبوط</span>');$(i).placeholder=r.keys[k].set?'اتركه فارغاً للإبقاء · اكتب - للحذف':'الصق المفتاح'});const pl=r.plain||{};$('kob').value=pl.openai_base||'';$('kom').value=pl.openai_model||''}catch(e){}}
$('keysBtn').onclick=()=>{$('menu').classList.remove('on');$('kmsg').textContent='';$('keysMdl').classList.add('on');loadKeys()};
$('kClose').onclick=()=>$('keysMdl').classList.remove('on');$('keysMdl').onclick=e=>{if(e.target===$('keysMdl'))$('keysMdl').classList.remove('on')};
$('kSave').onclick=async()=>{const b={};[['kgm','gemini_key'],['kf','freesound_key'],['kg','groq_key'],['ko','openai_key']].forEach(([i,k])=>{const v=$(i).value.trim();if(v)b[k]=v==='-'?'':v});const any=Object.keys(b).length;[['kob','openai_base'],['kom','openai_model']].forEach(([i,k])=>{b[k]=$(i).value.trim()});if(!any&&!b.openai_base&&!b.openai_model){$('kmsg').textContent='لم تُدخل شيئاً';return}
 $('kmsg').textContent='جارٍ الحفظ...';try{const R=await fetch('/api/mykeys',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});const j=await R.json();if(!R.ok){$('kmsg').textContent=(j.error||j.msg||'✗ فشل الحفظ');return}$('kmsg').innerHTML='تم الحفظ ✓ — اضغط «اختبار المحفوظ» للتأكد أن المفاتيح تعمل';loadKeys()}catch(e){$('kmsg').textContent='فشل الحفظ'}};
$('kTest').onclick=async()=>{$('kmsg').textContent='جارٍ الاختبار...';let out=[];for(const p of ['gemini','freesound','groq','openai']){try{const r=await (await fetch('/api/mykeys/test/'+p,{method:'POST'})).json();if(!r.ok&&/غير مضبوط/.test(r.msg||''))continue;out.push((r.ok?'✓ ':'✗ '+p+': ')+(r.msg||''))}catch(e){out.push('✗ '+p)}}$('kmsg').innerHTML=out.length?out.map(esc).join('<br>'):'لا توجد مفاتيح محفوظة للاختبار'};
$('menuBtn').onclick=e=>{e.stopPropagation();$('menu').classList.toggle('on')};document.addEventListener('click',e=>{if(!e.target.closest('.menuwrap'))$('menu').classList.remove('on')});
loadCfg();$('mwv').textContent=$('mw').value;$('thv').textContent=$('th').value+'dB';$('msv').textContent=(+$('msil').value).toFixed(2)+'ث';markPreset();syncTime();
api('/api/health').then(r=>r.json()).then(h=>{S.gpu=!!h.gpu;if(h.cloud)log('☁️ الرندر السريع مفعّل','s');else $('cloudTg').parentElement.style.display='none';log('الاستوديو جاهز','s');if(!h.gpu&&!lsGet('sa_cfg'))$('model').value='small';syncTime()}).catch(e=>log(e.message,'e'));
refreshLib().then(L=>{let ids=[];try{ids=JSON.parse(lsGet('sa_sel')||'[]')}catch(e){}if(!ids.length){const last=lsGet('sa_media');if(last)ids=[last]}S.sel=ids.map(f=>L.find(x=>x.file===f)).filter(Boolean);if(S.sel.length)applySel(false)});
</script></body></html>
'''
open('index.html', 'w', encoding='utf-8').write(HTML)

# ===================== مكتبة المكونات SA Kit =====================
KIT = r'''import React from "react";
import { AbsoluteFill, Easing, Loop, OffthreadVideo, Sequence, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig, getInputProps } from "remotion";
import { loadFont } from "@remotion/google-fonts/Cairo";

let fam = "Cairo";
try { fam = loadFont("normal", { weights: ["400", "700", "900"], subsets: ["arabic", "latin"] }).fontFamily; } catch (e) {}
export const FONT = `${fam}, "Noto Sans Arabic", "Noto Naskh Arabic", "Noto Color Emoji", sans-serif`;

export type Word = { text: string; start: number; end: number };
export type Seg = { text: string; start: number; end: number; words: Word[] };
export type ClipInfo = { src: string; file?: string; type?: string; duration?: number; width?: number; height?: number; original?: string; hasAudio?: boolean };
export type MediaProps = { mediaSrc?: string | null; mediaType?: string | null; mediaDuration?: number; segments?: Seg[]; words?: Word[]; duration?: number;
  videoSrc?: string | null; audioSrc?: string | null; clips?: ClipInfo[]; videos?: ClipInfo[]; audios?: ClipInfo[]; files?: ClipInfo[] };

// يجمع الوسائط من خصائص المكوّن أو مباشرة من inputProps — يعمل حتى لو لم يمرّرها كود التصميم
const kindOf = (src?: string | null, t?: string | null): string | null =>
  t === "video" || t === "audio" ? t : (src ? (/\.(m4a|mp3|wav|aac|ogg|flac|opus)(\?|$)/i.test(src) ? "audio" : "video") : null);

// يجمع الوسائط من خصائص المكوّن أو مباشرة من inputProps — فيديو + ملف صوتي + عدة مقاطع، ويعمل حتى لو لم يمرّرها كود التصميم
export const useSAMedia = (p?: MediaProps): MediaProps => {
  let inp: any = {};
  try { inp = getInputProps() || {}; } catch (e) {}
  const q: any = p || {};
  const g = (k: string): any => (q[k] !== undefined && q[k] !== null && q[k] !== "" ? q[k] : (inp[k] !== undefined && inp[k] !== null && inp[k] !== "" ? inp[k] : null));
  const clips: ClipInfo[] = ((g("clips") || g("videos") || []) as ClipInfo[]).filter((c) => c && c.src);
  const audios: ClipInfo[] = ((g("audios") || []) as ClipInfo[]).filter((c) => c && c.src);
  const rawSrc: string | null = g("mediaSrc") || g("mediaUrl") || g("src") || null;
  const vSrc: string | null = g("videoSrc") || (clips[0] && clips[0].src) || (rawSrc && kindOf(rawSrc, g("mediaType")) === "video" ? rawSrc : null);
  const aAny: string | null = g("audioSrc") || (audios[0] && audios[0].src) || (rawSrc && kindOf(rawSrc, g("mediaType")) === "audio" ? rawSrc : null);
  const src = vSrc || rawSrc || aAny;
  const type = vSrc ? "video" : kindOf(src, g("mediaType"));
  return {
    mediaSrc: src,
    mediaType: type,
    mediaDuration: g("mediaDuration") || 0,
    segments: (q.segments && q.segments.length ? q.segments : inp.segments) || [],
    words: (q.words && q.words.length ? q.words : inp.words) || [],
    duration: g("duration") || undefined,
    videoSrc: vSrc,
    audioSrc: aAny && aAny !== vSrc ? aAny : null,
    clips: clips.length ? clips : (vSrc ? [{ src: vSrc, type: "video", duration: g("mediaDuration") || 0 }] : []),
    audios,
  };
};

export const SA = { bg: "#05060a", a: "#ff6a3d", b: "#ffd60a", c: "#00e5ff", d: "#b46bff", e: "#ff3d7f", g: "#7cff6b", w: "#f6f1e8", mute: "rgba(246,241,232,.66)" };
export const ease = Easing.bezier(0.16, 1, 0.3, 1);
export const clampOpts = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const Aurora: React.FC<{ colors?: string[]; speed?: number }> = ({ colors = [SA.a, SA.c, SA.d], speed = 1 }) => {
  const f = useCurrentFrame() * speed;
  const blobs = colors.map((c, i) => {
    const x = 50 + Math.sin(f / (70 + i * 23) + i * 2) * 38;
    const y = 50 + Math.cos(f / (80 + i * 19) + i * 3) * 34;
    return `radial-gradient(circle at ${x}% ${y}%, ${c}66 0%, ${c}00 ${44 + i * 6}%)`;
  });
  return <AbsoluteFill style={{ background: `${blobs.join(",")}, linear-gradient(160deg, #0b0c14, ${SA.bg})` }} />;
};

export const Grid: React.FC<{ opacity?: number }> = ({ opacity = 0.07 }) => {
  const f = useCurrentFrame(); const { width, height } = useVideoConfig(); const m = Math.min(width, height); const s = m * 0.09;
  const mask = "radial-gradient(circle at 50% 50%, #000 15%, transparent 72%)";
  return <AbsoluteFill style={{ backgroundImage: `linear-gradient(rgba(255,255,255,${opacity}) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,${opacity}) 1px, transparent 1px)`, backgroundSize: `${s}px ${s}px`, backgroundPosition: `${f * 0.5}px ${f * 0.5}px`, WebkitMaskImage: mask, maskImage: mask }} />;
};

export const Particles: React.FC<{ n?: number; color?: string }> = ({ n = 36, color = "#ffffff" }) => {
  const f = useCurrentFrame(); const { width, height } = useVideoConfig(); const m = Math.min(width, height);
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {Array.from({ length: n }).map((_, i) => {
        const d = 0.3 + random("pd" + i) * 0.7;
        const y = (((random("py" + i) * height - f * d * 2.2) % height) + height) % height;
        const x = random("px" + i) * width + Math.sin(f / 30 + i) * m * 0.02;
        const s = m * (0.004 + d * 0.008);
        return <div key={i} style={{ position: "absolute", left: x, top: y, width: s, height: s, borderRadius: 99, background: color, opacity: 0.1 + d * 0.4, boxShadow: `0 0 ${s * 3}px ${color}` }} />;
      })}
    </AbsoluteFill>
  );
};

export const Vignette: React.FC<{ strength?: number }> = ({ strength = 0.7 }) => (
  <AbsoluteFill style={{ background: `radial-gradient(ellipse at center, transparent 42%, rgba(0,0,0,${strength}) 100%)`, pointerEvents: "none" }} />
);

const NOISE = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="220" height="220"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.55 0"/></filter><rect width="100%" height="100%" filter="url(#n)"/></svg>');
export const Grain: React.FC<{ opacity?: number }> = ({ opacity = 0.06 }) => {
  const f = useCurrentFrame();
  return <AbsoluteFill style={{ backgroundImage: `url("${NOISE}")`, backgroundSize: "220px 220px", backgroundPosition: `${(f * 37) % 220}px ${(f * 61) % 220}px`, opacity, pointerEvents: "none" }} />;
};

export const LightLeak: React.FC<{ at?: number; dur?: number; color?: string }> = ({ at = 0, dur = 24, color = SA.a }) => {
  const f = useCurrentFrame();
  const p = interpolate(f, [at, at + dur], [0, 1], clampOpts);
  const o = Math.sin(p * Math.PI);
  if (o <= 0.001) return null;
  return <AbsoluteFill style={{ opacity: o * 0.85, mixBlendMode: "screen", pointerEvents: "none", background: `linear-gradient(115deg, transparent ${p * 130 - 70}%, ${color}aa ${p * 130 - 38}%, #ffffff66 ${p * 130 - 26}%, transparent ${p * 130}%)` }} />;
};

export const MediaVideo: React.FC<{ src: string; mediaDuration?: number; style?: React.CSSProperties }> = ({ src, mediaDuration = 0, style }) => {
  const { fps, durationInFrames } = useVideoConfig();
  const mf = Math.max(1, Math.floor((mediaDuration || durationInFrames / fps) * fps));
  return (
    <Loop durationInFrames={mf}>
      <OffthreadVideo src={/^https?:\/\//.test(src) ? src : staticFile(src)} muted style={{ width: "100%", height: "100%", objectFit: "cover", ...style }} />
    </Loop>
  );
};

// عدة مقاطع فيديو تُشغَّل بالتتابع (وتُعاد حلقةً إن كانت أقصر من الفيديو). تُستخدم تلقائياً داخل Stage/VideoBg عند وجود أكثر من مقطع.
export const VideoClips: React.FC<{ clips?: ClipInfo[]; style?: React.CSSProperties }> = ({ clips, style }) => {
  const { fps, durationInFrames } = useVideoConfig();
  const mm = useSAMedia();
  const list = ((clips && clips.length ? clips : mm.clips) || []).filter((c) => c && c.src);
  if (!list.length) return null;
  const fr = list.map((c) => Math.max(1, Math.round((c.duration || 3) * fps)));
  const total = fr.reduce((a, b) => a + b, 0);
  const seq = list.map((c, i) => (
    <Sequence key={i} from={fr.slice(0, i).reduce((a, b) => a + b, 0)} durationInFrames={fr[i]}>
      <OffthreadVideo src={/^https?:\/\//.test(c.src) ? c.src : staticFile(c.src)} muted style={{ width: "100%", height: "100%", objectFit: "cover", ...style }} />
    </Sequence>
  ));
  return <AbsoluteFill>{total >= durationInFrames ? seq : <Loop durationInFrames={total}>{seq}</Loop>}</AbsoluteFill>;
};

export const useSAClips = (): ClipInfo[] => useSAMedia().clips || [];

export const VideoBg: React.FC<{ src?: string | null; type?: string | null; mediaDuration?: number; dim?: number; zoom?: boolean; colors?: string[] }> = ({ src, type, mediaDuration = 0, dim = 0.45, zoom = true, colors }) => {
  const f = useCurrentFrame(); const { durationInFrames } = useVideoConfig();
  const multi = useSAMedia().clips || [];
  if (!src || type !== "video") return <Aurora colors={colors} />;
  const z = zoom ? interpolate(f, [0, durationInFrames], [1.05, 1.17]) : 1.05;
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <AbsoluteFill style={{ transform: `scale(${z}) translate(${Math.sin(f / 90) * 8}px, ${Math.cos(f / 110) * 6}px)` }}>
        {multi.length > 1 ? <VideoClips clips={multi} style={{ filter: "contrast(1.1) saturate(1.2) brightness(.92)" }} /> : <MediaVideo src={src} mediaDuration={mediaDuration} style={{ filter: "contrast(1.1) saturate(1.2) brightness(.92)" }} />}
      </AbsoluteFill>
      <AbsoluteFill style={{ background: `linear-gradient(180deg, rgba(0,0,0,${dim * 0.7}), rgba(0,0,0,${dim * 0.3}) 45%, rgba(0,0,0,${Math.min(0.92, dim + 0.3)}))` }} />
    </AbsoluteFill>
  );
};

export const Stage: React.FC<{ media?: MediaProps; colors?: string[]; grid?: boolean; dim?: number; children?: React.ReactNode }> = ({ media, colors, grid = true, dim = 0.45, children }) => {
  const mm = useSAMedia(media);
  return (
  <AbsoluteFill style={{ background: SA.bg, fontFamily: FONT }}>
    <VideoBg src={mm.mediaSrc} type={mm.mediaType} mediaDuration={mm.mediaDuration} dim={dim} colors={colors} />
    {grid && <Grid />}
    <Particles n={34} />
    {children}
    <Vignette />
    <Grain />
  </AbsoluteFill>
  );
};

export const Kinetic: React.FC<{ text: string; color?: string; size?: number; delay?: number; stagger?: number; hl?: number[]; hlColor?: string; style?: React.CSSProperties }> = ({ text, color = SA.w, size = 0.13, delay = 0, stagger = 5, hl = [], hlColor = SA.b, style }) => {
  const f = useCurrentFrame(); const { fps, width, height } = useVideoConfig(); const m = Math.min(width, height);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", alignItems: "center", gap: `${m * 0.01}px ${m * 0.03}px`, direction: "rtl", fontFamily: FONT, ...style }}>
      {text.split(" ").map((w, i) => {
        const s = spring({ frame: f - delay - i * stagger, fps, config: { damping: 12, stiffness: 150 } });
        const c = hl.includes(i) ? hlColor : color;
        const k = Math.min(1, s);
        return (
          <span key={i} style={{ fontWeight: 900, fontSize: m * size, color: c, display: "inline-block", lineHeight: 1.2,
            transform: `translateY(${(1 - s) * m * 0.12}px) scale(${0.7 + Math.min(1.15, s) * 0.3}) rotate(${(1 - s) * (i % 2 ? 7 : -7)}deg)`,
            opacity: Math.min(1, s * 1.4), filter: k > 0.985 ? "none" : `blur(${(1 - k) * 14}px)`,
            textShadow: `0 ${m * 0.008}px ${m * 0.04}px ${c}66, 0 ${m * 0.004}px 0 rgba(0,0,0,.35)` }}>{w}</span>
        );
      })}
    </div>
  );
};

export const Glass: React.FC<{ children?: React.ReactNode; style?: React.CSSProperties; glow?: string }> = ({ children, style, glow = SA.c }) => {
  const { width, height } = useVideoConfig(); const m = Math.min(width, height);
  return (
    <div style={{ borderRadius: m * 0.05, padding: m * 0.045, background: "linear-gradient(160deg, rgba(255,255,255,.14), rgba(255,255,255,.04))", border: "1.5px solid rgba(255,255,255,.2)",
      boxShadow: `0 ${m * 0.03}px ${m * 0.12}px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.28), 0 0 ${m * 0.1}px ${glow}2e`, ...style }}>{children}</div>
  );
};

export const Pop: React.FC<{ children?: React.ReactNode; delay?: number; from?: "up" | "down" | "left" | "right" | "scale"; style?: React.CSSProperties }> = ({ children, delay = 0, from = "up", style }) => {
  const f = useCurrentFrame(); const { fps, width, height } = useVideoConfig(); const m = Math.min(width, height);
  const s = spring({ frame: f - delay, fps, config: { damping: 14, stiffness: 140 } });
  const d = (1 - s) * m * 0.14;
  const tx = from === "left" ? -d : from === "right" ? d : 0;
  const ty = from === "up" ? d : from === "down" ? -d : 0;
  const sc = from === "scale" ? 0.6 + Math.min(1.1, s) * 0.4 : 1;
  return <div style={{ transform: `translate(${tx}px, ${ty}px) scale(${sc})`, opacity: Math.min(1, s * 1.5), ...style }}>{children}</div>;
};

export const Icon: React.FC<{ emoji: string; color?: string; size?: number; delay?: number }> = ({ emoji, color = SA.a, size = 0.12, delay = 0 }) => {
  const f = useCurrentFrame(); const { fps, width, height } = useVideoConfig(); const m = Math.min(width, height);
  const s = spring({ frame: f - delay, fps, config: { damping: 9, stiffness: 160 } });
  const d = m * size; const float = Math.sin((f - delay) / 14) * m * 0.006;
  return (
    <div style={{ width: d, height: d, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: d * 0.52, flexShrink: 0, fontFamily: FONT,
      background: `radial-gradient(circle at 30% 25%, ${color}66, ${color}22 70%)`, border: `2px solid ${color}88`,
      boxShadow: `0 0 ${d * 0.5}px ${color}55, inset 0 0 ${d * 0.25}px ${color}33`, transform: `translateY(${float}px) scale(${Math.min(1.15, s)})`, opacity: Math.min(1, s * 2) }}>{emoji}</div>
  );
};

export const Counter: React.FC<{ to: number; unit?: string; label?: string; color?: string; delay?: number }> = ({ to, unit = "", label = "", color = SA.b, delay = 4 }) => {
  const f = useCurrentFrame(); const { fps, width, height } = useVideoConfig(); const m = Math.min(width, height);
  const p = interpolate(f, [delay, delay + fps * 1.5], [0, 1], { ...clampOpts, easing: Easing.out(Easing.cubic) });
  const pop = Math.min(1.1, spring({ frame: f - delay, fps, config: { damping: 12 } }));
  return (
    <div style={{ textAlign: "center", fontFamily: FONT, transform: `scale(${0.85 + pop * 0.15})` }}>
      <div style={{ fontSize: m * 0.2, fontWeight: 900, color, lineHeight: 1.05, direction: "ltr", textShadow: `0 0 ${m * 0.07}px ${color}88` }}>{Math.round(to * p).toLocaleString("en-US")}{unit}</div>
      <div style={{ width: m * 0.5 * p, height: m * 0.01, background: `linear-gradient(90deg, ${color}, ${SA.a})`, margin: `${m * 0.025}px auto`, borderRadius: 9 }} />
      {label ? <div style={{ fontSize: m * 0.055, color: SA.w, fontWeight: 700 }}>{label}</div> : null}
    </div>
  );
};

export const Ring: React.FC<{ value: number; label?: string; color?: string; size?: number; delay?: number }> = ({ value, label = "", color = SA.c, size = 0.19, delay = 8 }) => {
  const f = useCurrentFrame(); const { fps, width, height } = useVideoConfig(); const m = Math.min(width, height); const d = m * size;
  const p = interpolate(f, [delay, delay + fps * 1.4], [0, 1], { ...clampOpts, easing: Easing.out(Easing.cubic) });
  const C = 2 * Math.PI * 42;
  return (
    <div style={{ width: d, textAlign: "center", fontFamily: FONT }}>
      <div style={{ position: "relative", width: d, height: d }}>
        <svg width={d} height={d} viewBox="0 0 100 100" style={{ transform: "rotate(-90deg)" }}>
          <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,.12)" strokeWidth="9" />
          <circle cx="50" cy="50" r="42" fill="none" stroke={color} strokeWidth="9" strokeLinecap="round" strokeDasharray={`${(value / 100) * p * C} ${C}`} style={{ filter: `drop-shadow(0 0 6px ${color})` }} />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: d * 0.27, fontWeight: 900, color: SA.w, direction: "ltr" }}>{Math.round(value * p)}%</div>
      </div>
      {label ? <div style={{ marginTop: m * 0.012, fontSize: m * 0.035, color: SA.mute, fontWeight: 700 }}>{label}</div> : null}
    </div>
  );
};

export const Equalizer: React.FC<{ bars?: number; color?: string; height?: number }> = ({ bars = 20, color = SA.c, height = 0.14 }) => {
  const f = useCurrentFrame(); const { width, height: H } = useVideoConfig(); const m = Math.min(width, H);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: m * 0.012, height: m * height }}>
      {Array.from({ length: bars }).map((_, i) => {
        const v = 0.2 + 0.8 * Math.abs(Math.sin(f / 5 + i * 0.7) * Math.cos(f / 11 + i * 0.35));
        return <div key={i} style={{ width: m * 0.016, height: `${v * 100}%`, borderRadius: 99, background: `linear-gradient(180deg, ${color}, ${SA.a})`, boxShadow: `0 0 ${m * 0.012}px ${color}88` }} />;
      })}
    </div>
  );
};

export const Burst: React.FC<{ at?: number; colors?: string[]; n?: number }> = ({ at = 0, colors = [SA.a, SA.b, SA.c, SA.e], n = 48 }) => {
  const f = useCurrentFrame(); const { width, height } = useVideoConfig(); const m = Math.min(width, height); const t = f - at;
  const flash = interpolate(t, [0, 3, 18], [0, 0.5, 0], clampOpts);
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {t >= 0 && Array.from({ length: n }).map((_, i) => {
        const a = (i / n) * Math.PI * 2 + random("ba" + i) * 0.3;
        const dist = interpolate(t, [0, 45], [0, m * (0.25 + random("bd" + i) * 0.55)], { ...clampOpts, easing: Easing.out(Easing.exp) });
        const sz = m * (0.01 + random("bs" + i) * 0.016);
        return <div key={i} style={{ position: "absolute", left: width / 2 + Math.cos(a) * dist, top: height / 2 + Math.sin(a) * dist + t * 0.8, width: sz, height: sz * (i % 3 ? 1 : 2.4), borderRadius: 3, background: colors[i % colors.length], transform: `rotate(${i * 37 + t * 9}deg)`, opacity: interpolate(t, [10, 70], [1, 0], clampOpts) }} />;
      })}
      <AbsoluteFill style={{ background: "#fff", opacity: flash }} />
    </AbsoluteFill>
  );
};

export const ProgressBar: React.FC<{ color?: string }> = ({ color = SA.a }) => {
  const f = useCurrentFrame(); const { durationInFrames, width, height } = useVideoConfig(); const m = Math.min(width, height);
  return <div style={{ position: "absolute", top: 0, right: 0, height: Math.max(4, m * 0.007), width: `${(f / durationInFrames) * 100}%`, background: `linear-gradient(270deg, ${color}, ${SA.b})`, boxShadow: `0 0 ${m * 0.02}px ${color}` }} />;
};

export type SceneDef = { dur: number; node: React.ReactNode; tr?: "slide" | "fade" | "zoom" | "wipe" | "flash" | "none" };

const SceneShell: React.FC<{ enter: string; exit: string; dur: number; overlap: number; children?: React.ReactNode }> = ({ enter, exit, dur, overlap, children }) => {
  const f = useCurrentFrame(); const { height } = useVideoConfig();
  const e = Easing.bezier(0.65, 0, 0.35, 1);
  const ei = e(interpolate(f, [0, overlap], [0, 1], clampOpts));
  const eo = e(interpolate(f, [dur, dur + overlap], [0, 1], clampOpts));
  let tf = ""; let op = 1; let clip = "none";
  if (enter === "slide") tf += `translateY(${(1 - ei) * height}px) `;
  else if (enter === "fade" || enter === "flash") op *= ei;
  else if (enter === "zoom") { tf += `scale(${1.5 - 0.5 * ei}) `; op *= ei; }
  else if (enter === "wipe") clip = `inset(0 0 0 ${(1 - ei) * 100}%)`;
  if (exit === "slide") { tf += `translateY(${-eo * height * 0.22}px) scale(${1 - eo * 0.06}) `; op *= 1 - eo * 0.7; }
  else if (exit === "fade") op *= 1 - eo;
  else if (exit === "zoom") { tf += `scale(${1 + eo * 0.18}) `; op *= 1 - eo; }
  else if (exit === "wipe") op *= 1 - eo * 0.5;
  else if (exit === "flash") op *= 1 - eo;
  const flash = enter === "flash" ? interpolate(f, [0, 3, overlap], [0.9, 0.6, 0], clampOpts) : 0;
  return (
    <AbsoluteFill style={{ transform: tf.trim() || "none", opacity: op, clipPath: clip }}>
      {children}
      {flash > 0.01 ? <AbsoluteFill style={{ background: "#fff", opacity: flash }} /> : null}
    </AbsoluteFill>
  );
};

export const Scenes: React.FC<{ scenes: SceneDef[]; overlap?: number }> = ({ scenes, overlap = 14 }) => {
  let start = 0;
  return (
    <AbsoluteFill>
      {scenes.map((sc, i) => {
        const from = start; start += sc.dur;
        const last = i === scenes.length - 1; const next = scenes[i + 1];
        return (
          <Sequence key={i} from={from} durationInFrames={sc.dur + (last ? 0 : overlap)}>
            <SceneShell enter={i === 0 ? "none" : sc.tr || "slide"} exit={last ? "none" : (next && next.tr) || "slide"} dur={sc.dur} overlap={overlap}>{sc.node}</SceneShell>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const EMOJI: [string[], string][] = [
  [["نار", "حرق", "fire", "hot"], "🔥"], [["حب", "قلب", "love", "heart"], "❤️"], [["مال", "فلوس", "ربح", "دولار", "money", "cash"], "💰"],
  [["سرعة", "سريع", "fast", "speed"], "⚡"], [["نجاح", "فوز", "نصر", "win", "success"], "🏆"], [["فكرة", "فكر", "idea"], "💡"],
  [["انتبه", "تحذير", "خطر", "warning", "danger"], "⚠️"], [["ضحك", "هههه", "lol", "funny"], "😂"], [["جديد", "new"], "✨"],
  [["صوت", "موسيقى", "music"], "🎵"], [["وقت", "ساعة", "time"], "⏰"], [["عالم", "العالم", "world"], "🌍"], [["قوة", "قوي", "power", "strong"], "💪"],
  [["سر", "سري", "secret"], "🤫"], [["صدمة", "مفاجأة", "wow", "shock"], "😱"], [["اشترك", "تابع", "subscribe", "follow"], "🔔"],
  [["ملايين", "مليون", "million"], "🚀"], [["نصيحة", "tip"], "📌"], [["سؤال", "لماذا", "كيف", "؟", "?"], "🤔"], [["شكرا", "شكراً", "thanks"], "🙏"],
];
export const autoEmoji = (text: string): string | null => {
  const t = (text || "").toLowerCase();
  for (const [keys, e] of EMOJI) { if (keys.some((k) => t.includes(k))) return e; }
  return null;
};

export const Captions: React.FC<{ segments?: Seg[]; variant?: "pill" | "outline" | "karaoke"; anchor?: "center" | "bottom"; size?: number; palette?: string[]; emoji?: boolean }> = ({ segments: segIn, variant = "pill", anchor = "center", size = 0.1, palette = [SA.b, SA.c, SA.e, SA.g], emoji = true }) => {
  const segments: Seg[] = (segIn && segIn.length ? segIn : useSAMedia().segments) || [];
  const frame = useCurrentFrame(); const { fps, width, height } = useVideoConfig(); const m = Math.min(width, height); const t = frame / fps;
  const idx = segments.findIndex((s, i) => t >= s.start - 0.05 && t < (segments[i + 1] ? segments[i + 1].start - 0.05 : s.end + 0.6));
  if (idx < 0) return null;
  const seg = segments[idx]; const col = palette[idx % palette.length];
  const segF = Math.round((seg.start - 0.05) * fps);
  const enter = spring({ frame: frame - segF, fps, config: { damping: 13, stiffness: 190 } });
  const endT = segments[idx + 1] ? segments[idx + 1].start - 0.05 : seg.end + 0.6;
  const out = interpolate(t, [endT - 0.1, endT], [1, 0], clampOpts);
  const em = emoji ? autoEmoji(seg.text) : null;
  const emS = spring({ frame: frame - segF - 3, fps, config: { damping: 8, stiffness: 200 } });
  return (
    <AbsoluteFill style={{ justifyContent: anchor === "bottom" ? "flex-end" : "center", alignItems: "center", paddingBottom: anchor === "bottom" ? height * 0.17 : 0, paddingLeft: m * 0.06, paddingRight: m * 0.06, flexDirection: "column", gap: m * 0.03, fontFamily: FONT }}>
      {em ? <div style={{ fontSize: m * 0.13, transform: `scale(${Math.min(1.2, emS)}) rotate(${(1 - Math.min(1, emS)) * -20}deg)`, opacity: Math.min(1, emS * 2) * out, filter: "drop-shadow(0 8px 18px rgba(0,0,0,.5))" }}>{em}</div> : null}
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: `${m * 0.01}px ${m * 0.022}px`, direction: "rtl", opacity: Math.min(1, enter * 1.5) * out,
        transform: `scale(${0.75 + Math.min(1.1, enter) * 0.25}) translateY(${(1 - Math.min(1, enter)) * m * 0.06}px) rotate(${(1 - Math.min(1, enter)) * (idx % 2 ? 4 : -4)}deg)` }}>
        {(seg.words || []).map((w, i) => {
          const active = t >= w.start && t < w.end + 0.05; const past = t >= w.end;
          const pop = Math.min(1.2, spring({ frame: frame - Math.round(w.start * fps), fps, config: { damping: 9, stiffness: 280 } }));
          const base: React.CSSProperties = { fontSize: m * size, fontWeight: 900, lineHeight: 1.25, display: "inline-block" };
          if (variant === "outline") {
            return <span key={i} style={{ ...base, color: active ? col : "#fff", WebkitTextStroke: `${m * 0.008}px #000`, paintOrder: "stroke fill", textShadow: `0 ${m * 0.008}px 0 #000, 0 0 ${m * 0.04}px rgba(0,0,0,.8)`,
              transform: `scale(${active ? 1 + pop * 0.16 : 1}) rotate(${active ? (i % 2 ? 2 : -2) : 0}deg)` }}>{w.text}</span>;
          }
          if (variant === "karaoke") {
            const pr = Math.max(0, Math.min(1, (t - w.start) / Math.max(0.05, w.end - w.start)));
            return <span key={i} style={{ ...base, backgroundImage: `linear-gradient(to left, ${col} ${pr * 100}%, #ffffff ${pr * 100}%)`, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent", WebkitTextFillColor: "transparent",
              filter: "drop-shadow(0 6px 14px rgba(0,0,0,.65))", transform: `scale(${active ? 1.08 : 1})` }}>{w.text}</span>;
          }
          return <span key={i} style={{ ...base, color: active ? "#111" : past ? "#fff" : "rgba(255,255,255,.45)", background: active ? col : "transparent", padding: "0 .2em", borderRadius: m * 0.025,
            transform: `scale(${active ? 1 + pop * 0.14 : 1}) translateY(${active ? -pop * 8 : 0}px)`, boxShadow: active ? `0 0 ${m * 0.07}px ${col}` : "none", textShadow: active ? "none" : "0 6px 24px rgba(0,0,0,.7)" }}>{w.text}</span>;
        })}
      </div>
    </AbsoluteFill>
  );
};

export const Hint: React.FC<{ text: string }> = ({ text }) => {
  const { width, height } = useVideoConfig(); const m = Math.min(width, height);
  void m; void width; void height; void text; return null;
};
'''
open('src/sa_kit.tsx', 'w', encoding='utf-8').write(KIT)

# ===================== القوالب =====================
TPL_SHOWCASE = r'''import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Stage, Scenes, Kinetic, Glass, Pop, Icon, Counter, Ring, Equalizer, Burst, ProgressBar, LightLeak, SA, MediaProps } from "./sa_kit";

export const SFX = [
  { rt: 0.0, kind: "rise" }, { rt: 0.05, kind: "impact" }, { rt: 0.17, kind: "whoosh" }, { rt: 0.2, kind: "pop" }, { rt: 0.27, kind: "ding", vol: 0.8 },
  { rt: 0.37, kind: "whoosh" }, { rt: 0.41, kind: "pop" }, { rt: 0.45, kind: "pop" }, { rt: 0.49, kind: "pop" },
  { rt: 0.6, kind: "whoosh" }, { rt: 0.64, kind: "click" }, { rt: 0.68, kind: "click" },
  { rt: 0.76, kind: "rise" }, { rt: 0.8, kind: "impact" }, { rt: 0.8, kind: "bass", vol: 0.7 },
];

const Center: React.FC<{ children?: React.ReactNode; gap?: number }> = ({ children, gap = 0.04 }) => {
  const { width, height } = useVideoConfig(); const m = Math.min(width, height);
  return <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", gap: m * gap, padding: m * 0.07 }}>{children}</AbsoluteFill>;
};

const Hook: React.FC = () => {
  const { width, height } = useVideoConfig(); const m = Math.min(width, height);
  return (
    <Center gap={0.05}>
      <Icon emoji="🎬" color={SA.a} size={0.2} />
      <Kinetic text="هذا ليس فيديو عادي" size={0.12} hl={[2, 3]} hlColor={SA.b} delay={6} />
      <Pop delay={30}><div style={{ fontSize: m * 0.045, color: SA.mute, fontWeight: 700 }}>موشن احترافي بدقة سينمائية ✨</div></Pop>
      <LightLeak at={4} dur={26} />
    </Center>
  );
};

const Stats: React.FC = () => {
  const { width, height } = useVideoConfig(); const m = Math.min(width, height);
  return (
    <Center>
      <Pop from="scale">
        <Glass glow={SA.b} style={{ width: Math.min(width * 0.86, m * 1.3), display: "flex", flexDirection: "column", alignItems: "center", gap: m * 0.04 }}>
          <div style={{ display: "flex", alignItems: "center", gap: m * 0.03 }}>
            <Icon emoji="👁️" color={SA.b} size={0.1} delay={4} />
            <div style={{ fontSize: m * 0.05, color: SA.mute, fontWeight: 700 }}>إجمالي المشاهدات</div>
          </div>
          <Counter to={1000000} unit="+" label="مشاهدة في أسبوع واحد" />
          <div style={{ display: "flex", gap: m * 0.08 }}>
            <Ring value={92} label="تفاعل" color={SA.c} />
            <Ring value={78} label="احتفاظ" color={SA.e} delay={14} />
          </div>
        </Glass>
      </Pop>
    </Center>
  );
};

const FEATS: [string, string, string, string][] = [
  ["⚡", "سرعة خارقة", "رندر فوري بجودة عالية", SA.b],
  ["🎯", "دقة متناهية", "مزامنة الكلمات بالمللي ثانية", SA.c],
  ["🎨", "إبداع بلا حدود", "تصميمات وانتقالات سينمائية", SA.e],
];
const Feats: React.FC = () => {
  const { width, height } = useVideoConfig(); const m = Math.min(width, height);
  return (
    <Center gap={0.035}>
      <Kinetic text="كل ما تحتاجه" size={0.09} color={SA.w} hl={[2]} hlColor={SA.c} />
      {FEATS.map(([emoji, title, sub, color], i) => (
        <Pop key={i} from="right" delay={14 + i * 9}>
          <Glass glow={color} style={{ width: Math.min(width * 0.86, m * 1.3), display: "flex", alignItems: "center", gap: m * 0.035, padding: m * 0.035 }}>
            <Icon emoji={emoji} color={color} size={0.12} delay={16 + i * 9} />
            <div>
              <div style={{ fontSize: m * 0.058, fontWeight: 900, color: SA.w }}>{title}</div>
              <div style={{ fontSize: m * 0.036, fontWeight: 700, color: SA.mute }}>{sub}</div>
            </div>
          </Glass>
        </Pop>
      ))}
    </Center>
  );
};

const Keys: React.FC = () => (
  <Center gap={0.06}>
    <Icon emoji="🔥" color={SA.e} size={0.16} />
    <Kinetic text="حركة · إيقاع · قوة" size={0.1} color={SA.c} stagger={9} />
    <Equalizer bars={22} color={SA.c} />
  </Center>
);

const Cta: React.FC = () => {
  const f = useCurrentFrame(); const { width, height } = useVideoConfig(); const m = Math.min(width, height);
  const pulse = 1 + Math.sin(f / 6) * 0.03;
  return (
    <Center gap={0.05}>
      <Burst at={8} />
      <Kinetic text="ابدأ الآن" size={0.17} color={SA.a} delay={8} hl={[0]} hlColor={SA.b} />
      <Pop delay={26} from="scale">
        <div style={{ transform: `scale(${pulse})`, background: `linear-gradient(135deg, ${SA.a}, ${SA.b})`, color: "#1a0f0a", fontWeight: 900, fontSize: m * 0.06, padding: `${m * 0.025}px ${m * 0.07}px`, borderRadius: 999, boxShadow: `0 0 ${m * 0.1}px ${SA.a}88` }}>🚀 انضم إلينا</div>
      </Pop>
    </Center>
  );
};

export const Motion: React.FC<MediaProps> = (props) => {
  const { durationInFrames: D } = useVideoConfig();
  const weights = [2.8, 3.2, 3.6, 2.8, 3.4]; const sum = weights.reduce((a, b) => a + b, 0);
  const durs = weights.map((w) => Math.max(8, Math.round((w / sum) * D)));
  durs[durs.length - 1] += D - durs.reduce((a, b) => a + b, 0);
  const overlap = Math.max(2, Math.min(14, Math.floor(Math.min(...durs) / 2)));
  return (
    <Stage media={props} colors={[SA.a, SA.c, SA.d]} dim={0.5}>
      <Scenes overlap={overlap} scenes={[
        { dur: durs[0], node: <Hook /> },
        { dur: durs[1], node: <Stats />, tr: "slide" },
        { dur: durs[2], node: <Feats />, tr: "wipe" },
        { dur: durs[3], node: <Keys />, tr: "zoom" },
        { dur: durs[4], node: <Cta />, tr: "flash" },
      ]} />
      <ProgressBar />
    </Stage>
  );
};
'''

TPL_CAPTIONS = r'''import React from "react";
import { Stage, Captions, Hint, ProgressBar, SA, MediaProps } from "./sa_kit";

export const Motion: React.FC<MediaProps> = (props) => {
  const segments = props.segments || [];
  return (
    <Stage media={props} colors={[SA.c, SA.e, SA.d]} dim={0.5}>
      <Captions segments={segments} variant="pill" anchor="center" size={0.105} />
      {!segments.length ? <Hint text={props.mediaSrc ? "اضغط «تفريغ الصوت» لتظهر الترجمة هنا" : "ارفع ملفاً ثم اضغط «تفريغ الصوت» لتظهر الترجمة هنا"} /> : null}
      <ProgressBar color={SA.c} />
    </Stage>
  );
};
'''

TPL_VOICEOVER = r'''import React from "react";
import { AbsoluteFill, getInputProps, useVideoConfig } from "remotion";
import { Stage, Captions, Hint, ProgressBar, Scenes, SceneDef, Kinetic, Icon, Aurora, SA, autoEmoji, MediaProps } from "./sa_kit";

// قالب «تعليق صوتي»: كل جملة من الصوت المولَّد تصبح مشهداً مستقلاً يبدأ في لحظة نطقها بالضبط،
// والكلمات تُضاء كلمةً بكلمة حسب التوقيت الحقيقي. ولّد الصوت من لوحة «توليد الصوت» ثم ارندر.
const PALS = [[SA.a, SA.d, SA.c], [SA.c, SA.e, SA.d], [SA.b, SA.a, SA.e], [SA.g, SA.c, SA.d], [SA.e, SA.d, SA.a]];
const EMOJIS = ["✨", "🚀", "💡", "🔥", "🎯", "⚡"];
const TRS: SceneDef["tr"][] = ["slide", "zoom", "wipe", "fade", "flash"];

const SceneCard: React.FC<{ text: string; idx: number }> = ({ text, idx }) => {
  const { height } = useVideoConfig();
  const words = text.split(/\s+/).filter(Boolean);
  let hi = 0;
  words.forEach((w, i) => { if (w.length > words[hi].length) hi = i; });
  const key = (words[hi] || "").replace(/[.,!?؟،:؛"'«»()]/g, "");
  const pal = PALS[idx % PALS.length];
  const em = autoEmoji(text) || EMOJIS[idx % EMOJIS.length];
  return (
    <AbsoluteFill>
      <Aurora colors={pal} speed={1 + (idx % 3) * 0.2} />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", paddingBottom: height * 0.14 }}>
        <Icon emoji={em} color={pal[0]} size={0.16} delay={2} />
        <Kinetic text={key} color={SA.w} hl={[0]} hlColor={pal[0]} size={0.17} delay={4} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const Motion: React.FC<MediaProps> = (props) => {
  const { fps, durationInFrames } = useVideoConfig();
  let inp: any = {};
  try { inp = getInputProps() || {}; } catch (e) {}
  const scenes: { text: string; start: number; end: number }[] = (props as any).scenes || inp.scenes || [];
  const segments = (props.segments && props.segments.length ? props.segments : inp.segments) || [];
  if (!scenes.length) return <Stage media={props}><Hint text="ولّد صوتاً من لوحة «توليد الصوت» ثم اختره وارندر" /></Stage>;
  const defs: SceneDef[] = scenes.map((s, i) => {
    const a = i === 0 ? 0 : Math.round(s.start * fps);
    const b = i === scenes.length - 1 ? durationInFrames : Math.round(scenes[i + 1].start * fps);
    return { dur: Math.max(12, b - a), tr: TRS[i % TRS.length], node: <SceneCard text={s.text} idx={i} /> };
  });
  return (
    <Stage media={props} colors={[SA.d, SA.a, SA.c]} dim={0.6} grid={false}>
      <Scenes scenes={defs} />
      <Captions segments={segments} variant="karaoke" anchor="bottom" size={0.085} emoji={false} />
      <ProgressBar color={SA.a} />
    </Stage>
  );
};
'''

TPL_VIDEO = r'''import React from "react";
import { AbsoluteFill, interpolate, random, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Aurora, Captions, Grain, Hint, LightLeak, MediaVideo, ProgressBar, SA, Vignette, FONT, clampOpts, MediaProps, useSAMedia } from "./sa_kit";

export const Motion: React.FC<MediaProps> = (propsIn) => {
  const props = useSAMedia(propsIn);
  const frame = useCurrentFrame(); const { fps, width, height, durationInFrames } = useVideoConfig();
  const m = Math.min(width, height); const t = frame / fps;
  const segments = props.segments || [];
  const idx = segments.findIndex((s, i) => t >= s.start - 0.05 && t < (segments[i + 1] ? segments[i + 1].start - 0.05 : s.end + 0.5));
  const seg = idx >= 0 ? segments[idx] : null;
  const segF = seg ? Math.round((seg.start - 0.05) * fps) : -999;
  const punch = Math.min(1, spring({ frame: frame - segF, fps, config: { damping: 14, stiffness: 180 } }));
  const strong = !!seg && /[!؟?]/.test(seg.text);
  const base = idx % 3 === 0 ? 1.04 : idx % 3 === 1 ? 1.12 : 1.08;
  const zoom = base + (1 - punch) * 0.05 + interpolate(frame, [0, durationInFrames], [0, 0.04]);
  const shake = strong && frame >= segF && frame - segF < 10 ? (random("s" + frame) - 0.5) * m * 0.02 : 0;
  const flash = interpolate(frame - segF, [0, 3, 9], [0.28, 0.16, 0], clampOpts);
  const fade = Math.min(interpolate(frame, [0, 10], [0, 1], clampOpts), interpolate(frame, [durationInFrames - 12, durationInFrames], [1, 0], clampOpts));
  const hasVideo = !!props.mediaSrc && props.mediaType === "video";
  return (
    <AbsoluteFill style={{ background: "#000", fontFamily: FONT, opacity: fade }}>
      {hasVideo ? (
        <AbsoluteFill style={{ transform: `scale(${zoom}) translate(${shake}px, ${shake * 0.6}px)` }}>
          <MediaVideo src={props.mediaSrc as string} mediaDuration={props.mediaDuration} style={{ filter: "contrast(1.1) saturate(1.18) brightness(.95)" }} />
        </AbsoluteFill>
      ) : <Aurora colors={[SA.a, SA.c, SA.e]} />}
      <Vignette strength={0.65} />
      <AbsoluteFill style={{ background: "linear-gradient(transparent 55%, rgba(0,0,0,.72))" }} />
      {seg && idx % 4 === 3 ? <LightLeak at={segF} dur={18} color={SA.b} /> : null}
      {seg ? <AbsoluteFill style={{ background: "#fff", opacity: flash, mixBlendMode: "overlay" }} /> : null}
      <Captions segments={segments} variant="outline" anchor="bottom" size={0.085} />
      <Grain opacity={0.05} />
      <ProgressBar color={SA.b} />
      {!props.mediaSrc ? <Hint text="ارفع مقطع فيديو أولاً ثم فرّغ الصوت" /> : (!segments.length ? <Hint text="اضغط «تفريغ الصوت» لتظهر الترجمة" /> : null)}
    </AbsoluteFill>
  );
};
'''
for n, c in [('showcase', TPL_SHOWCASE), ('captions', TPL_CAPTIONS), ('videoedit', TPL_VIDEO), ('voiceover', TPL_VOICEOVER)]:
    open(f'src/tpl_{n}.tsx', 'w', encoding='utf-8').write(c)

# ===================== الخادم (app.py) =====================
APP = r'''
import os, re, json, uuid, threading, subprocess, shutil, time, glob, signal, tempfile, logging, importlib.util, hmac, zipfile, mimetypes, sys
from flask import Flask, request, jsonify, send_file, send_from_directory, abort, g
import requests
import sa_audio, sa_tts
PLATFORM = None

W = os.path.abspath(os.path.dirname(__file__))
VERSION = "11.0"
app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024

# ---- إعدادات الرندر السحابي + مفتاح الدخول (تأتي من متغيرات البيئة، لا تُكتب في أي ملف)
GH_TOKEN = os.environ.get("GH_TOKEN", "").strip()
GH_REPO = os.environ.get("GH_REPO", "").strip()
GH_REF = os.environ.get("GH_REF", "main")
GH_WORKFLOW = os.environ.get("GH_WORKFLOW", "render.yml")
GH_API = os.environ.get("GH_API_URL", "https://api.github.com").rstrip("/")
GH_UPLOADS = os.environ.get("GH_UPLOADS_URL", "https://uploads.github.com").rstrip("/")
try: CLOUD_CHUNKS = max(1, min(20, int(os.environ.get("SA_CLOUD_CHUNKS", "12"))))
except Exception: CLOUD_CHUNKS = 12
SA_KEY = os.environ.get("SA_KEY", "")

JOBS, PROCS, _models, UPLOADS, RECV = {}, {}, {}, {}, {}
LOCK, ULOCK, MLOCK, DLOCK = threading.Lock(), threading.Lock(), threading.Lock(), threading.Lock()
SYNTH = json.load(open(f"{W}/sfx_synth.json"))
META = f"{W}/uploads/media.json"
ALLOWED_PKGS = {"lucide-react", "react-icons", "lodash", "d3", "three", "@react-three/fiber", "@react-three/drei", "gsap", "chroma-js", "polished", "simplex-noise"}

_AR = {ord(c): str(i) for i, c in enumerate("\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669")}
_AR.update({ord(c): str(i) for i, c in enumerate("\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9")})
def num(v, d=0.0):
    if isinstance(v, bool): return d
    if isinstance(v, (int, float)): return float(v) if v == v else d
    try:
        s = str(v).strip().translate(_AR)
        for ch in ("\u066b", "\u066c", ",", "\u060c"): s = s.replace(ch, ".")
        s = re.sub(r"[^0-9.\-]", "", s)
        p = s.split(".")
        if len(p) > 2: s = p[0] + "." + "".join(p[1:])
        return float(s)
    except Exception:
        return d

def run(cmd, cwd=None, timeout=900):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "انتهت المهلة"
    except Exception as e:
        return 1, str(e)

def has_gpu():
    try: return subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0
    except Exception: return False
GPU = has_gpu()

def pkg_ver(name):
    try: return json.load(open(f"{W}/node_modules/{name}/package.json"))["version"]
    except Exception: return None
RV = pkg_ver("remotion") or "?"

def load_meta():
    try: return json.load(open(META, encoding="utf-8"))
    except Exception: return {}
def save_meta(m):
    with DLOCK:
        tmp = META + ".tmp"
        json.dump(m, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, META)
MEDIA = load_meta()

def _cur_uid():
    try: return PLATFORM.uid() if PLATFORM else ""
    except Exception: return ""

def job(**kw):
    jid = uuid.uuid4().hex[:12]; JOBS[jid] = {"status": "processing", "progress": 0, "created": time.time(), "owner": _cur_uid(), **kw}; return jid

TTL_MEDIA_H = float(os.environ.get("SA_MEDIA_TTL_H", "24"))
TTL_OUT_H = float(os.environ.get("SA_OUT_TTL_H", "6"))
SFX_CACHE_MAX = 60 * 1024 * 1024

def _fsize(p):
    try:
        if os.path.isdir(p) and not os.path.islink(p):
            tot = 0
            for r, _, fs in os.walk(p):
                for f in fs:
                    try: tot += os.path.getsize(os.path.join(r, f))
                    except OSError: pass
            return tot
        return os.path.getsize(p)
    except OSError:
        return 0

def _rm(p):
    s = _fsize(p)
    try:
        if os.path.isdir(p) and not os.path.islink(p): shutil.rmtree(p, ignore_errors=True)
        else: os.remove(p)
    except OSError:
        return 0
    return s

def _age(p, now):
    try: return now - os.path.getmtime(p)
    except OSError: return 0

def render_busy():
    return any(j.get("status") == "processing" and j.get("kind") == "render" for j in list(JOBS.values()))

def tidy(full=False, wipe_media=False):
    """ينظّف كل ما ليس أساسياً: مخرجات قديمة، ملفات رفع مؤقتة، وسائط منتهية، كاش، مجلدات tmp."""
    now, freed, cnt = time.time(), 0, 0
    busy = render_busy()
    working = busy or bool(RECV) or any(j.get("status") == "processing" for j in list(JOBS.values()))
    keep = {j.get("media") for j in list(JOBS.values()) if j.get("status") == "processing" and j.get("media")}
    def kill(p):
        nonlocal freed, cnt
        freed += _rm(p); cnt += 1
    for k in [k for k, j in list(JOBS.items()) if now - j.get("created", now) > 3 * 3600 and j.get("status") != "processing"]:
        JOBS.pop(k, None)
    for uid in [u for u, jid in list(UPLOADS.items()) if jid not in JOBS]:
        UPLOADS.pop(uid, None)
    for pat in ("*.mp4", "*.jpg", "*_spec.json"):
        for f in glob.glob(f"{W}/out/{pat}"):
            a = _age(f, now)
            if a > 600 and (a > TTL_OUT_H * 3600 or (full and not busy)): kill(f)
    for d in glob.glob(f"{W}/out/*_pub"):
        a = _age(d, now)
        if (not busy and (a > 3600 or full)) or a > 3 * 3600: kill(d)
    if not working:
        for pat, ttl in ((f"{W}/uploads/*.part", 6 * 3600), (f"{W}/uploads/raw_*", 2 * 3600), (f"{W}/uploads/chk_*", 600), (f"{W}/uploads/*_cut.*", 2 * 3600)):
            for f in glob.glob(pat):
                if full or _age(f, now) > ttl: kill(f)
    for name, rec in list(MEDIA.items()):   # الملفات المؤمّنة في الخزنة: نحذف نسخة القرص فقط (كاش) والسجل يبقى ويُستعاد عند الحاجة
        base = name.rsplit(".", 1)[0]
        if name in keep or working or not rec.get("locs"): continue
        last = max(rec.get("created", now), rec.get("used", 0))
        if os.path.exists(f"{W}/public/{name}") and (wipe_media or now - last > TTL_MEDIA_H * 3600):
            kill(f"{W}/public/{name}"); kill(f"{W}/uploads/{base}_asr.wav")
    if not working:
        for f in glob.glob(f"{W}/public/m_*"):
            if os.path.basename(f) not in MEDIA and _age(f, now) > 3600: kill(f)
        for f in glob.glob(f"{W}/uploads/m_*_asr.wav"):
            pre = os.path.basename(f)[:-8]
            if not any(k.rsplit(".", 1)[0] == pre for k in MEDIA): kill(f)
    def _mt(f):
        try: return os.path.getmtime(f)
        except OSError: return 0
    files = sorted(glob.glob(f"{W}/sfx_cache/*"), key=_mt)
    tot = sum(_fsize(f) for f in files)
    while files and tot > SFX_CACHE_MAX:
        f = files.pop(0); tot -= _fsize(f); kill(f)
    for f in files:
        if _fsize(f) < 1000: kill(f)
    if not busy:
        for pat in ("/tmp/remotion-*", "/tmp/react-motion-graphics*", "/tmp/puppeteer_dev_chrome_profile-*"):
            for f in glob.glob(pat):
                if full or _age(f, now) > 3600: kill(f)
    if full and not busy:
        kill(f"{W}/node_modules/.cache"); kill(f"{W}/__pycache__"); kill(os.path.expanduser("~/.npm/_cacache"))
    for lf in (f"{W}/server.log", f"{W}/cloudflared.log"):
        if _fsize(lf) > 5 * 1024 * 1024:
            try: os.truncate(lf, 0)
            except OSError: pass
    return {"freed_mb": round(freed / 1e6, 1), "removed": cnt}

def cleanup():
    try: tidy()
    except Exception as e: print("tidy:", e, flush=True)

def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height:stream_disposition=attached_pic", "-of", "json", path],
        capture_output=True, text=True).stdout
    d = json.loads(out or "{}"); st = d.get("streams", [])
    v = next((s for s in st if s.get("codec_type") == "video" and s.get("width") and not (s.get("disposition") or {}).get("attached_pic")), None)
    a = next((s for s in st if s.get("codec_type") == "audio"), None)
    return {"duration": float(d.get("format", {}).get("duration", 0) or 0), "has_audio": a is not None, "acodec": (a or {}).get("codec_name"),
            "has_video": v is not None, "vcodec": (v or {}).get("codec_name"), "width": (v or {}).get("width"), "height": (v or {}).get("height")}

def ff(args):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True, text=True)
    if r.returncode != 0: raise RuntimeError(r.stderr[-800:])

def ff_progress(args, duration, cb):
    errf = tempfile.TemporaryFile(mode="w+")
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-nostats", "-progress", "pipe:1", *args], stdout=subprocess.PIPE, stderr=errf, text=True, bufsize=1)
    for line in p.stdout:
        mm = re.match(r"out_time_(?:us|ms)=(\d+)", line.strip())
        if mm and duration > 0: cb(min(1.0, int(mm.group(1)) / 1e6 / duration))
    p.wait()
    if p.returncode != 0:
        errf.seek(0); raise RuntimeError(errf.read()[-800:])

@app.route("/")
def home():
    r = send_from_directory(W, "index.html"); r.headers["Cache-Control"] = "no-store"; return r
@app.route("/icon.svg")
def icon(): return send_from_directory(f"{W}/public", "icon.svg")
@app.route("/api/health")
def health(): return jsonify({"ok": True, "gpu": GPU, "cpus": os.cpu_count(), "remotion": RV, "cloud": cloud_enabled(), "running": sum(1 for j in list(JOBS.values()) if j.get("status") == "processing")})
@app.route("/api/template/<name>")
def tpl(name):
    if name not in ("showcase", "captions", "videoedit", "voiceover"): abort(404)
    return open(f"{W}/src/tpl_{name}.tsx", encoding="utf-8").read(), 200, {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"}

@app.route("/api/diag")
def diag():
    node = run(["node", "-v"], timeout=20)[1].strip()
    ffv = (run(["ffmpeg", "-version"], timeout=20)[1].splitlines() or ["?"])[0]
    return jsonify({"version": VERSION, "node": node, "ffmpeg": ffv, "remotion": RV, "react": pkg_ver("react"), "react_dom": pkg_ver("react-dom"),
                    "transitions": pkg_ver("@remotion/transitions"), "esbuild": pkg_ver("esbuild"), "gpu": GPU, "cpus": os.cpu_count(),
                    "chrome": os.path.isdir(f"{W}/node_modules/.remotion"), "media": len(MEDIA),
                    "whisper": importlib.util.find_spec("faster_whisper") is not None,
                    "disk_free_gb": round(shutil.disk_usage(W).free / 1e9, 1)})

def check_syntax(code):
    tmp = f"{W}/uploads/chk_{uuid.uuid4().hex[:8]}.tsx"
    try:
        open(tmp, "w", encoding="utf-8").write(code)
        rc, out = run(["node", f"{W}/check.cjs", tmp], cwd=W, timeout=60)
        for line in reversed(out.strip().splitlines()):
            try: return json.loads(line)
            except Exception: continue
        return {"ok": True, "skipped": True}
    finally:
        try: os.remove(tmp)
        except Exception: pass

def fix_common(code):
    notes = []
    c = code.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if re.search(r"^[ \t]*```", c, re.M):
        c = re.sub(r"^[ \t]*```[a-zA-Z]*[ \t]*$\n?", "", c, flags=re.M); notes.append("حذف علامات ``` الزائدة")
    if "registerRoot" in c:
        c = re.sub(r"^[ \t]*registerRoot\s*\([^\n]*\)\s*;?[ \t]*$\n?", "", c, flags=re.M)
        c = re.sub(r"^[ \t]*import\s*\{\s*registerRoot\s*\}\s*from\s*[\"']remotion[\"'];?[ \t]*$\n?", "", c, flags=re.M)
        c = re.sub(r"\bregisterRoot\s*,\s*", "", c)
        c = re.sub(r",\s*registerRoot\b", "", c)
        if "registerRoot" in c and not re.search(r"import[^;]*\bregisterRoot\b", c):
            c = "const registerRoot = (..._a: any[]) => {};\n" + c
        notes.append("حذف registerRoot تلقائياً (الاستوديو ينشئ الجذر بنفسه)")
    return c, notes

def unclosed_quote(line):
    i, n, q, start = 0, len(line), None, -1
    while i < n:
        ch = line[i]
        if q:
            if ch == "\\": i += 2; continue
            if ch == q: q = None
        else:
            if ch == "/" and i + 1 < n and line[i + 1] == "/": break
            if ch in "\"'`": q, start = ch, i
        i += 1
    return (q, start) if q in ("'", '"') else (None, -1)

def fix_unterminated(code, line_no):
    lines = code.split("\n"); i = line_no - 1
    if not (0 <= i < len(lines)): return None
    q, s = unclosed_quote(lines[i])
    if not q and i > 0:
        q, s = unclosed_quote(lines[i - 1])
        if q: i -= 1
    if not q: return None
    cur = lines[i]
    for k in range(1, 7):
        if i + k >= len(lines): break
        cur2 = cur + "\\n" + lines[i + k].strip()
        q2, _ = unclosed_quote(cur2)
        if not q2:
            lines[i:i + k + 1] = [cur2]; return "\n".join(lines)
        cur = cur2
    lines[i] = lines[i].rstrip() + q
    return "\n".join(lines)

def repair_code(code):
    code, notes = fix_common(code)
    last, tried_quotes = None, False
    for _ in range(12):
        res = check_syntax(code)
        if res.get("ok"): return code, notes, None
        e = (res.get("errors") or [{}])[0]; last = e
        txt, line = e.get("text", ""), int(e.get("line") or 0)
        fixed, label = None, ""
        if "Unterminated string" in txt and line:
            fixed, label = fix_unterminated(code, line), "إغلاق نص ناقص"
        elif not tried_quotes and re.search("[\u201c\u201d\u2018\u2019]", code):
            tried_quotes = True
            fixed = code.translate({0x201c: 34, 0x201d: 34, 0x2018: 39, 0x2019: 39}); label = "استبدال علامات الاقتباس الذكية"
        if not fixed or fixed == code: break
        code = fixed; notes.append(f"إصلاح تلقائي: {label} (سطر {line})")
    return code, notes, last

def format_err(e, code):
    if not e: return ""
    line = int(e.get("line") or 0); lines = code.split("\n"); out = [f"خطأ في صياغة الكود — سطر {line}: {e.get('text', '')}"]
    for n in range(max(1, line - 2), min(len(lines), line + 2) + 1):
        out.append(f"{'>>' if n == line else '  '} {n:>4} | {lines[n - 1][:140]}")
    return "\n".join(out)

@app.route("/api/check", methods=["POST"])
def check():
    code = (request.json or {}).get("code", "")
    if not code.strip(): return jsonify({"ok": False, "notes": [], "code": code, "error": "الكود فارغ"})
    fixed, notes, err = repair_code(code)
    return jsonify({"ok": err is None, "notes": notes, "code": fixed, "error": format_err(err, fixed)})

def pkg_of(mod):
    parts = mod.split("/")
    return "/".join(parts[:2]) if mod.startswith("@") else parts[0]

def ensure_packages(code, J):
    mods = set(re.findall(r"(?:from|import)\s*\(?\s*[\"']([^\"'./][^\"']*)[\"']", code))
    missing = []
    for m in sorted(mods):
        p = pkg_of(m)
        if p in ("react", "react-dom", "remotion") or os.path.exists(f"{W}/node_modules/{p}/package.json"): continue
        if not re.fullmatch(r"(@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*", p): continue
        if p.startswith("@remotion/") or p in ALLOWED_PKGS:
            J.update(stage=f"تثبيت حزمة {p}", progress=1)
            spec = f"{p}@{RV}" if p.startswith("@remotion/") and RV != "?" else p
            run(["npm", "install", "--no-audit", "--no-fund", "--loglevel=error", "--legacy-peer-deps", spec], cwd=W, timeout=400)
        if not os.path.exists(f"{W}/node_modules/{p}/package.json"): missing.append(p)
    return missing

def heal_react(J):
    J.update(stage="إصلاح الاعتماديات تلقائياً", progress=2)
    run(["npm", "install", "--no-audit", "--no-fund", "--loglevel=error", "--legacy-peer-deps", "react@19", "react-dom@19"], cwd=W, timeout=600)
    shutil.rmtree(f"{W}/node_modules/.cache", ignore_errors=True)

def finalize_media(J, src, original, base):
    J.update(stage="فحص الملف", progress=5)
    info = probe(src)
    if info["duration"] <= 0: raise RuntimeError("ملف غير صالح أو تالف")
    if info["has_video"]:
        out = f"{W}/public/m_{base}.mp4"
        big = max(info["width"] or 0, info["height"] or 0) > 1920
        simple = False  # always normalise: constant fps + dense keyframes (no black frames, fast seeking in parallel chunks)
        if simple:
            J.update(stage="تجهيز", progress=40)
            ff(["-i", src, "-c", "copy", "-movflags", "+faststart", out])
        else:
            J.update(stage="تحويل الفيديو", progress=10)
            vf = ["-vf", ("fps=30," + ("scale='if(gt(iw,ih),min(iw,1920),-2)':'if(gt(iw,ih),-2,min(ih,1920))'," if big else "") + "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p")]
            ff_progress(["-i", src, *vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-x264-params", "keyint=30:min-keyint=30:scenecut=0", "-pix_fmt", "yuv420p",
                         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out], info["duration"],
                        lambda p: J.update(progress=10 + int(p * 70)))
        typ = "video"
    else:
        out = f"{W}/public/m_{base}.m4a"; J.update(stage="تحويل الصوت", progress=30)
        ff(["-i", src, "-vn", "-c:a", "aac", "-b:a", "192k", out]); typ = "audio"
    if info["has_audio"]:
        J.update(stage="تجهيز التفريغ", progress=88)
        ff(["-i", out, "-vn", "-ac", "1", "-ar", "16000", f"{W}/uploads/m_{base}_asr.wav"])
    fi = probe(out)
    rec = {"file": os.path.basename(out), "original": original, "type": typ, "duration": fi["duration"],
           "has_audio": fi["has_audio"], "width": fi["width"], "height": fi["height"], "created": time.time()}
    if PLATFORM: PLATFORM.media_created(rec, J.get("owner"))
    MEDIA[rec["file"]] = rec; save_meta(MEDIA)
    return rec

def process_upload(jid, raw, original):
    J = JOBS[jid]; base = uuid.uuid4().hex[:10]
    J.update(stage='بانتظار الدور')
    try:
        MEDIA_SEM.acquire()
        rec = finalize_media(J, raw, original, base)
        J.update(status="done", progress=100, result=rec)
    except Exception as e:
        J.update(status="error", error=str(e))
    finally:
        MEDIA_SEM.release()
        try: os.remove(raw)
        except Exception: pass

@app.route("/api/upload", methods=["POST"])
def upload():
    uid = request.form.get("uid", ""); ch = request.files.get("chunk")
    try: idx, total, size = int(request.form["idx"]), int(request.form["total"]), int(request.form["size"])
    except Exception: return "بيانات غير صالحة", 400
    if not re.fullmatch(r"[a-z0-9]{6,30}", uid) or not ch or total > 4000 or idx < 0 or idx >= total or size <= 0 or size > 64 * 1024 * 1024:
        return "بيانات غير صالحة", 400
    original = (request.form.get("name") or "file")[:200]
    if idx == 0 and PLATFORM:
        _e = PLATFORM.upload_guard(total * size)
        if _e: return _e, 403
    ext = os.path.splitext(original)[1].lower()[:6]
    if not re.fullmatch(r"\.[a-z0-9]+", ext or ""): ext = ".bin"
    part = f"{W}/uploads/up_{uid}.part"
    with ULOCK:
        if uid in UPLOADS: return jsonify({"job_id": UPLOADS[uid]})
        if idx == 0: cleanup()
        with open(part, "r+b" if os.path.exists(part) else "w+b") as fh:
            fh.seek(idx * size); fh.write(ch.read())
        RECV.setdefault(uid, set()).add(idx)
        if len(RECV[uid]) < total: return jsonify({"ok": True})
        raw = f"{W}/uploads/raw_{uid}{ext}"; os.replace(part, raw); RECV.pop(uid, None)
        jid = job(kind="upload", stage="بدء"); UPLOADS[uid] = jid
        if PLATFORM: PLATFORM.audit("upload", PLATFORM.uid(), "", original[:60], PLATFORM.ip())
    threading.Thread(target=process_upload, args=(jid, raw, original), daemon=True).start()
    return jsonify({"job_id": jid})

def cut_task(jid, name, th, msil=0.45):
    J = JOBS[jid]
    try:
        src = f"{W}/public/{name}"; rec0 = MEDIA.get(name, {}); info = probe(src); dur = info["duration"]
        if not info["has_audio"]: raise RuntimeError("الملف لا يحتوي على صوت لقص الصمت")
        J.update(stage="كشف الصمت", progress=5)
        r = subprocess.run(["ffmpeg", "-v", "info", "-i", src, "-af", f"silencedetect=noise={th}dB:d={msil:.2f}", "-f", "null", "-"], capture_output=True, text=True)
        starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
        ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
        sil = list(zip(starts, ends + [dur] * (len(starts) - len(ends))))
        keep, cur, pad = [], 0.0, 0.08
        for s, e in sil:
            if s + pad - cur > 0.15: keep.append((cur, s + pad))
            cur = max(cur, e - pad)
        if dur - cur > 0.15: keep.append((cur, dur))
        if not sil or not keep: raise RuntimeError("لم يُكتشف صمت كافٍ للقص — جرّب حساسية أعلى")
        removed = dur - sum(e - s for s, e in keep)
        fl, lab = [], ""
        for i, (s, e) in enumerate(keep):
            if info["has_video"]:
                fl.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]"); lab += f"[v{i}]"
            fl.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]"); lab += f"[a{i}]"
        n = len(keep); v = 1 if info["has_video"] else 0
        fl.append(f"{lab}concat=n={n}:v={v}:a=1" + ("[ov][oa]" if v else "[oa]"))
        fscript = f"{W}/uploads/{jid}_cut.txt"; open(fscript, "w").write(";\n".join(fl))
        tmp = f"{W}/uploads/{jid}_cut." + ("mp4" if v else "m4a")
        args = ["-i", src, "-filter_complex_script", fscript] + (["-map", "[ov]"] if v else []) + ["-map", "[oa]"]
        args += (["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"] if v else []) + ["-c:a", "aac", "-b:a", "192k", tmp]
        J.update(stage="القص والدمج", progress=15)
        ff_progress(args, dur - removed, lambda p: J.update(progress=15 + int(p * 70)))
        rec = finalize_media(J, tmp, "✂ " + rec0.get("original", name), uuid.uuid4().hex[:10])
        os.remove(tmp); os.remove(fscript)
        rec = dict(rec, removed=removed)
        J.update(status="done", progress=100, result=rec)
    except Exception as e:
        J.update(status="error", error=str(e))

@app.route("/api/cut_silence", methods=["POST"])
def cut_silence():
    d = request.json or {}; name = os.path.basename(d.get("file", "") or "")
    _e = PLATFORM.media_access(name)
    if _e: return _e, 400
    try: th = max(-60, min(-15, int(round(num(d.get("th"), -35)))))
    except Exception: th = -35
    msil = max(0.15, min(3.0, num(d.get("min_sil"), 0.45)))
    jid = job(kind="cut", stage="بدء")
    threading.Thread(target=cut_task, args=(jid, name, th, msil), daemon=True).start()
    return jsonify({"job_id": jid})

def pick_sfx(text, i):
    if re.search(r"[؟?]", text): return "ding"
    if "!" in text: return "impact"
    if re.search(r"\d", text): return "pop"
    if i == 0: return "rise"
    return "whoosh" if i % 3 == 0 else None

def build_segments(words, max_words, max_gap=0.6):
    segs, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > max_gap or re.search(r"[.!?؟،,؛]$", cur[-1]["text"])):
            segs.append(cur); cur = []
        cur.append(w)
    if cur: segs.append(cur)
    out = []
    for i, s in enumerate(segs):
        tx = " ".join(x["text"] for x in s)
        out.append({"text": tx, "start": s[0]["start"], "end": s[-1]["end"], "words": s, "sfx": pick_sfx(tx, i)})
    return out

@app.route("/api/segments", methods=["POST"])
def segments():
    d = request.json or {}
    try: mw = max(1, min(10, int(d.get("max_words", 3))))
    except Exception: mw = 3
    segs = build_segments(d.get("words") or [], mw)
    name = os.path.basename(d.get("file") or "")
    if name in MEDIA and PLATFORM.owns(name): MEDIA[name]["segments"] = segs; save_meta(MEDIA)
    return jsonify({"segments": segs})

def get_model(name, device):
    key = (name, device)
    with MLOCK:
        if key not in _models:
            from faster_whisper import WhisperModel
            _models[key] = WhisperModel(name, device=device, compute_type="float16" if device == "cuda" else "int8", cpu_threads=os.cpu_count() or 2)
        return _models[key]

def run_asr(jid, path, lang, model_name, device):
    J = JOBS[jid]; J.update(stage=f"تحميل النموذج ({device})", progress=3)
    m = get_model(model_name, device); J.update(stage="تفريغ")
    segs, info = m.transcribe(path, language=lang or None, word_timestamps=True, beam_size=5, vad_filter=True,
                              vad_parameters={"min_silence_duration_ms": 400}, condition_on_previous_text=False)
    words, total = [], max(info.duration, 0.1)
    for s in segs:
        for w in (s.words or []):
            t = w.word.strip()
            if t: words.append({"text": t, "start": round(float(w.start), 3), "end": round(float(w.end), 3)})
        J["progress"] = min(99, int(s.end / total * 100))
    for w in words:
        if w["end"] <= w["start"]: w["end"] = round(w["start"] + 0.15, 3)
    return words, info.language

ASR_SEM = threading.Semaphore(int(os.environ.get('SA_ASR_SLOTS', '2')))
MEDIA_SEM = threading.Semaphore(int(os.environ.get('SA_MEDIA_SLOTS', '3')))
def transcribe_task(jid, path, lang, model_name, mw, name):
    JOBS[jid].update(stage='بانتظار الدور')
    with ASR_SEM: _transcribe_task(jid, path, lang, model_name, mw, name)
def _transcribe_task(jid, path, lang, model_name, mw, name):
    try:
        words, language, dev = None, None, "CPU"
        try:
            _g = sa_tts.groq_words(PLATFORM, path, lang) if (PLATFORM and words is None) else None
            if _g and _g[0]: words, language = _g; dev = "Groq"
        except Exception as e: print("Groq ASR failed:", e, flush=True)
        if GPU and words is None:
            try: words, language = run_asr(jid, path, lang, model_name, "cuda"); dev = "GPU"
            except Exception as e: print("GPU ASR failed:", e, flush=True); _models.pop((model_name, "cuda"), None)
        if words is None: words, language = run_asr(jid, path, lang, model_name, "cpu")
        segs = build_segments(words, mw)
        if name in MEDIA: MEDIA[name].update(words=words, segments=segs); save_meta(MEDIA)
        JOBS[jid].update(status="done", progress=100, result={"words": words, "segments": segs, "language": language, "device": dev})
    except Exception as e:
        JOBS[jid].update(status="error", error=f"{type(e).__name__}: {e}")

@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    d = request.json or {}; name = os.path.basename(d.get("file", "") or ""); base = name.rsplit(".", 1)[0]
    _e = PLATFORM.media_access(name)
    if _e: return _e, 400
    _e = PLATFORM.can_asr(name)
    if _e: return _e, 429
    path = f"{W}/uploads/{base}_asr.wav"
    if not os.path.exists(path): path = f"{W}/public/{name}"
    if not name or not os.path.exists(path): return "الملف غير موجود، ارفعه مرة أخرى", 400
    model = d.get("model") if d.get("model") in ("small", "medium", "large-v3") else "medium"
    try: mw = max(1, min(10, int(d.get("max_words", 3))))
    except Exception: mw = 3
    jid = job(kind="asr", stage="بدء")
    threading.Thread(target=transcribe_task, args=(jid, path, d.get("lang") or "", model, mw, name), daemon=True).start()
    return jsonify({"job_id": jid})

SFX_QUERY = {"whoosh": "whoosh swoosh transition", "pop": "pop bubble ui", "impact": "cinematic impact hit", "rise": "riser swell",
             "ding": "ding notification bell", "typing": "keyboard typing", "click": "ui click", "bass": "bass drop sub boom", "glitch": "glitch digital",
             "shine": "sparkle shine magic", "tick": "clock tick"}

FS_BASES = ("https://freesound.org/apiv2/search/text/", "https://freesound.org/apiv2/search/")

def fs_search(kind, key):
    params = {"query": SFX_QUERY.get(kind, kind), "filter": "duration:[0.1 TO 3]", "sort": "score",
              "fields": "id,name,previews,username", "page_size": 8}
    last = "لا استجابة"
    for base in FS_BASES:
        try:
            r = requests.get(base, timeout=15, params={**params, "token": key},
                             headers={"Authorization": "Token " + key, "User-Agent": "SA-Motion-Studio/9"})
        except requests.RequestException as e:
            last = f"تعذّر الاتصال: {e}"; continue
        if r.status_code == 404:
            last = "HTTP 404"; continue
        if r.status_code != 200:
            try: det = r.json().get("detail", "")
            except Exception: det = r.text[:200]
            raise RuntimeError(f"HTTP {r.status_code} {det}")
        return r.json().get("results", [])
    raise RuntimeError(last)

@app.route("/api/fs_test", methods=["POST"])
def fs_test():
    key = ((request.json or {}).get("key") or "").strip()
    if not key: return jsonify({"ok": False, "msg": "أدخل المفتاح أولاً"})
    try:
        res = fs_search("whoosh", key)
        return jsonify({"ok": True, "msg": f"المفتاح يعمل ✓ ({len(res)} نتيجة)"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"فشل: {e} — 401 يعني مفتاح خاطئ، 429 تجاوز الحد"})

def local_sfx(kind):
    p = f"{W}/public/audio/{kind}.mp3"
    if (not os.path.exists(p) or os.path.getsize(p) < 500) and SYNTH.get(kind):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", SYNTH[kind], "-ar", "48000", "-ac", "2", "-b:a", "192k", p], capture_output=True)
    return p

FS_DOWN = {"until": 0.0, "why": ""}

def get_sfx(kind, key, variant):
    if kind not in SYNTH: kind = "whoosh"
    key = (key or "").strip()
    if key and time.time() < FS_DOWN["until"]:
        return local_sfx(kind), "محلي (Freesound متوقف مؤقتاً: " + FS_DOWN["why"] + ")"
    if key:
        fn = f"{W}/sfx_cache/fs_{kind}_{variant}.mp3"
        if os.path.exists(fn) and os.path.getsize(fn) > 1000: return fn, "Freesound (cache)"
        try:
            res = fs_search(kind, key)
            if res:
                s = res[variant % len(res)]
                pv = s.get("previews") or {}
                url = pv.get("preview-hq-mp3") or pv.get("preview-lq-mp3")
                a = requests.get(url, timeout=20) if url else None
                if a is not None and a.ok and len(a.content) > 1000:
                    open(fn, "wb").write(a.content); return fn, f"Freesound #{s['id']} by {s['username']}"
            return local_sfx(kind), "محلي (لا نتائج في Freesound)"
        except Exception as e:
            if re.search(r"HTTP (401|403|429)", str(e)): FS_DOWN.update(until=time.time() + 600, why=str(e)[:80])
            return local_sfx(kind), f"محلي (Freesound: {e})"
    return local_sfx(kind), "مولّد محلياً"

def mix_audio(video, out, duration, voice, sfx_list):
    vinfo = probe(video)
    inputs = ["-i", video]
    filters, labels = [], []
    idx = 1
    if vinfo["has_audio"]:
        filters.append("[0:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[b]")
        labels.append("[b]")
    else:
        inputs += ["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        filters.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo[b]")
        labels.append("[b]")
        idx += 1
    if voice and os.path.exists(voice):
        inputs += ["-i", voice]
        filters.append(f"[{idx}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,apad[v0]")
        labels.append("[v0]"); idx += 1
    for i, (path, t, v) in enumerate(sfx_list):
        if not os.path.exists(path): continue
        ms = max(0, int(t * 1000)); inputs += ["-i", path]
        filters.append(f"[{idx}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,volume={v:.3f},adelay={ms}|{ms},apad[s{i}]")
        labels.append(f"[s{i}]"); idx += 1
    n = len(labels)
    filters.append(f"{''.join(labels)}amix=inputs={n}:duration=first:dropout_transition=0,volume={n},alimiter=limit=0.95[a]")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[a]",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-t", f"{duration:.3f}", "-movflags", "+faststart", out], capture_output=True, text=True)
    if r.returncode != 0: raise RuntimeError("ffmpeg mix: " + r.stderr[-800:])

def code_sfx(code, duration):
    m = re.search(r"export\s+const\s+SFX\s*(?::[^=]+)?=\s*\[([\s\S]*?)\]\s*;?", code)
    if not m: return None
    out = []
    for obj in re.findall(r"\{([^}]*)\}", m.group(1)):
        t = re.search(r"\bt\s*:\s*([\d.]+)", obj); rt = re.search(r"\brt\s*:\s*([\d.]+)", obj)
        k = re.search(r"\bkind\s*:\s*[\"']([a-z]+)[\"']", obj); v = re.search(r"\bvol(?:ume)?\s*:\s*([\d.]+)", obj)
        if k and (t or rt):
            try:
                tt = float(t.group(1)) if t else float(rt.group(1)) * duration
                out.append({"t": tt, "kind": k.group(1), "vol": float(v.group(1)) if v else 1.0})
            except ValueError: pass
    return out

def kill_proc(p):
    try: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except Exception:
        try: p.kill()
        except Exception: pass

def prepare_public(jid, mfile=None, mtype=None, files=None):
    pub = f"{W}/out/{jid}_pub"
    def link(src, dst):
        try: os.link(src, dst)
        except Exception: shutil.copy2(src, dst)
    shutil.copytree(f"{W}/public", pub, copy_function=link, dirs_exist_ok=True)
    if mfile and os.path.exists(f"{pub}/{mfile}"):
        ext = os.path.splitext(mfile)[1]
        for alias in ([f"current_media{ext}"] + (["current_video.mp4"] if mtype == "video" else [])):
            try: link(f"{pub}/{mfile}", f"{pub}/{alias}")
            except Exception: pass
    nv = na = 0
    for f in (files or []):
        fn = f.get("file")
        if not fn or not os.path.exists(f"{pub}/{fn}"): continue
        ext = os.path.splitext(fn)[1]
        if f.get("type") == "video":
            nv += 1; al = "current_video.mp4" if nv == 1 else f"current_video_{nv}.mp4"
        else:
            na += 1; al = f"current_audio{ext}" if na == 1 else f"current_audio_{na}{ext}"
        if not os.path.exists(f"{pub}/{al}"):
            try: link(f"{pub}/{fn}", f"{pub}/{al}")
            except Exception: pass
    return pub

MEDIA_USE = re.compile(r"mediaSrc|videoSrc|audioSrc|mediaUrl|mediaFile|useSAMedia|useSAClips|VideoClips|props\.clips|props\.videos|props\.audios|MediaVideo|VideoBg|<Stage\b|getInputProps|current_media|current_video|\bm_[a-z0-9]+\.(?:mp4|m4a)")

def code_has_audio(code):
    """هل كود التصميم نفسه يشغّل صوتاً (Audio أو فيديو غير مكتوم)؟ لتفادي تكرار الصوت عند الدمج."""
    if re.search(r"<\s*Audio\b", code): return True
    for tag in re.findall(r"<\s*(?:OffthreadVideo|Video)\b[^>]*>?", code):
        if not re.search(r"\bmuted\b", tag): return True
    return False


def black_check(path, duration):
    """sample ~8 frames: (mean luma 0-255, brightest pixel) — None when it cannot be measured"""
    try:
        fps = max(0.05, min(2.0, 8.0 / max(duration, 1.0)))
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={fps:.4f},scale=160:-2,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-", "-an", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=120)
        v = [float(x) for x in re.findall(r"YAVG=([\d.]+)", r.stdout)]
        return (sum(v) / len(v), max(v)) if v else None
    except Exception:
        return None

def black_warning(final, duration, mfile, mtype, code, segs, rec):
    m = black_check(final, duration)
    if not m or m[1] > 22:
        return None
    why = []
    if not mfile and MEDIA_USE.search(code or ""):
        why.append("الكود يعرض ملفاً لكنك لم تختر ملفاً في الاستوديو (اختر ملفاً من المكتبة قبل الرندر)")
    if mfile and mtype == "video":
        src = f"{W}/public/{mfile}"
        sm = black_check(src, min(float(rec.get('duration') or 10), 20)) if os.path.exists(src) else None
        if sm and sm[1] <= 22:
            why.append("الفيديو المرفوع نفسه داكن/أسود")
        elif sm:
            why.append("الفيديو المرفوع سليم، فالمشكلة في كود التصميم: تأكد أنه يعرض mediaSrc داخل Stage/MediaVideo")
    if not segs and re.search(r"segments|Captions|Kinetic|words", code or ""):
        why.append("لا يوجد تفريغ نصي (segments فارغة) فلا يوجد ما يُرسم فوق الخلفية الداكنة؛ اضغط «تفريغ» أو فعّل التفريغ التلقائي")
    if not why:
        why.append("الكود يرسم خلفية داكنة فقط؛ راجع الألوان/العناصر أو جرّب معاينة إطار (Still) عند ثانية لاحقة")
    return "⚠ الفيديو الناتج يبدو أسود (متوسط السطوع %.0f/255). الأسباب المحتملة: " % m[0] + "؛ ".join(why) + "."

def media_warnings(code, mfile, mtype, carries, voice_on):
    w = []
    if not mfile: return w
    if carries and voice_on:
        w.append("الكود يشغّل الصوت بنفسه (Audio/Video) فلم يُدمج صوت الملف تلقائياً لتفادي التكرار.")
    elif not (MEDIA_USE.search(code) or carries):
        w.append("كود التصميم لا يقرأ الملف المرفوع (لا mediaSrc ولا Stage/MediaVideo)، لذلك لن يظهر الفيديو داخل التصميم. "
                 + ("صوت الملف سيُدمج تلقائياً." if voice_on else "ودمج الصوت معطّل أيضاً."))
    return w

def hint_for(msg):
    h = []
    if "__CLIENT_INTERNALS" in msg or "React2" in msg: h.append("تعارض إصدار React — حاول الاستوديو إصلاحه تلقائياً؛ أعد تشغيل السكربت إن تكرر.")
    if "Can't resolve" in msg or "Module not found" in msg: h.append("حزمة أو ملف مستورد غير موجود. استخدم ./sa_kit أو remotion أو @remotion/* فقط.")
    if "404" in msg: h.append("ملف مطلوب غير موجود في public. المؤثرات المتاحة: " + ", ".join(f"audio/{k}.mp3" for k in SYNTH) + " + ملفاتك المرفوعة.")
    if re.search(r"Target closed|Protocol error|out of memory|Aborted|SIGKILL", msg): h.append("المتصفح انهار بسبب الذاكرة — قلّل الدقة أو FPS أو المدة ثم أعد المحاولة.")
    if re.search(r"Timed out|delayRender", msg): h.append("انتهت مهلة تحميل مورد (خط أو فيديو) — أعد المحاولة، وتأكد من اتصال الإنترنت.")
    return ("\n\nتلميح: " + " ".join(h)) if h else ""

def run_node_render(jid, sfile, J):
    p = subprocess.Popen(["node", f"{W}/render.cjs", sfile], cwd=W, env={k: v for k, v in os.environ.items() if k not in ("SA_MASTER", "ADMIN_PASS", "ADMIN_EMAIL", "GH_TOKEN", "TG_BOT_TOKEN", "TG_CHAT_ID", "TG_STORAGE_CHAT", "SA_KEY")}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
    PROCS[jid] = p; tail, blogs, err = [], [], None
    t0 = time.time()
    for line in p.stdout:
        line = line.rstrip()
        if not line.startswith("@@"):
            if line.strip(): tail.append(line); tail = tail[-60:]
            continue
        try: ev = json.loads(line[2:])
        except Exception: continue
        st = ev.get("stage")
        if st == "bundle":
            bp = int(ev.get("progress", 0) or 0); J.update(stage="تجميع الكود", progress=1 + int(bp * 0.07), details=f"bundle {bp}%")
        elif st == "compose": J.update(stage="تحميل الخطوط والتكوين", progress=9, details="")
        elif st == "render":
            pr = float(ev.get("progress", 0) or 0); el = time.time() - t0
            eta = f" · متبقٍ ~{int(el / pr - el)}ث" if pr > 0.05 else ""
            J.update(stage="دمج" if ev.get("stitch") == "muxing" else "رندر الإطارات", progress=10 + int(pr * 80),
                     details=f"{ev.get('rendered', 0)} / {ev.get('total', 0)} إطار{eta}")
        elif st == "log": blogs.append(ev.get("text", "")); J["logs"] = blogs[-10:]
        elif st == "error": err = ev.get("text", "")
    p.wait()
    return p.returncode, err, tail

def render_task(jid, d):
    J = JOBS[jid]; mode = d["mode"]; pub = None
    cfg = d["config"]; fps = cfg["fps"]; frames = cfg["frames"]; duration = frames / fps
    sfile = f"{W}/out/{jid}_spec.json"
    out = f"{W}/out/{jid}.jpg" if mode == "still" else f"{W}/out/{jid}_raw.mp4"
    try:
        media = d.get("media") or {}
        # كل الملفات المختارة (فيديو + صوت، أو أكثر من مقطع) — لا يُستبدل أحدها بالآخر
        _raw = d.get("medias") if isinstance(d.get("medias"), list) and d.get("medias") else ([media] if media.get("file") else [])
        _seen, files = set(), []
        for _m in _raw[:6]:
            fn = os.path.basename((_m or {}).get("file", "") or "")
            if not fn or fn in _seen: continue
            _seen.add(fn)
            if not PLATFORM.ensure_local(fn):
                raise RuntimeError("MEDIA_MISSING: تعذّرت استعادة الملف من التخزين الآمن. ارفعه مرة أخرى.")
            _r = MEDIA.get(fn) or {}
            if _r: _r["used"] = time.time()
            files.append({"file": fn, "type": _r.get("type") or (_m or {}).get("type") or ("audio" if fn.endswith((".m4a", ".mp3", ".wav")) else "video"),
                          "duration": float(_r.get("duration") or (_m or {}).get("duration") or 0),
                          "has_audio": bool(_r.get("has_audio", (_m or {}).get("has_audio", True))),
                          "width": _r.get("width") or (_m or {}).get("width"), "height": _r.get("height") or (_m or {}).get("height"),
                          "original": _r.get("original") or (_m or {}).get("original") or fn})
        vids = [f for f in files if f["type"] == "video"]; auds = [f for f in files if f["type"] == "audio"]
        prim = vids[0] if vids else (auds[0] if auds else None)      # الصورة: أول فيديو، وإلا الصوت
        speech = auds[0] if auds else (vids[0] if vids else None)    # الكلام: ملف الصوت المرفوع أولاً، وإلا صوت الفيديو
        mfile = prim["file"] if prim else ""
        rec = MEDIA.get(mfile) or {}
        srec = MEDIA.get(speech["file"]) if speech else {}
        srec = srec or {}
        mdur = prim["duration"] if prim else 0
        mtype = prim["type"] if prim else None
        J["media"] = mfile
        _pf = lambda f: {"src": f["file"], "file": f["file"], "type": f["type"], "duration": f["duration"], "hasAudio": f["has_audio"], "width": f["width"], "height": f["height"], "original": f["original"]}
        props = {"words": d.get("words") or srec.get("words") or [], "segments": d.get("segments") or srec.get("segments") or [], "scenes": srec.get("scenes") or rec.get("scenes") or [], "mediaSrc": mfile or None,
                 "mediaType": mtype, "mediaDuration": mdur, "duration": duration, "hasMedia": bool(files)}
        if files:
            props.update(videoSrc=vids[0]["file"] if vids else None, audioSrc=auds[0]["file"] if auds else mfile, src=mfile, mediaUrl=mfile, mediaFile=mfile,
                         media={"src": mfile, "type": mtype, "duration": mdur},
                         files=[_pf(f) for f in files], videos=[_pf(f) for f in vids], clips=[_pf(f) for f in vids], audios=[_pf(f) for f in auds],
                         videoDuration=vids[0]["duration"] if vids else 0, audioDuration=auds[0]["duration"] if auds else 0)
        carries = code_has_audio(d.get("code", ""))
        warns = media_warnings(d.get("code", ""), mfile, mtype, carries, bool(d.get("voice", True)))
        if vids and auds:
            warns.append(f"دُمج الفيديو ({vids[0]['original']}) مع الصوت ({auds[0]['original']}): الصورة من الفيديو والصوت من الملف الصوتي" + (" (صوت الفيديو الأصلي مكتوم)." if vids[0]["has_audio"] else "."))
        elif len(vids) > 1:
            warns.append(f"{len(vids)} مقاطع مرفقة: يمرَّر الجميع للكود (props.clips) ويُشغَّل صوت الأول فقط ما لم يكتب التصميم غير ذلك.")
        use_cloud = (mode == "video") and d.get("cloud", True) is not False and cloud_enabled()
        narr = None
        _nr = sa_tts.parse_narration(d.get("code", "")) if mode == "video" else None
        if _nr:
            J.update(stage="توليد الصوت من الكود", progress=2)
            narr = sa_tts.narrate(sys.modules[__name__], PLATFORM, J, jid, _nr[0], _nr[1])
            try: PLATFORM.bump(J.get("owner"), tts_chars=narr["chars"])
            except Exception: pass
            _need = narr["end"] + 0.8
            if _need > duration + 0.01:
                _cap = float(d.get("_maxsec") or 900)
                _newd = min(_need, _cap)
                frames = int(-(-(_newd * fps) // 1)); duration = frames / fps
                cfg["frames"] = frames
                if not use_cloud:
                    with LOCK:
                        _rt = open(f"{W}/src/Root.tsx", encoding="utf-8").read()
                        _rt = re.sub(r"durationInFrames=\{\d+\}", "durationInFrames={" + str(frames) + "}", _rt)
                        open(f"{W}/src/Root.tsx", "w", encoding="utf-8").write(_rt)
                warns.append(f"مُدّدت مدة الفيديو تلقائياً إلى {duration:.1f} ثانية ليتّسع الصوت المولّد." if _newd >= _need else f"الصوت ({_need:.1f} ث) أطول من أقصى مدة في اشتراكك ({_cap:.0f} ث) فسيُقصّ.")
            props.update(duration=duration, words=narr["words"], segments=narr["segments"], scenes=narr["scenes"], narration=True)
            d["words"] = narr["words"]; d["segments"] = narr["segments"]
            for _n in narr.get("notes") or []: warns.append("الصوت: " + _n)
            if narr.get("moved"): warns.append("تعذّر وضع بعض الجمل في ثانيتها المطلوبة لأن الجملة السابقة لم تنتهِ: " + "، ".join(f"جملة {a} (طُلب {b} ← {c})" for a, b, c in narr["moved"]))
            J.update(narration={"provider": narr["provider"], "voice": narr["voice"], "seconds": narr["end"], "native_timing": narr["native"]})
        if use_cloud:
            J.update(cloud=True)
            cloud_render(jid, d, J, props, mfile, mtype, out)
            missing, spec = [], {"frame": 0}
        else:
            J.update(stage="فحص الحزم", progress=1)
            missing = ensure_packages(d.get("code", ""), J)
            J.update(stage="تجهيز الملفات", progress=1)
            if J.get("cancelled"): raise RuntimeError("تم الإلغاء")
            pub = prepare_public(jid, mfile, mtype, files)
            if J.get("cancelled"): raise RuntimeError("تم الإلغاء")
            t = num(d.get("time"), 0.0)
            spec = {"root": W, "publicDir": pub, "props": props, "mode": mode, "output": out, "crf": cfg["crf"], "preset": cfg["preset"],
                    "concurrency": max(1, min(4, os.cpu_count() or 1)), "frame": min(frames - 1, max(0, int(round(t * fps))))}
            json.dump(spec, open(sfile, "w", encoding="utf-8"), ensure_ascii=False)
            rc, err, tail = run_node_render(jid, sfile, J)
            if rc != 0 and not J.get("cancelled") and re.search(r"__CLIENT_INTERNALS|React2|__SECRET_INTERNALS", (err or "") + "\n".join(tail)):
                heal_react(J); rc, err, tail = run_node_render(jid, sfile, J)
            if J.get("cancelled"): raise RuntimeError("تم الإلغاء")
            if rc != 0 or not os.path.exists(out):
                msg = err or "\n".join(tail[-30:]) or "خطأ غير معروف"
                extra = f"\n\nحزم غير متاحة: {', '.join(missing)}" if missing else ""
                raise RuntimeError("خطأ في Remotion:\n" + msg[-4000:] + extra + hint_for(msg))
        if mode == "still":
            J.update(status="done", progress=100, result={"url": f"/api/still/{jid}", "frame": spec["frame"], "notes": d.get("notes", []), "fixed_code": d.get("fixed_code"), "warnings": warns}); return
        J.update(stage="مزج الصوت والمؤثرات", progress=92, details="")
        voice = f"{W}/public/{speech['file']}" if (speech and d.get("voice", True) and speech["has_audio"] and not carries) else None
        if narr: voice = narr["path"]
        final = f"{W}/out/{jid}.mp4"
        used, _aw, arep = sa_audio.finish(sys.modules[__name__], jid, d, J, out, final, duration, voice, props["segments"])
        warns += _aw
        _bw = black_warning(final, duration, mfile, mtype, d.get('code', ''), props['segments'], rec)
        if _bw: warns.insert(0, _bw)
        if files:
            _why = None
            if not voice:
                _why = ("«دمج صوت الملف» مُعطّل" if not d.get("voice", True) else ("الملف لا يحتوي مسار صوت" if not (speech and speech["has_audio"]) else ("الكود نفسه يشغّل الصوت" if carries else "لم يُدمج")))
            arep["voice"] = {"mixed": bool(voice), "why": _why}
        if narr: arep["voice"] = {"mixed": True, "why": None, "narration": {"provider": narr["provider"], "voice": narr["voice"], "seconds": narr["end"], "words": len(narr["words"])}}
        J.update(status="done", progress=100, result={"url": f"/api/video/{jid}", "sfx_used": used, "audio": arep, "size_mb": round(os.path.getsize(final) / 1e6, 1),
                                                      "notes": d.get("notes", []), "fixed_code": d.get("fixed_code"), "warnings": warns})
    except Exception as e:
        J.update(status="error", error=str(e))
    finally:
        PROCS.pop(jid, None)
        for f in ([sfile] + ([out] if mode != "still" else [])):
            try: os.remove(f)
            except Exception: pass
        if pub: shutil.rmtree(pub, ignore_errors=True)
        try: os.remove(f"{W}/out/{jid}_narr.wav")
        except Exception: pass

# ===================== الرندر السحابي (GitHub Actions) — الوحدة sa_cloud =====================
import sa_cloud
def cloud_enabled(): return sa_cloud.enabled(sys.modules[__name__])
def cloud_render(jid, d, J, props, mfile, mtype, out): return sa_cloud.render(sys.modules[__name__], jid, d, J, props, mfile, mtype, out)

def pick_component(code):
    names = re.findall(r"export\s+(default\s+)?(?:const|function|class)\s+([A-Z]\w*)", code)
    names = [(dflt, n) for dflt, n in names if not n.isupper()]
    if names:
        pick = next((n for n in names if n[1] in ("Motion", "MyComposition", "Main", "Video")), None) or names[0]
        return pick[1], bool(pick[0]), code
    m = re.search(r"export\s*\{([^}]*)\}", code)
    if m:
        for part in m.group(1).split(","):
            nm = part.strip().split(" as ")[-1].strip()
            if re.fullmatch(r"[A-Z]\w*", nm) and nm != "SFX": return nm, False, code
    if re.search(r"export\s+default\b", code): return "Motion", True, code
    cands = re.findall(r"(?:const|function)\s+([A-Z][A-Za-z0-9]*)\s*(?:[:=(]|<)", code)
    cands = [c for c in cands if not c.isupper()]
    if cands:
        nm = "Motion" if "Motion" in cands else cands[-1]
        return "Motion", False, code + f"\nexport {{ {nm} as Motion }};\n"
    return None, False, code

@app.route("/api/render", methods=["POST"])
def render():
    d = request.json or {}; code = d.get("code", "")
    if not code.strip(): return "الكود فارغ", 400
    mode = "still" if d.get("mode") == "still" else "video"; c = d.get("config", {}) or {}
    try:
        w = max(64, min(4096, int(num(c.get("width"), 1080)))) // 2 * 2
        h = max(64, min(4096, int(num(c.get("height"), 1920)))) // 2 * 2
        fps = max(1, min(120, int(num(c.get("fps"), 30))))
        frames = max(1, min(fps * 900, int(num(c.get("frames"), 300))))
        crf = max(10, min(35, int(num(c.get("crf"), 18))))
        preset = c.get("preset") if c.get("preset") in ("ultrafast", "veryfast", "fast", "medium", "slow") else "medium"
    except Exception: return "إعدادات غير صالحة", 400
    _g = PLATFORM.guard_render(d, w, h, fps, frames, mode)
    if _g: return _g[0], _g[1]
    _nar = sa_tts.parse_narration(code) if mode == 'video' else None
    if _nar:
        _g = PLATFORM.narration_guard(d, _nar[0])
        if _g: return _g[0], _g[1]
    fixed, notes, err = repair_code(code)
    if err: return format_err(err, fixed) + "\n\nجرّب زر «فحص وإصلاح» أو أعد تحميل قالب جاهز.", 400
    name, is_def, fixed = pick_component(fixed)
    if not name: return "لم أجد مكوناً مُصدَّراً. اكتب: export const Motion = () => ...", 400
    _sel = [m for m in (d.get("medias") or ([d.get("media")] if d.get("media") else [])) if isinstance(m, dict) and m.get("file")][:6]
    for _m in _sel:
        _e = PLATFORM.media_access(os.path.basename(_m.get("file", "")))
        if _e: return _e, 400
    cleanup()
    with LOCK:
        _busy = PLATFORM.busy_reason(d)
        if _busy: return _busy, 409
        imp = ("import " + name + " from './Composition';") if is_def else ("import { " + name + " } from './Composition';")
        open(f"{W}/src/Composition.tsx", "w", encoding="utf-8").write(fixed)
        root = ("import React from 'react';\nimport { Composition } from 'remotion';\n" + imp + "\n"
                "export const RemotionRoot: React.FC = () => (\n"
                "  <Composition id=\"MainVideo\" component={" + name + " as any} durationInFrames={" + str(frames) + "} fps={" + str(fps) +
                "} width={" + str(w) + "} height={" + str(h) + "} defaultProps={{}} />\n);\n")
        open(f"{W}/src/Root.tsx", "w", encoding="utf-8").write(root)
        open(f"{W}/src/index.ts", "w").write("import { registerRoot } from 'remotion';\nimport { RemotionRoot } from './Root';\nregisterRoot(RemotionRoot);\n")
        d["config"] = {"width": w, "height": h, "fps": fps, "frames": frames, "crf": crf, "preset": preset}; d["mode"] = mode; d["comp"] = {"name": name, "default": bool(is_def)}
        d["code"] = fixed; d["notes"] = notes; d["fixed_code"] = fixed if fixed != code.replace("\r\n", "\n") else None
        jid = job(kind="render", mode=mode, stage="بدء", details="")
        PLATFORM.render_started(jid, mode)
    threading.Thread(target=render_task, args=(jid, d), daemon=True).start()
    return jsonify({"job_id": jid})

@app.route("/api/cancel/<jid>", methods=["POST"])
def cancel(jid):
    if jid in JOBS and not PLATFORM.is_admin() and JOBS[jid].get("owner") != PLATFORM.uid(): abort(404)
    p = PROCS.get(jid)
    if jid in JOBS: JOBS[jid]["cancelled"] = True
    if p: kill_proc(p)
    return jsonify({"ok": True})

@app.route("/api/job/<jid>")
def job_status(jid):
    j = JOBS.get(jid)
    if j and not PLATFORM.is_admin() and j.get("owner") != PLATFORM.uid(): j = None
    return jsonify(PLATFORM.public_job(j)) if j else (jsonify({"status": "error", "error": "المهمة غير موجودة (ربما أُعيد تشغيل الخادم)"}), 404)

@app.route("/api/video/<jid>")
def video(jid):
    if not re.fullmatch(r"[a-f0-9]{12}", jid) or not PLATFORM.job_ok(jid): abort(404)
    path = f"{W}/out/{jid}.mp4"
    if not os.path.exists(path): abort(404)
    return send_file(path, mimetype="video/mp4", conditional=True, as_attachment=request.args.get("dl") == "1", download_name=f"SA_Motion_{jid}.mp4")

@app.route("/api/still/<jid>")
def still(jid):
    if not re.fullmatch(r"[a-f0-9]{12}", jid) or not PLATFORM.job_ok(jid): abort(404)
    path = f"{W}/out/{jid}.jpg"
    if not os.path.exists(path): abort(404)
    return send_file(path, mimetype="image/jpeg")

@app.route("/api/cleanup", methods=["POST"])
def api_cleanup():
    wipe = bool((request.json or {}).get("media"))
    if render_busy(): return "يوجد رندر قيد التنفيذ — انتظر حتى ينتهي ثم أعد التنظيف", 409
    if wipe and any(j.get("status") == "processing" for j in list(JOBS.values())):
        return "توجد مهمة قيد التنفيذ (رفع/تفريغ/قص) — انتظر حتى تنتهي", 409
    return jsonify({"ok": True, **tidy(full=True, wipe_media=wipe)})

@app.route("/api/storage")
def api_storage():
    mb = lambda p: round(_fsize(p) / 1e6, 1)
    return jsonify({"media_mb": mb(f"{W}/public") , "out_mb": mb(f"{W}/out"), "uploads_mb": mb(f"{W}/uploads"), "sfx_cache_mb": mb(f"{W}/sfx_cache"),
                    "free_gb": round(shutil.disk_usage(W).free / 1e9, 1)})

def _janitor():
    time.sleep(20)
    while True:
        cleanup()
        time.sleep(1800)
import sa_platform
PLATFORM = sa_platform.install(sys.modules[__name__])
threading.Thread(target=_janitor, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3847, threaded=True, use_reloader=False)
'''
open('app.py', 'w', encoding='utf-8').write(APP)

# ===================== تنظيف وترتيب مساحة العمل =====================
def tidy_workspace():
    import glob
    strict = os.path.isdir("/content") or os.environ.get("SA_STRICT_TIDY") == "1"
    freed = 0
    def rm(p):
        nonlocal freed
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                for r, _, fs in os.walk(p):
                    for f in fs:
                        try: freed += os.path.getsize(os.path.join(r, f))
                        except OSError: pass
                shutil.rmtree(p, ignore_errors=True)
            else:
                freed += os.path.getsize(p); os.remove(p)
        except OSError:
            pass
    if strict:  # مجلد مخصص (كولاب): لا يبقى إلا الأساسي
        keep_root = {"node_modules", "package.json", "package-lock.json", "src", "public", "out", "uploads", "sfx_cache", "index.html", "app.py",
                     "render.cjs", "check.cjs", "tsconfig.json", "remotion.config.ts", "sfx_synth.json", "cloudflared", "server.log", "cloudflared.log"}
        for n in os.listdir(W):
            if n not in keep_root: rm(f"{W}/{n}")
        keep_src = {"sa_kit.tsx", "tpl_showcase.tsx", "tpl_captions.tsx", "tpl_videoedit.tsx", "tpl_voiceover.tsx", "Composition.tsx", "Root.tsx", "index.ts"}
        for n in os.listdir(f"{W}/src"):
            if n not in keep_src: rm(f"{W}/src/{n}")
        for n in os.listdir(f"{W}/public"):
            if n in ("icon.svg", "audio") or re.fullmatch(r"m_[a-z0-9_]+\.(mp4|m4a)", n): continue
            rm(f"{W}/public/{n}")
    rm(f"{W}/__pycache__")
    for f in glob.glob(f"{W}/out/*"): rm(f)
    for pat in ("*.part", "raw_*", "chk_*", "*_cut.*", "*.tmp"):
        for f in glob.glob(f"{W}/uploads/{pat}"): rm(f)
    try: known = set(json.load(open(f"{W}/uploads/media.json", encoding="utf-8")).keys())
    except Exception: known = set()
    for f in glob.glob(f"{W}/public/m_*"):
        if os.path.basename(f) not in known: rm(f)
    for f in glob.glob(f"{W}/uploads/m_*_asr.wav"):
        pre = os.path.basename(f)[:-8]
        if not any(k.rsplit(".", 1)[0] == pre for k in known): rm(f)
    for f in glob.glob(f"{W}/sfx_cache/*"):
        try:
            if os.path.getsize(f) < 1000: rm(f)
        except OSError: pass
    print(f"🧹 تنظيف مساحة العمل: تحرير {freed / 1e6:.1f}MB" + (" (وضع صارم: بقيت الملفات الأساسية فقط)" if strict else ""))
tidy_workspace()

# ===================== فحص ذاتي للأكواد الجاهزة =====================
for n in ["sa_kit", "tpl_showcase", "tpl_captions", "tpl_videoedit", "tpl_voiceover"]:
    rc, out = sh(f"node check.cjs src/{n}.tsx")
    print(f"  فحص {n}:", "✓" if '"ok":true' in out else "⚠️ " + out[-300:])

if os.environ.get("SA_SETUP_ONLY") == "1":
    print("✅ تم تجهيز الملفات (وضع التجهيز فقط) — شغّل app.py بنفسك أو عبر خلية كولاب.")
    sys.exit(0)

# ===================== إعداد الرندر السحابي (GitHub Actions) =====================
import secrets, getpass
def _secret(name):
    v = os.environ.get(name, "").strip()
    if v: return v
    try:
        from google.colab import userdata
        return (userdata.get(name) or "").strip()
    except Exception:
        return ""
os.environ.setdefault("GH_REPO", "mnem0908/saif-ather")
_tok = _secret("GH_TOKEN")
if not _tok and ("ipykernel" in sys.modules or (sys.stdin and sys.stdin.isatty())):
    try: _tok = getpass.getpass("🔑 GitHub token (اضغط Enter للتخطي → رندر محلي): ").strip()
    except Exception: _tok = ""
if _tok: os.environ["GH_TOKEN"] = _tok
CLOUD_OK = False
if _tok:
    try:
        import requests as _rq
        _h = {"Authorization": f"Bearer {_tok}", "Accept": "application/vnd.github+json"}
        _r = _rq.get(f"https://api.github.com/repos/{os.environ['GH_REPO']}", headers=_h, timeout=20)
        _w = _rq.get(f"https://api.github.com/repos/{os.environ['GH_REPO']}/actions/workflows/render.yml", headers=_h, timeout=20)
        if _r.status_code != 200: print(f"⚠️ لا أستطيع الوصول للمستودع {os.environ['GH_REPO']} ({_r.status_code}) — سيعمل الرندر محليًا.")
        elif _w.status_code != 200: print("⚠️ المستودع موجود لكن ملف .github/workflows/render.yml غير مرفوع — سيعمل الرندر محليًا.")
        else:
            CLOUD_OK = True
            print(f"☁️ الرندر السحابي جاهز: {os.environ['GH_REPO']} (" + ("عام" if not _r.json().get('private') else "خاص — دقائق Actions محدودة") + ")")
    except Exception as e:
        print("⚠️ تعذر فحص GitHub:", str(e)[:120], "— سيعمل الرندر محليًا.")
if not CLOUD_OK: os.environ.pop("GH_TOKEN", None)
if "SA_KEY" not in os.environ: os.environ["SA_KEY"] = secrets.token_urlsafe(9)
SA_KEY_VALUE = os.environ["SA_KEY"]
def lnk(u):
    return u

# ===================== التشغيل والربط الخارجي =====================
def server_alive():
    try:
        urllib.request.urlopen("http://127.0.0.1:3847/api/health", timeout=2).read(); return True
    except Exception:
        return False

srv_proc = subprocess.Popen([sys.executable, "app.py"], cwd=W, stdout=open(f'{W}/server.log', 'w'), stderr=subprocess.STDOUT, start_new_session=True)
ok = False
for _ in range(60):
    time.sleep(1)
    if server_alive(): ok = True; break
print("✅ الخادم يعمل على المنفذ 3847" if ok else "❌ فشل تشغيل الخادم:\n" + open(f'{W}/server.log').read()[-3000:])

# ---------- cloudflared ----------
CF = f"{W}/cloudflared"
ARCH = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower(), "amd64")

def cf_ok():
    try:
        return os.path.exists(CF) and os.path.getsize(CF) > 5_000_000 and subprocess.run([CF, "--version"], capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False

if not cf_ok() and not os.environ.get("SA_NO_TUNNEL"):
    try: os.remove(CF)
    except Exception: pass
    for attempt in range(3):
        sh(f"curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{ARCH} -o {CF} && chmod +x {CF}")
        if cf_ok(): break
        time.sleep(2)

BAD_HOSTS = {"api", "www", "dash", "developers", "support"}

def find_tunnel_url(text):
    for m in re.finditer(r"https://([a-z0-9-]+)\.trycloudflare\.com", text):
        if m.group(1) not in BAD_HOSTS:
            return m.group(0)
    return None

def tunnel_reaches_server(u):
    for _ in range(25):
        try:
            req = urllib.request.Request(u + "/api/health", headers={"User-Agent": "Mozilla/5.0"})
            body = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", "ignore")
            if '"ok"' in body: return True
        except Exception:
            pass
        time.sleep(2)
    return False

def start_tunnel(proto):
    for pat in ["[c]loudflared tunnel"]:
        subprocess.run(["pkill", "-f", pat], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    log = f'{W}/cloudflared.log'
    p = subprocess.Popen([CF, "tunnel", "--no-autoupdate", "--protocol", proto, "--edge-ip-version", "4", "--url", "http://127.0.0.1:3847"],
                         stdout=open(log, 'w'), stderr=subprocess.STDOUT, start_new_session=True)
    found = None
    for _ in range(45):
        time.sleep(1)
        if p.poll() is not None: break
        try: txt = open(log, errors="ignore").read()
        except Exception: txt = ""
        found = find_tunnel_url(txt)
        if found and re.search(r"Registered tunnel connection|Connection [0-9a-f-]+ registered", txt): break
    return p, found

url = None
tun_proc = None
if ok and cf_ok() and not os.environ.get("SA_NO_TUNNEL"):
    for proto in ("http2", "quic", "http2"):
        print(f"🔗 إنشاء النفق ({proto}) ...")
        tun_proc, cand = start_tunnel(proto)
        if cand and tunnel_reaches_server(cand):
            url = cand; break
        try: tun_proc.terminate()
        except Exception: pass

# كشف روابط GitHub Codespaces أو Colab تلقائياً
cs_url = None
if os.environ.get("CODESPACE_NAME") and os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN"):
    cs_url = f"https://{os.environ['CODESPACE_NAME']}-3847.{os.environ['GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN']}"

alt = None
try:
    from google.colab.output import eval_js
    alt = eval_js("google.colab.kernel.proxyPort(3847)")
except Exception:
    pass

print("\n" + "=" * 60 + "\n  🎬 SA Motion Studio v11.0 جاهز للعمل" + ("  ☁️ رندر سحابي" if CLOUD_OK else "  💻 رندر محلي"))
if url: print(f"  🌐 رابط Cloudflare المباشر: {lnk(url)}")
if cs_url: print(f"  🐙 رابط GitHub Codespaces:  {lnk(cs_url)}")
if alt: print(f"  🔬 رابط Google Colab:       {lnk(alt)}")
print(f"  🏠 الرابط المحلي:           {lnk('http://127.0.0.1:3847')}")
print("  🔐 الدخول بالمعرّف وكلمة المرور (لوحة الإدارة: /admin)")
print("=" * 60)

# إذا كنا نعمل في Terminal عادي (خارج دفتر Jupyter/Colab)، نبقي السكربت حياً لكي لا يغلق الخادم
if "ipykernel" not in sys.modules and ok:
    print("⏳ الخادم يعمل في الخلفية (اضغط Ctrl+C للإيقاف)...")
    try:
        while True:
            time.sleep(5)
            if not server_alive():
                print("⚠️ الخادم توقف، جاري إعادة التشغيل...")
                srv_proc = subprocess.Popen([sys.executable, "app.py"], cwd=W, stdout=open(f'{W}/server.log', 'a'), stderr=subprocess.STDOUT, start_new_session=True)
    except KeyboardInterrupt:
        print("\n🛑 تم إيقاف الاستوديو.")
