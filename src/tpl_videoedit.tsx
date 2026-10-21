import React from "react";
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
