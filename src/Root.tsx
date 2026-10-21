import React from "react";
import { Composition } from "remotion";
import { MainVideo, Props, defaultProps } from "./Composition";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="MainVideo"
    component={MainVideo as any}
    durationInFrames={300}
    fps={30}
    width={1080}
    height={1920}
    defaultProps={defaultProps}
    calculateMetadata={async ({ props }: { props: Props }) => {
      const fps = Math.max(1, Math.min(60, Number(props.fps) || 30));
      const seconds = Math.max(1, Math.min(600, Number(props.duration) || 10));
      return {
        fps,
        durationInFrames: Math.round(seconds * fps),
        width: (Math.max(64, Math.min(4096, Number(props.width) || 1080)) >> 1) << 1,
        height: (Math.max(64, Math.min(4096, Number(props.height) || 1920)) >> 1) << 1,
      };
    }}
  />
);
