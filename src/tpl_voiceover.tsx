import React from "react";
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
