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

interface SegmentSource {
  name: string;
  text: string;
}

interface Segment {
  speaker?: string;
  text: string;
  start_ms: number;
  end_ms: number;
  chunk?: boolean;
  type?: "pause";
  emphasis?: string[];
  source?: SegmentSource;
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
   EMPHASIZED TEXT RENDERER
========================= */

interface EmphasisTextProps {
  text: string;
  emphasis?: string[];
  isCurrentChunk?: boolean;
}

const EmphasisText: React.FC<EmphasisTextProps> = ({ text, emphasis, isCurrentChunk }) => {
  if (!emphasis || emphasis.length === 0) {
    return <>{text}</>;
  }

  // Create regex to match emphasis words (case insensitive, word boundaries)
  const emphasisLower = emphasis.map(w => w.toLowerCase());

  // Split text into words while preserving spaces and punctuation
  const parts = text.split(/(\s+)/);

  return (
    <>
      {parts.map((part, i) => {
        // Check if this word (without punctuation) should be emphasized
        const cleanWord = part.replace(/[^\w\u0080-\uFFFF]/g, '').toLowerCase();
        const isEmphasized = emphasisLower.some(e =>
          cleanWord === e.toLowerCase() ||
          cleanWord.includes(e.toLowerCase())
        );

        if (isEmphasized && part.trim()) {
          return (
            <span
              key={i}
              style={{
                color: "#FFD700",
                fontWeight: 900,
                fontSize: isCurrentChunk ? "1.1em" : "1em",
                textShadow: "0 0 20px rgba(255, 215, 0, 0.5)",
              }}
            >
              {part}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
};

/* =========================
   FILM GRAIN OVERLAY
========================= */

const FilmGrain: React.FC = () => {
  const frame = useCurrentFrame();

  // Animate grain by shifting position each frame
  const grainOffset = (frame * 50) % 200;

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        opacity: 0.08, // 8% - slightly stronger grain
        mixBlendMode: "overlay",
      }}
    >
      <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <filter id="grain" x="0%" y="0%" width="100%" height="100%">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.7"
              numOctaves="4"
              seed={frame % 10}
              stitchTiles="stitch"
            />
            <feColorMatrix type="saturate" values="0" />
          </filter>
        </defs>
        <rect
          width="100%"
          height="100%"
          filter="url(#grain)"
          transform={`translate(${grainOffset}, ${grainOffset})`}
        />
      </svg>
    </div>
  );
};

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

  // Text appears 500ms earlier than audio
  const TEXT_OFFSET_MS = 500;
  const textTimeMs = currentTimeMs + TEXT_OFFSET_MS;

  /* =========================
     CHUNK LOGIC
  ========================= */

  const chunkSegments = segments.filter(
    (s) => s.chunk && !s.type
  );

  const currentChunkIndex = chunkSegments.findIndex(
    (s) =>
      textTimeMs >= s.start_ms &&
      textTimeMs <= s.end_ms
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
      textTimeMs,
      [startMs, startMs + 200],
      [0, 1],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

  /* =========================
     IMAGE LOGIC (change image every few speaker changes)
  ========================= */

  // Find current segment
  const effectiveSegmentIndex = segments.findIndex(
    (s) => currentTimeMs < s.end_ms
  );
  const safeSegmentIndex = effectiveSegmentIndex >= 0
    ? effectiveSegmentIndex
    : segments.length - 1;

  // Count speaker changes and calculate image switches
  const SPEAKER_CHANGES_PER_IMAGE = 3; // Change image every 3 speaker switches

  const getSpeakerChangeCount = (): number => {
    let changeCount = 0;
    let lastSpeaker: string | undefined;

    for (let i = 0; i <= safeSegmentIndex; i++) {
      const seg = segments[i];
      if (seg.speaker && seg.speaker !== lastSpeaker) {
        changeCount++;
        lastSpeaker = seg.speaker;
      }
    }

    return Math.max(0, changeCount - 1); // First speaker is change 0
  };

  const speakerChangeCount = getSpeakerChangeCount();
  const imageChangeNumber = Math.floor(speakerChangeCount / SPEAKER_CHANGES_PER_IMAGE);
  const currentImageIndex = images.length > 0
    ? imageChangeNumber % images.length
    : 0;
  const currentImage = images.length > 0 ? images[currentImageIndex] : null;

  /* =========================
     IMAGE TIMING (for motion effects)
  ========================= */

  // Find when the current image started (at the speaker change that triggered this image)
  const getImageStartFrame = (): number => {
    const targetChangeCount = imageChangeNumber * SPEAKER_CHANGES_PER_IMAGE;
    let changeCount = 0;
    let lastSpeaker: string | undefined;

    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      if (seg.speaker && seg.speaker !== lastSpeaker) {
        if (changeCount === targetChangeCount) {
          return Math.floor((seg.start_ms / 1000) * fps);
        }
        changeCount++;
        lastSpeaker = seg.speaker;
      }
    }

    return 0;
  };

  const imageStartFrame = getImageStartFrame();

  /* =========================
     BACKGROUND MOTION (cinematic push-in + parallax pan)
  ========================= */

  const framesIntoImage = frame - imageStartFrame;
  const zoomDuration = fps * 8; // 8 seconds for full zoom cycle

  // Cinematic push-in effect: 1.0 → 1.08 over 8 seconds (stronger zoom)
  const scale = interpolate(
    framesIntoImage,
    [0, zoomDuration],
    [1.0, 1.08],
    { extrapolateRight: "clamp" }
  );

  // Parallax pan effect - deterministic "random" direction based on image index
  // Use image index to determine pan direction (8 possible directions)
  const panDirections = [
    { x: 1, y: 0 },    // right
    { x: -1, y: 0 },   // left
    { x: 0, y: 1 },    // down
    { x: 0, y: -1 },   // up
    { x: 1, y: 1 },    // diagonal down-right
    { x: -1, y: 1 },   // diagonal down-left
    { x: 1, y: -1 },   // diagonal up-right
    { x: -1, y: -1 },  // diagonal up-left
  ];

  const panDirection = panDirections[currentImageIndex % panDirections.length];
  const panAmount = 15; // pixels to pan over duration

  const panX = interpolate(
    framesIntoImage,
    [0, zoomDuration],
    [0, panDirection.x * panAmount],
    { extrapolateRight: "clamp" }
  );

  const panY = interpolate(
    framesIntoImage,
    [0, zoomDuration],
    [0, panDirection.y * panAmount],
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
      {/* Background image with cinematic effects */}
      {currentImage?.file && (
        <AbsoluteFill style={{ overflow: "hidden" }}>
          <Img
            src={staticFile(`images/${currentImage.file}`)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              transform: `scale(${scale}) translate(${panX}px, ${panY}px)`,
              willChange: "transform",
            }}
          />
        </AbsoluteFill>
      )}

      {/* Depth vignette - affects image only */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.8) 100%)",
          opacity: 0.45,
          pointerEvents: "none",
        }}
      />

