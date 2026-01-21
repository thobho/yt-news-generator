import { Composition } from "remotion";
import { SubtitleVideo } from "./SubtitleVideo";
import timeline from "../../timeline.json";
import images from "../../output/images/images.json";

// Calculate total duration from timeline
const lastSegment = timeline.segments[timeline.segments.length - 1];
const totalDurationMs = lastSegment.end_ms + 500; // Add 500ms padding at the end
const FPS = 30;
const durationInFrames = Math.ceil((totalDurationMs / 1000) * FPS);

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="SubtitleVideo"
        component={SubtitleVideo}
        durationInFrames={durationInFrames}
        fps={FPS}
        width={1080}
        height={1920}
        defaultProps={{
          audioFile: timeline.audio_file,
          segments: timeline.segments,
          images: images.images,
        }}
      />
    </>
  );
};
