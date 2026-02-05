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
  episodeNumber?: number; // Episode counter starting from 6
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
  const { width, height } = useVideoConfig();

  // Generate noise pattern using canvas-like approach with random dots
  // Use frame to create animated grain effect
  const seed = frame % 60; // Change pattern every frame, loop every 60

  // Create a pseudo-random but deterministic pattern based on seed
  const generateNoise = () => {
    const dots: React.ReactNode[] = [];
    const gridSize = 8; // Size of noise grid
    const cols = Math.ceil(width / gridSize);
    const rows = Math.ceil(height / gridSize);

    for (let i = 0; i < 800; i++) {
      // Pseudo-random positions based on index and seed
      const x = ((i * 127 + seed * 311) % cols) * gridSize;
      const y = ((i * 311 + seed * 127) % rows) * gridSize;
      const opacity = ((i * 17 + seed * 23) % 100) / 100;

      dots.push(
        <rect
          key={i}
          x={x}
          y={y}
          width={gridSize}
          height={gridSize}
          fill={opacity > 0.5 ? "white" : "black"}
          opacity={0.15}
        />
      );
    }
    return dots;
  };

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        opacity: 0.12,
        mixBlendMode: "overlay",
      }}
    >
      <svg width={width} height={height}>
        {generateNoise()}
      </svg>
    </div>
  );
};

/* =========================
   CALL TO ACTION (end of video)
========================= */

interface CTAProps {
  startFrame: number;
  durationFrames: number;
  headline?: string;
  subline?: string;
  showArrow?: boolean;
  visibleDurationFrames?: number;
}

const CallToAction: React.FC<CTAProps> = ({
  startFrame,
  durationFrames,
  headline = "Mniej emocji. Więcej debat.",
  subline = "Źródła w opisie",
  showArrow = true,
  visibleDurationFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const framesIntoAnimation = frame - startFrame;

  // Don't render if not yet visible
  if (framesIntoAnimation < 0) return null;
  if (visibleDurationFrames !== undefined && framesIntoAnimation > visibleDurationFrames) {
    return null;
  }

  const animationDuration = Math.min(fps * 0.8, durationFrames); // 0.8s animation

  // Opacity: 0 → 1 with ease-out
  const opacity = interpolate(
    framesIntoAnimation,
    [0, animationDuration],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: (t) => 1 - Math.pow(1 - t, 3), // ease-out cubic
    }
  );

  // TranslateY: 30px → 0 with ease-out
  const translateY = interpolate(
    framesIntoAnimation,
    [0, animationDuration],
    [30, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: (t) => 1 - Math.pow(1 - t, 3), // ease-out cubic
    }
  );

  return (
    <div
      style={{
        position: "absolute",
        bottom: 340, // Higher - well above YT subscribe button area
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
        opacity,
        transform: `translateY(${translateY}px)`,
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 10,
        }}
      >
        <div
          style={{
            fontSize: 28,
            fontWeight: 500,
            color: "rgba(255, 255, 255, 0.9)",
            textAlign: "center",
            lineHeight: 1.4,
            textShadow: "0 2px 8px rgba(0,0,0,0.6)",
            letterSpacing: "0.02em",
          }}
        >
          {headline}
        </div>
        {subline && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              fontSize: 26,
              fontWeight: 400,
              color: "rgba(255, 255, 255, 0.75)",
              textShadow: "0 2px 8px rgba(0,0,0,0.6)",
            }}
          >
            <span>{subline}</span>
            {showArrow && <span style={{ fontSize: 24 }}>↓</span>}
          </div>
        )}
      </div>
    </div>
  );
};

/* =========================
   HEADER WATERMARK (episode counter + logo)
========================= */

interface HeaderWatermarkProps {
  episodeNumber?: number;
}

