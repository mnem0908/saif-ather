import React from "react";
import { AbsoluteFill, useVideoConfig } from "remotion";
import { Stage, Kinetic, Pop, ProgressBar, SA, MediaProps } from "./sa_kit";

export const Motion: React.FC<MediaProps & { title?: string }> = (props) => {
  const { width, height } = useVideoConfig(); const m = Math.min(width, height);
  return (
    <Stage media={props}>
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", gap: m * 0.04, padding: m * 0.07 }}>
        <Kinetic text={props.title || "SA Motion Studio"} size={0.1} delay={6} />
        <Pop delay={30}><div style={{ width: m * 0.2, height: m * 0.008, borderRadius: 99, background: SA.a }} /></Pop>
      </AbsoluteFill>
      <ProgressBar color={SA.b} />
    </Stage>
  );
};
