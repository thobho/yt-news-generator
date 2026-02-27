#!/usr/bin/env python3
"""
Generate audio from dialogue JSON using Chatterbox TTS on RunPod Serverless.

Each dialogue segment is generated individually with per-speaker voice switching
(male/female). Segments are merged with silence gaps and converted to MP3.
A timeline.json is produced with the same structure as the ElevenLabs pipeline.

Usage:
    python generate_audio_runpod.py dialogue.json -o output.mp3 -t timeline.json

Environment variables:
    RUNPOD_API_KEY: Your RunPod API key (required)
    RUNPOD_ENDPOINT_ID: Your RunPod serverless endpoint ID (required)
    CHATTERBOX_CFG_WEIGHT: Speed control 0.2-1.0 (default 0.6)
    CHATTERBOX_EXAGGERATION: Expressiveness 0.25-2.0 (default 0.9)
"""

import argparse
import json
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Union

from .audio import (
    PAUSE_BETWEEN_SEGMENTS_MS,
    chunk_segment_aligned,
    extract_segments,
)
from .audio_align import transcribe_with_timestamps, align_text_to_audio
from ..core.logging_config import get_logger
from ..core.storage import StorageBackend
from ..core.storage_config import get_data_storage
from .tts_client import TTSClient

logger = get_logger(__name__)


# Target format for merging – must match between segments and silence
_MERGE_SAMPLE_RATE = 44100
_FADE_MS = 15  # fade-in/out at segment edges to eliminate TTS edge noise

# Parallelization settings
TTS_MAX_WORKERS = 5  # Max parallel TTS requests
FFMPEG_MAX_WORKERS = 4  # Max parallel FFmpeg processes


def _normalize_single_wav(args: tuple) -> Path:
    """Normalize a single WAV file (for parallel processing).

    Args:
        args: Tuple of (wav_path, output_path, sample_rate, fade_sec)

    Returns:
        Path to normalized file
    """
    wav_path, output_path, sample_rate, fade_sec = args
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(wav_path),
            "-ar", str(sample_rate), "-ac", "1",
            "-af", (
                f"afade=t=in:d={fade_sec},"
                f"areverse,afade=t=in:d={fade_sec},areverse"
            ),
            str(output_path),
        ],
        capture_output=True,
        check=True,
    )
    return output_path


def _normalize_and_merge(wav_files: list[Path], output: Path, pause_ms: int):
    """Merge WAV segments into MP3 with silence gaps.

    Uses parallel processing for normalization to speed up the process.
    """
    temp = wav_files[0].parent
    fade_sec = _FADE_MS / 1000

    # 1. Normalize each WAV in parallel: resample, mono, 16-bit PCM, fade edges
    normalize_args = [
        (wav, temp / f"norm_{i:03}.wav", _MERGE_SAMPLE_RATE, fade_sec)
        for i, wav in enumerate(wav_files)
    ]

    normalized: list[Path] = [None] * len(wav_files)
    with ProcessPoolExecutor(max_workers=FFMPEG_MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_normalize_single_wav, args): i
            for i, args in enumerate(normalize_args)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            normalized[idx] = future.result()

    # 2. Generate silence in the exact same WAV format
    silence = temp / "silence.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anullsrc=r={_MERGE_SAMPLE_RATE}:cl=mono",
            "-t", str(pause_ms / 1000),
            str(silence),
        ],
        capture_output=True,
        check=True,
    )

    # 3. Build concat list (all files are now identical format)
    concat = temp / "concat.txt"
    with open(concat, "w") as f:
        for i, norm in enumerate(normalized):
            f.write(f"file '{norm}'\n")
            if i < len(normalized) - 1:
                f.write(f"file '{silence}'\n")

    # 4. Concat → MP3
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat),
            "-c:a", "libmp3lame", "-q:a", "2",
            str(output),
        ],
        capture_output=True,
        check=True,
    )


