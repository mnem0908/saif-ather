import React from "react";
import { AbsoluteFill, Audio } from "remotion";
import { MediaProps, Seg } from "./sa_kit";
import { Motion as Showcase } from "./tpl_showcase";
import { Motion as Captions } from "./tpl_captions";
import { Motion as VideoEdit } from "./tpl_videoedit";
import { Motion as TitleCard } from "./tpl_title";

export type Props = {
  mediaUrl: string;
  title: string;
  duration: number; // seconds
  template: "title" | "showcase" | "captions" | "videoedit";
  mediaType: "video" | "audio" | "";
  width: number;
  height: number;
  fps: number;
  segments: Seg[];
};

export const defaultProps: Props = {
  mediaUrl: "", title: "SA Motion Studio", duration: 10, template: "title",
  mediaType: "", width: 1080, height: 1920, fps: 30, segments: [],
};

export const MainVideo: React.FC<Props> = (p) => {
  const media: MediaProps & { title?: string } = {
    mediaSrc: p.mediaUrl || null, mediaType: p.mediaType || (p.mediaUrl ? "video" : null),
    mediaDuration: p.duration, segments: p.segments || [], duration: p.duration, title: p.title,
  };
  const Tpl: React.FC<any> = p.template === "showcase" ? Showcase : p.template === "captions" ? Captions : p.template === "videoedit" ? VideoEdit : TitleCard;
  return (
    <AbsoluteFill>
      <Tpl {...media} />
      {p.mediaUrl ? <Audio src={p.mediaUrl} /> : null}
    </AbsoluteFill>
  );
};
