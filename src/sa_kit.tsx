import React from "react";
import { AbsoluteFill, Easing, Loop, OffthreadVideo, Sequence, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig, getInputProps } from "remotion";
import { loadFont } from "@remotion/google-fonts/Cairo";

let fam = "Cairo";
try { fam = loadFont("normal", { weights: ["400", "700", "900"], subsets: ["arabic", "latin"] }).fontFamily; } catch (e) {}
export const FONT = `${fam}, "Noto Sans Arabic", "Noto Naskh Arabic", "Noto Color Emoji", sans-serif`;

export type Word = { text: string; start: number; end: number };
export type Seg = { text: string; start: number; end: number; words: Word[] };
export type MediaProps = { mediaSrc?: string | null; mediaType?: string | null; mediaDuration?: number; segments?: Seg[]; words?: Word[]; duration?: number };

// يجمع الوسائط من خصائص المكوّن أو مباشرة من inputProps — يعمل حتى لو لم يمرّرها كود التصميم
export const useSAMedia = (p?: MediaProps): MediaProps => {
  let inp: any = {};
  try { inp = getInputProps() || {}; } catch (e) {}
  const q: any = p || {};
  const src = q.mediaSrc || q.videoSrc || q.audioSrc || q.mediaUrl || q.src || inp.mediaSrc || inp.mediaUrl || null;
  return {
    mediaSrc: src,
    mediaType: q.mediaType || inp.mediaType || null,
    mediaDuration: q.mediaDuration || inp.mediaDuration || 0,
    segments: (q.segments && q.segments.length ? q.segments : inp.segments) || [],
    words: (q.words && q.words.length ? q.words : inp.words) || [],
    duration: q.duration || inp.duration,
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

export const VideoBg: React.FC<{ src?: string | null; type?: string | null; mediaDuration?: number; dim?: number; zoom?: boolean; colors?: string[] }> = ({ src, type, mediaDuration = 0, dim = 0.45, zoom = true, colors }) => {
  const f = useCurrentFrame(); const { durationInFrames } = useVideoConfig();
  if (!src || type !== "video") return <Aurora colors={colors} />;
  const z = zoom ? interpolate(f, [0, durationInFrames], [1.05, 1.17]) : 1.05;
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <AbsoluteFill style={{ transform: `scale(${z}) translate(${Math.sin(f / 90) * 8}px, ${Math.cos(f / 110) * 6}px)` }}>
        <MediaVideo src={src} mediaDuration={mediaDuration} style={{ filter: "contrast(1.1) saturate(1.2) brightness(.92)" }} />
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
  return <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", color: SA.mute, fontSize: m * 0.05, fontWeight: 700, textAlign: "center", padding: m * 0.1, fontFamily: FONT }}>{text}</AbsoluteFill>;
};
