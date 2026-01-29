#!/usr/bin/env python3
"""
Generate audio from dialogue JSON using Chatterbox TTS on RunPod Serverless.

This module calls a RunPod Serverless endpoint running Chatterbox TTS,
generates audio segments, merges them locally, and creates a timeline.

No quota approval needed - just sign up at runpod.io and add credits.

Usage:
    python generate_audio_runpod.py dialogue.json -o final_audio.mp3 -t timeline.json

Environment variables:
    RUNPOD_API_KEY: Your RunPod API key (required)
    RUNPOD_ENDPOINT_ID: Your RunPod serverless endpoint ID (required)

The interface is identical to generate_audio.py for easy swapping.
"""

import argparse
import base64
import json
import os
import subprocess
import re
import tempfile
from pathlib import Path
from typing import Union, Optional

import runpod

from logging_config import get_logger
from storage import StorageBackend

logger = get_logger(__name__)


# ==========================
# CONFIG
# ==========================

DEFAULT_VOICE_A = "neutral"
DEFAULT_VOICE_B = "neutral"
PAUSE_BETWEEN_SEGMENTS_MS = 150  # Short pause between dialog segments

# RunPod Serverless Configuration
RUNPOD_ENDPOINT_ID = os.environ.get("RUNPOD_ENDPOINT_ID")
RUNPOD_REQUEST_TIMEOUT = int(os.environ.get("RUNPOD_REQUEST_TIMEOUT", "120"))

# Chatterbox Configuration
CHATTERBOX_SAMPLE_RATE = 24000

# TTS Parameters for Polish language
# cfg_weight: Controls pace/speed (0.2-1.0). Lower = slower speech. Default 0.5
# exaggeration: Controls expressiveness (0.25-2.0). Higher = more dramatic/vivid. Default 0.5
#   0.5 = neutral, 0.8 = lively, 1.0+ = very expressive
CHATTERBOX_CFG_WEIGHT = float(os.environ.get("CHATTERBOX_CFG_WEIGHT", "0.6"))  # Slightly faster
CHATTERBOX_EXAGGERATION = float(os.environ.get("CHATTERBOX_EXAGGERATION", "0.9"))  # Very expressive

# Voice reference audio paths (optional - for voice cloning with native Polish speaker)
# To use: place a 5-10 second WAV file of a native Polish speaker in data/voices/
# This helps with proper Polish pronunciation (rolled R, etc.)
VOICE_REFS = {
    "neutral": "data/voices/polish_native_cleaned.wav",  # Your Polish voice sample (cleaned, 24kHz)
}

CONNECTORS = {
    "i", "ale", "że", "bo", "który", "która",
    "którzy", "które", "oraz", "ponieważ"
}

MIN_WORDS = 2
MAX_WORDS = 6


# ==========================
# SEMANTIC CHUNKING
# ==========================

def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+|[^\w\s]", text, re.UNICODE)


def semantic_chunks(text: str) -> list[str]:
    words = tokenize(text)
    chunks = []
    current = []

    for w in words:
        current.append(w)
        clean_words = [x for x in current if re.match(r"\w+", x)]
        wc = len(clean_words)

        if (
            wc >= MAX_WORDS
            or w in {".", "?", "!"}
            or (wc >= MIN_WORDS and w.lower() in CONNECTORS)
        ):
            chunks.append(" ".join(current).strip())
            current = []

    if current:
        chunks.append(" ".join(current).strip())

    return chunks


def chunk_segment(segment: dict) -> list[dict]:
    chunks = semantic_chunks(segment["text"])
    start = segment["start_ms"]
    end = segment["end_ms"]
    duration = end - start
    emphasis = segment.get("emphasis", [])
    source = segment.get("source")

    lengths = [len(c.split()) for c in chunks]
    total_words = sum(lengths)

    result = []
    current_time = start

    for chunk, words in zip(chunks, lengths):
        part = int(duration * (words / total_words))
        chunk_data = {
            "speaker": segment["speaker"],
            "text": chunk,
            "start_ms": current_time,
            "end_ms": current_time + part,
            "chunk": True
        }
        if emphasis:
            chunk_emphasis = [w for w in emphasis if w.lower() in chunk.lower()]
            if chunk_emphasis:
                chunk_data["emphasis"] = chunk_emphasis
        if source:
            chunk_data["source"] = source
        result.append(chunk_data)
        current_time += part

    if result:
        result[-1]["end_ms"] = end

    return result


