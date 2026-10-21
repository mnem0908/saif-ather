import React from "react";
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
