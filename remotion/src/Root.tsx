import { Composition, getInputProps } from "remotion";
import { SubtitleVideo } from "./SubtitleVideo";
import type { SubtitleVideoProps } from "./SubtitleVideo";

const FPS = 30;

type Timeline = {
  audio_file: string;
  segments: SubtitleVideoProps["segments"];
};

export const RemotionRoot: React.FC = () => {
  const { timeline, images } = getInputProps() as {
    timeline: Timeline;
    images: SubtitleVideoProps["images"];
  };

  if (!timeline || !timeline.segments || timeline.segments.length === 0) {
    throw new Error("Invalid or empty timeline passed to Remotion");
  }

  const lastSegment = timeline.segments[timeline.segments.length - 1];
  const totalDurationMs = lastSegment.end_ms + 500;
  const durationInFrames = Math.ceil((totalDurationMs / 1000) * FPS);

  return (
    <Composition<SubtitleVideoProps>
      id="SubtitleVideo"
      component={SubtitleVideo as React.FC<SubtitleVideoProps>}
      durationInFrames={durationInFrames}
      fps={FPS}
      width={1080}
      height={1920}
      defaultProps={{
        audioFile: timeline.audio_file,
        segments: timeline.segments,
        images: images ?? [],
      }}
    />
  );
};
