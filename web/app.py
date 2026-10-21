# -*- coding: utf-8 -*-
"""SA Motion Studio — Hugging Face Space (Gradio). Rendering runs on GitHub Actions."""
import io, os, time, uuid, zipfile, mimetypes
import requests
import gradio as gr

GH_TOKEN = os.environ.get("GH_TOKEN", "")          # Space secret: fine-grained PAT (Actions: RW, Contents: RW)
GH_REPO = os.environ.get("GH_REPO", "")            # Space variable: "owner/repo"
GH_REF = os.environ.get("GH_REF", "main")
WORKFLOW = os.environ.get("GH_WORKFLOW", "render.yml")
API = "https://api.github.com"
HDR = {"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
MAX_MB = 90
OUT_DIR = "/tmp/renders"
os.makedirs(OUT_DIR, exist_ok=True)


def _release_id():
    """Get-or-create a release named 'media' that holds uploaded files."""
    r = requests.get(f"{API}/repos/{GH_REPO}/releases/tags/media", headers=HDR, timeout=30)
    if r.status_code == 200:
        return r.json()["id"]
    r = requests.post(f"{API}/repos/{GH_REPO}/releases", headers=HDR, timeout=30,
                      json={"tag_name": "media", "name": "media", "body": "Uploaded media for renders", "prerelease": True})
    r.raise_for_status()
    return r.json()["id"]


def upload_media(path):
    rid = _release_id()
    ext = os.path.splitext(path)[1].lower() or ".bin"
    name = f"{uuid.uuid4().hex[:12]}{ext}"
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        r = requests.post(f"https://uploads.github.com/repos/{GH_REPO}/releases/{rid}/assets",
                          params={"name": name}, data=f, timeout=600,
                          headers={**HDR, "Content-Type": ctype})
    r.raise_for_status()
    return r.json()["browser_download_url"], ("video" if ctype.startswith("video") else "audio")


def find_run(job_id, since):
    for _ in range(40):
        r = requests.get(f"{API}/repos/{GH_REPO}/actions/workflows/{WORKFLOW}/runs",
                         headers=HDR, params={"event": "workflow_dispatch", "per_page": 20}, timeout=30)
        if r.status_code == 200:
            for run in r.json().get("workflow_runs", []):
                if job_id in (run.get("display_title") or ""):
                    return run
        time.sleep(3)
    return None


def render(media, title, duration, template, preset):
    if not GH_TOKEN or not GH_REPO:
        raise gr.Error("الإعداد ناقص: أضف GH_TOKEN (Secret) وGH_REPO (Variable) في إعدادات الـ Space.")
    try:
        duration = float(duration)
    except Exception:
        raise gr.Error("المدة يجب أن تكون رقمًا")
    if not 1 <= duration <= 600:
        raise gr.Error("المدة بين 1 و600 ثانية")
    w, h = (1080, 1920) if preset.startswith("9:16") else (1920, 1080)
    job_id = uuid.uuid4().hex[:10]

    media_url, media_type = "", ""
    if media:
        if os.path.getsize(media) > MAX_MB * 1024 * 1024:
            raise gr.Error(f"الملف أكبر من {MAX_MB}MB")
        yield "⬆️ رفع الملف...", None
        media_url, media_type = upload_media(media)
    if template in ("captions", "videoedit") and media_type != "video":
        template = "title"  # these templates need a video; fall back safely

    yield "🚀 إرسال المهمة إلى GitHub Actions...", None
    inputs = {"job_id": job_id, "mediaUrl": media_url, "title": title or "SA Motion Studio",
              "duration": str(duration), "template": template, "mediaType": media_type,
              "width": str(w), "height": str(h), "fps": "30", "segments": "[]", "chunks": "8"}
    r = requests.post(f"{API}/repos/{GH_REPO}/actions/workflows/{WORKFLOW}/dispatches",
                      headers=HDR, json={"ref": GH_REF, "inputs": inputs}, timeout=30)
    if r.status_code != 204:
        raise gr.Error(f"فشل إطلاق المهمة ({r.status_code}): {r.text[:300]}")

    yield "⏳ بانتظار بدء الرندر...", None
    run = find_run(job_id, time.time())
    if not run:
        raise gr.Error("لم أجد التشغيل على GitHub. تحقق من اسم الـ workflow والفرع.")
    run_id, url = run["id"], run["html_url"]

    t0 = time.time()
    while True:
        rr = requests.get(f"{API}/repos/{GH_REPO}/actions/runs/{run_id}", headers=HDR, timeout=30).json()
        if rr.get("status") == "completed":
            break
        yield f"🎞️ جاري الرندر... {int(time.time() - t0)}ث — {url}", None
        time.sleep(8)
        if time.time() - t0 > 3600:
            raise gr.Error("انتهت المهلة (ساعة).")
    if rr.get("conclusion") != "success":
        raise gr.Error(f"فشل الرندر ({rr.get('conclusion')}). السجلات: {url}")

    arts = requests.get(f"{API}/repos/{GH_REPO}/actions/runs/{run_id}/artifacts", headers=HDR, timeout=30).json()
    art = next((a for a in arts.get("artifacts", []) if a["name"] == f"video-{job_id}"), None)
    if not art:
        raise gr.Error("اكتمل الرندر لكن لم أجد ملف الفيديو.")
    z = requests.get(art["archive_download_url"], headers=HDR, timeout=300)
    z.raise_for_status()
    out = os.path.join(OUT_DIR, f"{job_id}.mp4")
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        with zf.open("video.mp4") as src, open(out, "wb") as dst:
            dst.write(src.read())
    yield f"✅ تم ({int(time.time() - t0)}ث)", out


with gr.Blocks(title="SA Motion Studio") as demo:
    gr.Markdown("# 🎬 SA Motion Studio\nالرندر يتم على GitHub Actions. أول طلب قد يستغرق دقيقة أو أكثر.")
    with gr.Row():
        with gr.Column():
            media = gr.File(label="ملف صوت/فيديو (اختياري)", type="filepath", file_types=["audio", "video"])
            title = gr.Textbox(label="العنوان", value="SA Motion Studio")
            duration = gr.Number(label="المدة (ثوانٍ)", value=10, minimum=1, maximum=600)
            template = gr.Dropdown(["title", "showcase", "captions", "videoedit"], value="title", label="القالب")
            preset = gr.Radio(["9:16 ريلز", "16:9 يوتيوب"], value="9:16 ريلز", label="الأبعاد")
            btn = gr.Button("رندر", variant="primary")
        with gr.Column():
            status = gr.Textbox(label="الحالة", interactive=False)
            video = gr.Video(label="النتيجة")
    btn.click(render, [media, title, duration, template, preset], [status, video])

demo.queue(default_concurrency_limit=2).launch()
