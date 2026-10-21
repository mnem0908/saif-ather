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

  // 2) media -> public/<file> (+ the aliases the studio code may use)
  fs.mkdirSync("public", { recursive: true });
  const m = job.media;
  if (m && m.file) {
    if (!SAFE_FILE.test(m.file)) throw new Error("bad media file name");
    console.log("download media", m.file);
    const r = await fetch(m.url, { redirect: "follow" });
    if (!r.ok) throw new Error("media download failed: " + r.status);
    const buf = Buffer.from(await r.arrayBuffer());
    fs.writeFileSync(path.join("public", m.file), buf);
    const ext = path.extname(m.file);
    fs.writeFileSync(path.join("public", "current_media" + ext), buf);
    if (m.type === "video") fs.writeFileSync(path.join("public", "current_video.mp4"), buf);
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
