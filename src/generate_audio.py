#!/usr/bin/env python3
"""
Generate audio from dialogue JSON using ElevenLabs API
and produce a timeline with semantic subtitle chunks.

Usage:
    python generate_audio.py dialogue.json -o final_audio.mp3 -t timeline.json
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import re
from pathlib import Path
from typing import Union

from elevenlabs import ElevenLabs

from logging_config import get_logger
from storage import StorageBackend

logger = get_logger(__name__)


# ==========================
# CONFIG
# ==========================

DEFAULT_VOICE_A = "Adam"
DEFAULT_VOICE_B = "Bella"
PAUSE_BETWEEN_SEGMENTS_MS = 300

VOICE_IDS = {
    "Adam": "pNInz6obpgDQGcFmaJgB",
    "Bella": "EXAVITQu4vr4xnSDxMaL",
    "Antoni": "ErXwobaYiN019PkySvjV",
    "Josh": "TxGEqnHWrfWFTfGW9XjX",
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
        # Add emphasis words that appear in this chunk
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


def generate_audio_segment(client, text, voice_id, output_path) -> int:
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id="eleven_multilingual_v2",
    )
    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    return get_audio_duration_ms(output_path)


def merge_audio(files: list[Path], output: Path, pause_ms: int):
    temp = files[0].parent
    silence = temp / "silence.mp3"
    concat = temp / "concat.txt"

    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(pause_ms / 1000),
            silence
        ],
        capture_output=True,
        check=True,
    )

    with open(concat, "w") as f:
        for i, file in enumerate(files):
            f.write(f"file '{file}'\n")
            if i < len(files) - 1:
                f.write(f"file '{silence}'\n")

    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat,
            "-c:a", "libmp3lame",
            output
        ],
        capture_output=True,
        check=True,
    )


# ==========================
# MAIN GENERATION
# ==========================

def load_dialogue(path: Union[Path, str], storage: StorageBackend = None) -> dict:
    """Load dialogue from file.

    Args:
        path: Path to dialogue file
        storage: Optional storage backend. If None, reads from local filesystem.
    """
    if storage is not None:
        content = storage.read_text(str(path))
        return json.loads(content)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_segments(data: dict):
    """Extract segments with emphasis and source data.

    Returns list of (speaker, text, emphasis, source) tuples and list of speakers.
    """
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

    return segments, speakers


def voice_id(name: str) -> str:
    return VOICE_IDS.get(name, name)


def generate_audio(
    dialogue_path: Union[Path, str],
    output: Union[Path, str],
    timeline: Union[Path, str],
    voice_a: str,
    voice_b: str,
    storage: StorageBackend = None
):
    """Generate audio from dialogue.

    Args:
        dialogue_path: Path to dialogue JSON file
        output: Path to output audio file
        timeline: Path to output timeline file
        voice_a: Voice name for speaker A
        voice_b: Voice name for speaker B
        storage: Optional storage backend. If None, uses local filesystem.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    logger.info("Generating audio from dialogue: %s", dialogue_path)
    eleven_client = ElevenLabs(api_key=api_key)

    data = load_dialogue(dialogue_path, storage)
    segments, speakers = extract_segments(data)
    logger.info("Found %d segments with speakers: %s", len(segments), speakers)

    voices = [voice_id(voice_a), voice_id(voice_b)]
    voice_map = {s: voices[i % 2] for i, s in enumerate(speakers)}
    logger.debug("Voice mapping: %s", voice_map)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        audio_files = []
        durations = []

        for i, (speaker, text, _emphasis, _source) in enumerate(segments):
            out = tmp / f"seg_{i:03}.mp3"
            logger.debug("Generating segment %d/%d: %s...", i + 1, len(segments), text[:50])
            dur = generate_audio_segment(eleven_client, text, voice_map[speaker], out)
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
