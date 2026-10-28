// Applies a studio job (job.json) to this checkout: installs extra packages, downloads media,
// writes src/Composition.tsx + src/Root.tsx + props.json. Run inside each render job.
const fs = require("fs"), path = require("path"), cp = require("child_process");
const job = JSON.parse(fs.readFileSync(process.argv[2] || "job.json", "utf8"));
const ALLOWED = new Set(["lucide-react", "react-icons", "lodash", "d3", "three", "@react-three/fiber", "@react-three/drei", "gsap", "chroma-js", "polished", "simplex-noise"]);
const SAFE_FILE = /^[A-Za-z0-9_.-]{1,120}$/;

(async () => {
  // 1) extra npm packages (whitelisted only)
  let rv = "4";
  try { rv = JSON.parse(fs.readFileSync("node_modules/remotion/package.json", "utf8")).version; } catch (e) {}
  const pk = (job.packages || []).filter((p) => ALLOWED.has(p) || /^@remotion\/[a-z0-9-]+$/.test(p));
  if (pk.length) {
    const specs = pk.map((p) => (p.startsWith("@remotion/") ? `${p}@${rv}` : p));
    console.log("npm install", specs.join(" "));
    cp.execSync(`npm install --no-save --no-audit --no-fund --loglevel=error --legacy-peer-deps ${specs.join(" ")}`, { stdio: "inherit" });
  }

  // 2) media -> public/<file> (+ the aliases the studio code may use). Several files: video + audio, or more clips.
  fs.mkdirSync("public", { recursive: true });
  const list = (job.medias && job.medias.length ? job.medias : (job.media ? [job.media] : [])).filter((x) => x && x.file);
  let nv = 0, na = 0;
  for (const m of list) {
    if (!SAFE_FILE.test(m.file)) throw new Error("bad media file name");
    console.log("download media", m.file);
    let buf = null, last = "";
    for (let i = 0; i < 4 && !buf; i++) {
      try {
        const r = await fetch(m.url, { redirect: "follow" });
        if (!r.ok) { last = "HTTP " + r.status; await new Promise((z) => setTimeout(z, 1500 * (i + 1))); continue; }
        const b = Buffer.from(await r.arrayBuffer());
        if (b.length < 100) { last = "empty file"; continue; }
        buf = b;
      } catch (e) { last = String(e); await new Promise((z) => setTimeout(z, 1500 * (i + 1))); }
    }
    if (!buf) throw new Error("media download failed: " + m.file + " " + last);
    fs.writeFileSync(path.join("public", m.file), buf);
    const ext = path.extname(m.file);
    const primary = job.media && job.media.file === m.file;
    if (primary) fs.writeFileSync(path.join("public", "current_media" + ext), buf);
    if (m.type === "video") { nv++; fs.writeFileSync(path.join("public", nv === 1 ? "current_video.mp4" : `current_video_${nv}.mp4`), buf); }
    else { na++; fs.writeFileSync(path.join("public", na === 1 ? "current_audio" + ext : `current_audio_${na}${ext}`), buf); }
  }

  // 3) composition + root
  const c = job.config, comp = job.comp || {};
  if (!/^[A-Z]\w*$/.test(comp.name || "")) throw new Error("bad component name");
  fs.writeFileSync("src/Composition.tsx", job.code, "utf8");
  const imp = comp.default ? `import ${comp.name} from './Composition';` : `import { ${comp.name} } from './Composition';`;
  const num = (v, d) => (Number.isFinite(+v) ? Math.round(+v) : d);
  const root =
    "import React from 'react';\nimport { Composition } from 'remotion';\n" + imp + "\n" +
    "export const RemotionRoot: React.FC = () => (\n" +
    `  <Composition id="MainVideo" component={${comp.name} as any} durationInFrames={${num(c.frames, 300)}} fps={${num(c.fps, 30)}} width={${num(c.width, 1080)}} height={${num(c.height, 1920)}} defaultProps={{}} />\n);\n`;
  fs.writeFileSync("src/Root.tsx", root, "utf8");
  fs.writeFileSync("src/index.ts", "import { registerRoot } from 'remotion';\nimport { RemotionRoot } from './Root';\nregisterRoot(RemotionRoot);\n");

  // 4) props
  fs.writeFileSync("props.json", JSON.stringify(job.props || {}));
  console.log("job applied:", comp.name, c.width + "x" + c.height, "@" + c.fps, c.frames + " frames");
})().catch((e) => { console.error(e); process.exit(1); });