# ==========================
# AUDIO HELPERS
# ==========================

def get_audio_duration_ms(path: Path) -> int:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(float(result.stdout.strip()) * 1000)


def merge_audio(files: list[Path], output: Path, pause_ms: int):
    """Merge audio files with pauses between them using ffmpeg filter_complex."""
    if not files:
        raise ValueError("No audio files to merge")

    # Build filter_complex for concatenation with silence gaps
    # First, generate inputs
    inputs = []
    for f in files:
        inputs.extend(["-i", str(f)])

    # Build filter graph
    filter_parts = []
    concat_inputs = []

    for i in range(len(files)):
        # Normalize each input to consistent format
        filter_parts.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a{i}]")
        concat_inputs.append(f"[a{i}]")

        # Add silence after each segment except the last
        if i < len(files) - 1:
            silence_label = f"s{i}"
            filter_parts.append(
                f"aevalsrc=0:d={pause_ms/1000}:s=44100:c=stereo[{silence_label}]"
            )
            concat_inputs.append(f"[{silence_label}]")

    # Concatenate all
    filter_parts.append(
        f"{''.join(concat_inputs)}concat=n={len(concat_inputs)}:v=0:a=1[out]"
    )

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "libmp3lame", "-q:a", "2",
        str(output)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg merge failed: %s", result.stderr)
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)


# ==========================
# RUNPOD SERVERLESS CLIENT
# ==========================

def _call_serverless_tts(
    endpoint: runpod.Endpoint,
    text: str,
    voice_ref_b64: Optional[str] = None,
) -> tuple[bytes, int]:
    """Call the RunPod serverless endpoint for a single TTS segment.

    Args:
        endpoint: RunPod Endpoint instance
        text: Text to synthesize
        voice_ref_b64: Optional base64-encoded voice reference WAV

    Returns:
        Tuple of (wav_bytes, duration_ms)

    Raises:
        RuntimeError: If the job fails or times out
    """
    payload = {
        "text": text,
        "language_id": "pl",
        "cfg_weight": CHATTERBOX_CFG_WEIGHT,
        "exaggeration": CHATTERBOX_EXAGGERATION,
    }
    if voice_ref_b64:
        payload["voice_ref_base64"] = voice_ref_b64

    job = endpoint.run({"input": payload})
    logger.debug("Submitted job %s for text: %s...", job.job_id, text[:50])

    try:
        output = job.output(timeout=RUNPOD_REQUEST_TIMEOUT)
    except TimeoutError:
        logger.error("Job timed out after %ds for: %s...", RUNPOD_REQUEST_TIMEOUT, text[:50])
        try:
            job.cancel()
        except Exception:
            pass
        raise RuntimeError(f"TTS generation timed out for: {text[:50]}...")

    if output is None:
        status = job.status()
        raise RuntimeError(f"TTS job failed with status: {status}")

    audio_b64 = output["audio_base64"]
    duration_ms = output["duration_ms"]
    wav_bytes = base64.b64decode(audio_b64)

    return wav_bytes, duration_ms


# ==========================
# MAIN GENERATION
# ==========================

def load_dialogue(path: Union[Path, str], storage: StorageBackend = None) -> dict:
    """Load dialogue from file."""
    if storage is not None:
        content = storage.read_text(str(path))
        return json.loads(content)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_segments(data: dict):
    """Extract segments with emphasis and source data."""
    segments = []
    speakers = []

    def track(s):
        if s not in speakers:
            speakers.append(s)
        return s

    for d in data.get("script", []):
        emphasis = d.get("emphasis", [])
        source = d.get("source")
        segments.append((track(d["speaker"]), d["text"], emphasis, source))

    for d in data.get("cooldown", []):
        emphasis = d.get("emphasis", [])
        source = d.get("source")
        segments.append((track(d["speaker"]), d["text"], emphasis, source))

    if q := data.get("viewer_question"):
        q_emphasis = data.get("viewer_question_emphasis", [])
        segments.append(("__NARRATOR__", q, q_emphasis, None))

    first = speakers[0] if speakers else "A"
    return [(first if s == "__NARRATOR__" else s, t, e, src) for s, t, e, src in segments], speakers


def voice_ref(name: str) -> Optional[str]:
    """Get voice reference path for a voice name."""
    return VOICE_REFS.get(name)


