import { AbsoluteFill, Audio, Img, useCurrentFrame, useVideoConfig, staticFile, interpolate } from "remotion";

interface Segment {
  speaker: string;
  text: string;
  start_ms: number;
  end_ms: number;
}

interface ImageInfo {
  id: string;
  purpose: string;
  prompt: string;
  file: string;
  segment_index?: number;
  segment_indices?: number[];
}

interface SubtitleVideoProps {
  audioFile: string;
  segments: Segment[];
  images: ImageInfo[];
}

export const SubtitleVideo: React.FC<SubtitleVideoProps> = ({
  audioFile,
  segments,
  images,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Convert frame to milliseconds
  const currentTimeMs = (frame / fps) * 1000;

  // Find the current segment index based on time
  const currentSegmentIndex = segments.findIndex(
    (segment) => currentTimeMs >= segment.start_ms && currentTimeMs <= segment.end_ms
  );

  const currentSegment = currentSegmentIndex >= 0 ? segments[currentSegmentIndex] : null;

  // Find which segment we're at or past (for image selection during pauses)
  const getEffectiveSegmentIndex = (): number => {
    // Before first segment
    if (currentTimeMs < segments[0].start_ms) {
      return 0;
    }

    // Find the last segment that started before current time
    for (let i = segments.length - 1; i >= 0; i--) {
      if (currentTimeMs >= segments[i].start_ms) {
        return i;
      }
    }
    return 0;
  };

  const effectiveSegmentIndex = getEffectiveSegmentIndex();

  // Find the current background image based on effective segment index
  const getCurrentImage = (): ImageInfo | null => {
    // Find image that contains this segment index
    for (const img of images) {
      if (img.segment_index === effectiveSegmentIndex) {
        return img;
      }
      if (img.segment_indices?.includes(effectiveSegmentIndex)) {
        return img;
      }
    }

    // Fallback: find by approximate position
    const totalSegments = segments.length;
    const progress = effectiveSegmentIndex / totalSegments;

    if (progress < 0.1) return images.find(img => img.id === "hook") || images[0];
    if (progress < 0.4) return images.find(img => img.id === "topic_1") || images[1];
    if (progress < 0.7) return images.find(img => img.id === "topic_2") || images[2];
    return images.find(img => img.id === "discussion") || images[images.length - 1];
  };

  const currentImage = getCurrentImage();

  // Get speaker color
  const getSpeakerColor = (speaker: string) => {
    return speaker === "A" ? "#3B82F6" : "#EC4899"; // Blue for A, Pink for B
  };

  // Subtle zoom animation for background
  const scale = interpolate(frame, [0, fps * 60], [1, 1.1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0F172A",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      {/* Background Image */}
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

      {/* Dark overlay for contrast */}
      <AbsoluteFill
        style={{
          background: "linear-gradient(to bottom, rgba(0,0,0,0.3) 0%, rgba(0,0,0,0.5) 40%, rgba(0,0,0,0.8) 100%)",
        }}
      />

      {/* Audio */}
      <Audio src={staticFile(audioFile)} />

      {/* Subtitle container - centered */}
      <AbsoluteFill
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "0 48px",
        }}
      >
        {currentSegment && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              maxWidth: "100%",
            }}
          >
            {/* Speaker indicator */}
            <div
              style={{
                backgroundColor: getSpeakerColor(currentSegment.speaker),
                color: "white",
                padding: "12px 32px",
                borderRadius: 30,
                fontSize: 32,
                fontWeight: 700,
                marginBottom: 32,
                boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
              }}
            >
              {currentSegment.speaker === "A" ? "Osoba A" : "Osoba B"}
            </div>

            {/* Subtitle text with strong contrast */}
            <div
              style={{
                color: "white",
                fontSize: 56,
                fontWeight: 800,
                textAlign: "center",
                lineHeight: 1.3,
                textShadow: `
                  0 0 20px rgba(0,0,0,0.9),
                  0 0 40px rgba(0,0,0,0.8),
                  0 4px 8px rgba(0,0,0,0.9),
                  2px 2px 0 rgba(0,0,0,0.8),
                  -2px -2px 0 rgba(0,0,0,0.8),
                  2px -2px 0 rgba(0,0,0,0.8),
                  -2px 2px 0 rgba(0,0,0,0.8)
                `,
                maxWidth: "100%",
                padding: "20px",
                borderRadius: 16,
                backgroundColor: "rgba(0,0,0,0.4)",
              }}
            >
              {currentSegment.text}
            </div>
          </div>
        )}
      </AbsoluteFill>

      {/* Progress bar */}
      <div
        style={{
          position: "absolute",
          bottom: 60,
          left: 40,
          right: 40,
          height: 8,
          backgroundColor: "rgba(255,255,255,0.3)",
          borderRadius: 4,
          boxShadow: "0 2px 10px rgba(0,0,0,0.5)",
        }}
      >
        <div
          style={{
            height: "100%",
            backgroundColor: "#3B82F6",
            borderRadius: 4,
            width: `${(currentTimeMs / (segments[segments.length - 1].end_ms + 500)) * 100}%`,
            boxShadow: "0 0 10px rgba(59,130,246,0.8)",
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
