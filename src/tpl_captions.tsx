import React from "react";
import { Stage, Captions, Hint, ProgressBar, SA, MediaProps } from "./sa_kit";

export const Motion: React.FC<MediaProps> = (props) => {
  const segments = props.segments || [];
  return (
    <Stage media={props} colors={[SA.c, SA.e, SA.d]} dim={0.5}>
      <Captions segments={segments} variant="pill" anchor="center" size={0.105} />
      {!segments.length ? <Hint text={props.mediaSrc ? "اضغط «تفريغ الصوت» لتظهر الترجمة هنا" : "ارفع ملفاً ثم اضغط «تفريغ الصوت» لتظهر الترجمة هنا"} /> : null}
      <ProgressBar color={SA.c} />
    </Stage>
  );
};