def generate_audio(
    dialogue_path: Union[Path, str],
    output: Union[Path, str],
    timeline: Union[Path, str],
    voice_a: str,
    voice_b: str,
    storage: StorageBackend = None
):
    """Generate audio from dialogue using Chatterbox TTS on RunPod Serverless.

    Args:
        dialogue_path: Path to dialogue JSON file
        output: Path to output audio file
        timeline: Path to output timeline file
        voice_a: Voice name for speaker A
        voice_b: Voice name for speaker B
        storage: Optional storage backend. If None, uses local filesystem.
    """
    logger.info("Generating audio from dialogue: %s", dialogue_path)

    # Validate config
    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        raise RuntimeError("RUNPOD_API_KEY environment variable not set")
    if not RUNPOD_ENDPOINT_ID:
        raise RuntimeError(
            "RUNPOD_ENDPOINT_ID environment variable not set.\n"
            "Create a serverless endpoint at https://www.runpod.io/console/serverless"
        )

    runpod.api_key = api_key
    endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)

    data = load_dialogue(dialogue_path, storage)
    segments, speakers = extract_segments(data)
    logger.info("Found %d segments with speakers: %s", len(segments), speakers)

    # Pre-encode voice reference files as base64 (done once, reused for all segments)
    voices = [voice_ref(voice_a), voice_ref(voice_b)]
    voice_map = {s: voices[i % 2] for i, s in enumerate(speakers)}

    voice_b64_map = {}
    for speaker, local_path in voice_map.items():
        if local_path and Path(local_path).exists():
            wav_bytes = Path(local_path).read_bytes()
            voice_b64_map[speaker] = base64.b64encode(wav_bytes).decode("utf-8")
            logger.info("Encoded voice reference for %s: %s (%d bytes)",
                        speaker, local_path, len(wav_bytes))
        else:
            voice_b64_map[speaker] = None

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        audio_files = []
        durations = []

        for i, (speaker, text, _emphasis, _source) in enumerate(segments):
            out = tmp / f"seg_{i:03}.wav"
            logger.info("Generating segment %d/%d: %s...",
                        i + 1, len(segments), text[:50])

            wav_bytes, dur = _call_serverless_tts(
                endpoint, text, voice_b64_map[speaker]
            )

            out.write_bytes(wav_bytes)
            audio_files.append(out)
            durations.append(dur)

        logger.info("Merging %d audio segments", len(audio_files))

        # Create temp output for merging
        temp_output = tmp / "merged.mp3"
        merge_audio(audio_files, temp_output, PAUSE_BETWEEN_SEGMENTS_MS)

        # Copy to final destination
        if storage is not None:
            storage.copy_from_local(temp_output, str(output))
        else:
            import shutil
            output = Path(output)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp_output, output)

    # Build timeline
    timeline_segments = []
    t = 0

    output_name = Path(output).name if isinstance(output, (str, Path)) else output

    for i, ((speaker, text, emphasis, source), dur) in enumerate(zip(segments, durations)):
        base = {
            "speaker": speaker,
            "text": text,
            "start_ms": t,
            "end_ms": t + dur,
            "emphasis": emphasis
        }
        if source:
            base["source"] = source

        timeline_segments.extend(chunk_segment(base))
        t += dur

        if i < len(segments) - 1:
            timeline_segments.append({
                "type": "pause",
                "start_ms": t,
                "end_ms": t + PAUSE_BETWEEN_SEGMENTS_MS
            })
            t += PAUSE_BETWEEN_SEGMENTS_MS

    timeline_data = {
        "audio_file": output_name,
        "segments": timeline_segments
    }

    timeline_json = json.dumps(timeline_data, ensure_ascii=False, indent=2)

    if storage is not None:
        storage.write_text(str(timeline), timeline_json)
    else:
        timeline = Path(timeline)
        with open(timeline, "w", encoding="utf-8") as f:
            f.write(timeline_json)

    total_duration_s = sum(durations) / 1000
    logger.info("Audio generated: %s (%.1fs, %d chunks)", output, total_duration_s, len(timeline_segments))


# ==========================
# CLI
# ==========================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("dialogue", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("-t", "--timeline", type=Path, required=True)
    p.add_argument("--voice-a", default=DEFAULT_VOICE_A)
    p.add_argument("--voice-b", default=DEFAULT_VOICE_B)
    args = p.parse_args()

    generate_audio(
        args.dialogue,
        args.output,
        args.timeline,
        args.voice_a,
        args.voice_b
    )


if __name__ == "__main__":
    main()