def load_dialogue(path: Union[Path, str], storage: StorageBackend = None) -> dict:
    """Load dialogue from file."""
    if storage is not None:
        content = storage.read_text(str(path))
        return json.loads(content)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_audio(
    dialogue_path: Union[Path, str],
    output: Union[Path, str],
    timeline: Union[Path, str] = None,
    voice_a: str = None,
    voice_b: str = None,
    storage: StorageBackend = None,
    language: str = "pl",
):
    """Generate audio from dialogue using Chatterbox TTS on RunPod Serverless.

    Each dialogue line is generated as a separate segment with the appropriate
    voice reference (male/female). Segments are merged with silence gaps and
    converted to MP3. A timeline.json is produced for subtitle rendering.

    Args:
        dialogue_path: Path to dialogue JSON file
        output: Path to output audio file (MP3)
        timeline: Path to output timeline JSON file
        voice_a: Storage key for first speaker voice (required)
        voice_b: Storage key for second speaker voice (required)
        storage: Optional storage backend
    """
    if not voice_a or not voice_b:
        raise ValueError("voice_a and voice_b storage keys are required for Chatterbox TTS.")
    logger.info("Generating audio from dialogue: %s", dialogue_path)

    client = TTSClient()

    data = load_dialogue(dialogue_path, storage)
    segments, speakers = extract_segments(data)
    logger.info("Found %d segments with speakers: %s", len(segments), speakers)

    # Build voice map: first speaker -> voice_a, second speaker -> voice_b
    voice_map = {s: [voice_a, voice_b][i % 2] for i, s in enumerate(speakers)}
    logger.debug("Voice mapping: %s", voice_map)

    # Voice files live under data/ storage (not run storage)
    data_storage = get_data_storage() if storage is not None else None

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        n_segments = len(segments)

        # Parallel TTS generation
        logger.info("Generating %d audio segments in parallel (max %d workers)", n_segments, TTS_MAX_WORKERS)

        def generate_segment(args):
            """Generate a single TTS segment."""
            idx, speaker, text, voice_ref = args
            out_path = tmp / f"seg_{idx:03}.wav"
            result = client.generate_with_metadata(
                text=text,
                voice_ref_path=voice_ref,
                storage=data_storage,
                language_id=language,
            )
            out_path.write_bytes(result["audio"])
            return idx, out_path, result["duration_ms"], text

        # Prepare arguments for parallel execution
        tts_args = [
            (i, speaker, text, voice_map[speaker])
            for i, (speaker, text, _, _) in enumerate(segments)
        ]

        # Run TTS in parallel
        audio_files = [None] * n_segments
        durations = [None] * n_segments
        segment_texts = [None] * n_segments

        with ThreadPoolExecutor(max_workers=TTS_MAX_WORKERS) as executor:
            futures = [executor.submit(generate_segment, args) for args in tts_args]
            for future in as_completed(futures):
                idx, out_path, duration_ms, text = future.result()
                audio_files[idx] = out_path
                durations[idx] = duration_ms
                segment_texts[idx] = text
                logger.debug("Generated segment %d/%d (%.1fs)", idx + 1, n_segments, duration_ms / 1000)

        # Run Whisper alignment (can also be parallelized but API cost is per-minute)
        alignments = []
        if timeline is not None:
            logger.info("Running Whisper alignment on %d segments", n_segments)
            for i, (audio_file, text) in enumerate(zip(audio_files, segment_texts)):
                try:
                    whisper_words = transcribe_with_timestamps(audio_file, language=language)
                    aligned = align_text_to_audio(text, whisper_words, start_offset_ms=0)
                    alignments.append(aligned)
                    logger.debug("Aligned %d words for segment %d", len(aligned), i + 1)
                except Exception as e:
                    logger.warning("Whisper alignment failed for segment %d: %s", i + 1, e)
                    alignments.append(None)
        else:
            alignments = [None] * n_segments

        logger.info("Merging %d audio segments", len(audio_files))

        # Normalize all WAVs to common format, apply fades, merge with silence
        temp_output = tmp / "merged.mp3"
        _normalize_and_merge(audio_files, temp_output, PAUSE_BETWEEN_SEGMENTS_MS)

        # Copy to final destination
        if storage is not None:
            storage.copy_from_local(temp_output, str(output))
        else:
            output = Path(output)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp_output, output)

    # Build timeline
    if timeline is not None:
        timeline_segments = []
        t = 0

        output_name = Path(output).name if isinstance(output, (str, Path)) else output

        for i, ((speaker, text, emphasis, sources), dur, aligned) in enumerate(
            zip(segments, durations, alignments)
        ):
            if aligned:
                aligned_offset = [
                    {
                        "word": w["word"],
                        "start_ms": w["start_ms"] + t,
                        "end_ms": w["end_ms"] + t,
                    }
                    for w in aligned
                ]
                chunks = chunk_segment_aligned(
                    aligned_offset, speaker, emphasis, sources, t, t + dur
                )
                timeline_segments.extend(chunks)
                logger.debug("Whisper aligned segment %d (%d chunks)", i + 1, len(chunks))
            else:
                logger.warning("No alignment for segment %d, skipping chunks", i + 1)

            t += dur

            if i < len(segments) - 1:
                timeline_segments.append(
                    {
                        "type": "pause",
                        "start_ms": t,
                        "end_ms": t + PAUSE_BETWEEN_SEGMENTS_MS,
                    }
                )
                t += PAUSE_BETWEEN_SEGMENTS_MS

        timeline_data = {
            "audio_file": output_name,
            "segments": timeline_segments,
        }

        timeline_json = json.dumps(timeline_data, ensure_ascii=False, indent=2)

        if storage is not None:
            storage.write_text(str(timeline), timeline_json)
        else:
            timeline_path = Path(timeline)
            timeline_path.parent.mkdir(parents=True, exist_ok=True)
            with open(timeline_path, "w", encoding="utf-8") as f:
                f.write(timeline_json)

    total_duration_s = sum(durations) / 1000
    logger.info(
        "Audio generated: %s (%.1fs, %d segments)", output, total_duration_s, len(segments)
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("dialogue", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("-t", "--timeline", type=Path, default=None)
    p.add_argument("--voice-a", required=True, help="Storage key for first speaker voice WAV")
    p.add_argument("--voice-b", required=True, help="Storage key for second speaker voice WAV")
    args = p.parse_args()

    generate_audio(
        args.dialogue,
        args.output,
        args.timeline,
        args.voice_a,
        args.voice_b,
    )


if __name__ == "__main__":
    main()