const HeaderWatermark: React.FC<HeaderWatermarkProps> = ({ episodeNumber }) => {
  // Default to 6 if no episode number provided
  const displayNumber = episodeNumber ?? 6;
  const headerHeight = 28; // Shared height for text and logo

  return (
    <div
      style={{
        position: "absolute",
        top: 40,
        left: 64,
        right: 64,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        opacity: 0.6,
        pointerEvents: "none",
      }}
    >
      {/* Episode counter - upper left */}
      <div
        style={{
          fontSize: headerHeight,
          fontWeight: 700,
          color: "white",
          textShadow: "0 2px 6px rgba(0,0,0,0.6)",
          letterSpacing: "0.08em",
        }}
      >
        DYSKUSJA #{displayNumber}
      </div>

      {/* Logo - upper right */}
      <Img
        src={staticFile("channel-logo.png")}
        style={{
          height: headerHeight,
          width: "auto",
          objectFit: "contain",
        }}
      />
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
  episodeNumber,
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
     IMAGE LOGIC (first switch at 3s, rest distributed evenly)
  ========================= */

  const FIRST_SWITCH_MS = 3000;
  const lastSegment = segments[segments.length - 1];
  const totalDurationMs = lastSegment ? lastSegment.end_ms : 0;
  const numImages = images.length;

  // Build switch times: image 0 at 0ms, image 1 at 3000ms,
  // remaining images evenly from 3s to end
  const getImageSwitchTimeMs = (idx: number): number => {
    if (idx <= 0) return 0;
    if (idx === 1) return FIRST_SWITCH_MS;
    if (numImages <= 2) return FIRST_SWITCH_MS;
    const remainingTime = totalDurationMs - FIRST_SWITCH_MS;
    const remainingImages = numImages - 1; // images after the first
    return FIRST_SWITCH_MS + remainingTime * (idx - 1) / remainingImages;
  };

  const getCurrentImageIndex = (): number => {
    if (numImages === 0) return 0;
    for (let i = numImages - 1; i >= 0; i--) {
      if (currentTimeMs >= getImageSwitchTimeMs(i)) {
        return i;
      }
    }
    return 0;
  };

  const currentImageIndex = getCurrentImageIndex();
  const currentImage = images.length > 0 ? images[currentImageIndex] : null;

  /* =========================
     IMAGE TIMING (for motion effects)
  ========================= */

  const imageStartFrame = Math.floor(
    (getImageSwitchTimeMs(currentImageIndex) / 1000) * fps
  );

  const imageEndFrame = (() => {
    const nextIndex = currentImageIndex + 1;
    if (nextIndex >= numImages) {
      return Math.floor((totalDurationMs / 1000) * fps);
    }
    return Math.floor((getImageSwitchTimeMs(nextIndex) / 1000) * fps);
  })();

  /* =========================
     BACKGROUND MOTION (cinematic push-in + parallax pan)
  ========================= */

  const framesIntoImage = frame - imageStartFrame;
  const imageDuration = Math.max(1, imageEndFrame - imageStartFrame);

  // Cinematic push-in effect: 1.0 → 1.08 over entire image duration
  const scale = interpolate(
    framesIntoImage,
    [0, imageDuration],
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
  const panAmount = 40; // pixels to pan over duration (stronger parallax)

  const panX = interpolate(
    framesIntoImage,
    [0, imageDuration],
    [0, panDirection.x * panAmount],
    { extrapolateRight: "clamp" }
  );

  const panY = interpolate(
    framesIntoImage,
    [0, imageDuration],
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

      {/* Header watermark - episode counter + channel logo */}
      <HeaderWatermark episodeNumber={episodeNumber} />

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

      {/* Call to Action - appears in last 15% of video */}
      {(() => {
        const totalDurationMs = segments[segments.length - 1].end_ms;
        const ctaStartMs = totalDurationMs * 0.85; // Start at 85% of video
        const ctaStartFrame = Math.floor((ctaStartMs / 1000) * fps);
        const ctaDurationFrames = Math.floor(((totalDurationMs - ctaStartMs) / 1000) * fps);

        return (
          <>
            <CallToAction
              startFrame={Math.floor(5 * fps)}
              durationFrames={Math.floor(0.8 * fps)}
              headline="Zajrzyj do źródeł ↓"
              subline={"Więcej informacji w opisie"}
              showArrow={false}
              visibleDurationFrames={Math.floor(3 * fps)}
            />
            <CallToAction
              startFrame={ctaStartFrame}
              durationFrames={ctaDurationFrames}
            />
          </>
        );
      })()}

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
