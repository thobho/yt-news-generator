import {
  AbsoluteFill,
  Audio,
  Img,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
  interpolate,
} from "remotion";

/* =========================
   TYPES
========================= */

interface Segment {
  speaker?: string;
  text: string;
  start_ms: number;
  end_ms: number;
  chunk?: boolean;
  type?: "pause";
}

interface ImageInfo {
  id: string;
  purpose: string;
  prompt: string;
  file: string;
  segment_index?: number;
  segment_indices?: number[];
}

export interface SubtitleVideoProps {
  audioFile: string;
  segments: Segment[];
  images: ImageInfo[];
}

/* =========================
   EQUALIZER (SUBTLE)
========================= */

const Equalizer: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <div style={{ display: "flex", gap: 8, opacity: 0.35 }}>
      {Array.from({ length: 7 }).map((_, i) => {
        const h =
          16 +
          Math.abs(Math.sin(frame / fps + i)) * 40;

        return (
          <div
            key={i}
            style={{
              width: 8,
              height: h,
              background: "white",
              borderRadius: 4,
              boxShadow: "0 0 12px rgba(255,255,255,0.4)",
            }}
          />
        );
      })}
    </div>
  );
};

/* =========================
   MAIN COMPONENT
========================= */

export const SubtitleVideo: React.FC<SubtitleVideoProps> = ({
  audioFile,
  segments,
  images,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTimeMs = (frame / fps) * 1000;

  /* =========================
     CHUNK LOGIC
  ========================= */

  const chunkSegments = segments.filter(
    (s) => s.chunk && !s.type
  );

  const currentChunkIndex = chunkSegments.findIndex(
    (s) =>
      currentTimeMs >= s.start_ms &&
      currentTimeMs <= s.end_ms
  );

  const currentChunk =
    currentChunkIndex >= 0
      ? chunkSegments[currentChunkIndex]
      : null;

  const previousChunk =
    currentChunkIndex > 0
      ? chunkSegments[currentChunkIndex - 1]
      : null;

  const fadeIn = (startMs: number) =>
    interpolate(
      currentTimeMs,
      [startMs, startMs + 200],
      [0, 1],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

  /* =========================
     IMAGE LOGIC (always show an image, never black screen)
  ========================= */

  const effectiveSegmentIndex = segments.findIndex(
    (s) => currentTimeMs < s.end_ms
  );

  // Clamp to valid range
  const safeSegmentIndex = effectiveSegmentIndex >= 0
    ? effectiveSegmentIndex
    : segments.length - 1;

  const getCurrentImage = (): ImageInfo => {
    // First try exact match
    for (const img of images) {
      if (img.segment_index === safeSegmentIndex) {
        return img;
      }
      if (img.segment_indices?.includes(safeSegmentIndex)) {
        return img;
      }
    }

    // Find closest previous image
    let bestImage = images[0];
    for (const img of images) {
      const imgSegIdx = img.segment_index ?? img.segment_indices?.[0] ?? 0;
      const bestSegIdx = bestImage.segment_index ?? bestImage.segment_indices?.[0] ?? 0;
      if (imgSegIdx <= safeSegmentIndex && imgSegIdx > bestSegIdx) {
        bestImage = img;
      }
    }

    // Always return something - never null
    return bestImage ?? images[0];
  };

  const currentImage = images.length > 0 ? getCurrentImage() : null;

  /* =========================
     BACKGROUND MOTION (subtle per-image zoom)
  ========================= */

  // Find when current image started
  const imageStartFrame = (() => {
    if (!currentImage) return 0;
    const segIdx = currentImage.segment_index ?? currentImage.segment_indices?.[0] ?? 0;
    const clampedIdx = Math.max(0, Math.min(segIdx, segments.length - 1));
    const seg = segments[clampedIdx];
    if (!seg) return 0;
    return Math.floor((seg.start_ms / 1000) * fps);
  })();

  const framesIntoImage = frame - imageStartFrame;
  const zoomDuration = fps * 4; // 4 seconds for full zoom cycle

  const scale = interpolate(
    framesIntoImage,
    [0, zoomDuration],
    [1.0, 1.06], // Subtle but noticeable: 6% zoom over 4 seconds
    { extrapolateRight: "clamp" }
  );

  /* =========================
     RENDER
  ========================= */

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0B1220",
        fontFamily:
          "system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      {/* Background image */}
      {currentImage?.file && (
        <AbsoluteFill style={{ overflow: "hidden" }}>
          <Img
            src={staticFile(`images/${currentImage.file}`)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              transform: `scale(${scale})`,
            }}
          />
        </AbsoluteFill>
      )}

      {/* Dark overlay */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(to top, rgba(0,0,0,0.6), rgba(0,0,0,0.2))",
        }}
      />

      {/* Audio */}
      <Audio src={staticFile(audioFile)} />

      {/* Subtitles + Equalizer (centered layout) */}
      <AbsoluteFill
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          paddingLeft: 48,
          paddingRight: 48,
        }}
      >
        {/* Equalizer above text */}
        <div
          style={{
            marginBottom: 32,
            pointerEvents: "none",
          }}
        >
          <Equalizer />
        </div>

        {/* Subtitles container */}
        <div
          style={{
            maxWidth: "90%",
            display: "flex",
            flexDirection: "column",
            gap: 14,
            textAlign: "center",
          }}
        >
          {/* Previous chunk */}
          {previousChunk && (
            <div
              style={{
                fontSize: 42,
                fontWeight: 600,
                color: "rgba(255,255,255,0.55)",
                lineHeight: 1.25,
              }}
            >
              {previousChunk.text}
            </div>
          )}

          {/* Current chunk */}
          {currentChunk && (
            <div
              style={{
                fontSize: 56,
                fontWeight: 800,
                color: "white",
                lineHeight: 1.3,
                opacity: fadeIn(currentChunk.start_ms),
                textShadow:
                  "0 10px 40px rgba(0,0,0,0.9)",
              }}
            >
              {currentChunk.text}
            </div>
          )}
        </div>
      </AbsoluteFill>

      {/* Progress bar */}
      <div
        style={{
          position: "absolute",
          bottom: 60,
          left: 40,
          right: 40,
          height: 6,
          background: "rgba(255,255,255,0.25)",
          borderRadius: 3,
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${
              (currentTimeMs /
                segments[segments.length - 1].end_ms) *
              100
            }%`,
            background: "white",
            borderRadius: 3,
            boxShadow:
              "0 0 12px rgba(255,255,255,0.6)",
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