      {/* Dark overlay for text readability */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(to top, rgba(0,0,0,0.6), rgba(0,0,0,0.2))",
        }}
      />

      {/* Film grain overlay - adds realism, removes AI smoothness */}
      <FilmGrain />

      {/* Audio */}
      <Audio src={staticFile(audioFile)} />

      {/* Source attribution - fixed position at 1/4 screen height */}
      {currentChunk?.source && (
        <div
          style={{
            position: "absolute",
            top: "25%",
            left: 48,
            right: 48,
            textAlign: "center",
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              color: "#FFD700",
              fontSize: 30,
              fontWeight: 700,
              marginBottom: 6,
            }}
          >
            {currentChunk.source.name}
          </div>
          <div
            style={{
              color: "#FFFFFF",
              fontSize: 28,
              fontWeight: 400,
              lineHeight: 1.3,
            }}
          >
            {currentChunk.source.text}
          </div>
        </div>
      )}

      {/* Equalizer - fixed position */}
      <div
        style={{
          position: "absolute",
          top: "38%",
          left: 0,
          right: 0,
          display: "flex",
          justifyContent: "center",
          pointerEvents: "none",
        }}
      >
        <Equalizer />
      </div>

      {/* Subtitles (centered layout) */}
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
          {/* Previous chunk - no emphasis, plain text */}
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
              <EmphasisText
                text={currentChunk.text}
                emphasis={currentChunk.emphasis}
                isCurrentChunk={true}
              />
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
