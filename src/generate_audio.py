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
import tempfile
import re
from pathlib import Path
from typing import Union

from elevenlabs import ElevenLabs

from align_audio import transcribe_with_timestamps, align_text_to_audio
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

MIN_SOURCE_DURATION_MS = 5000  # Minimum 5 seconds per source display
MIN_CHUNK_WORDS = 3
MAX_CHUNK_WORDS = 8


def chunk_segment_aligned(
    aligned_words: list[dict],
    speaker: str,
    emphasis: list[str],
    sources: list,
    start_ms: int,
    end_ms: int,
) -> list[dict]:
    """
    Build subtitle chunks from Whisper word-aligned timestamps.

    Groups words into readable chunks (MIN_CHUNK_WORDS–MAX_CHUNK_WORDS) while
    respecting natural break points (punctuation).
    """
    if not aligned_words:
        return []

    source_ranges = distribute_sources(sources, start_ms, end_ms)

    chunks = []
    current_words = []
    current_word_data = []
    current_start = None

    for word_data in aligned_words:
        word = word_data["word"]
        word_start = word_data["start_ms"]
        word_end = word_data["end_ms"]

        if current_start is None:
            current_start = word_start

        current_words.append(word)
        current_word_data.append({"word": word, "start_ms": word_start, "end_ms": word_end})

        ends_sentence = word.rstrip()[-1] in ".?!" if word.strip() else False
        has_comma = "," in word
        word_count = len(current_words)

        should_break = (
            word_count >= MAX_CHUNK_WORDS
            or (word_count >= MIN_CHUNK_WORDS and (ends_sentence or has_comma))
        )

        if should_break:
            chunk_text = " ".join(current_words)
            chunk_data = {
                "speaker": speaker,
                "text": chunk_text,
                "start_ms": current_start,
                "end_ms": word_end,
                "chunk": True,
                "words": list(current_word_data),
            }

            if emphasis:
                chunk_lower = chunk_text.lower()
                chunk_emphasis = []
                for phrase in emphasis:
                    phrase_lower = phrase.lower()
                    if phrase_lower in chunk_lower:
                        chunk_emphasis.append(phrase)
                    else:
                        for emp_word in phrase_lower.split():
                            if len(emp_word) > 2 and re.search(
                                rf"\b{re.escape(emp_word)}\b", chunk_lower
                            ):
                                chunk_emphasis.append(emp_word)
                if chunk_emphasis:
                    chunk_data["emphasis"] = chunk_emphasis

            chunk_midpoint = current_start + (word_end - current_start) // 2
            active_source = get_source_for_time(source_ranges, chunk_midpoint)
            if active_source:
                chunk_data["source"] = active_source

            chunks.append(chunk_data)
            current_words = []
            current_word_data = []
            current_start = None

    if current_words:
        chunk_text = " ".join(current_words)
        chunk_data = {
            "speaker": speaker,
            "text": chunk_text,
            "start_ms": current_start,
            "end_ms": aligned_words[-1]["end_ms"],
            "chunk": True,
            "words": list(current_word_data),
        }
        if emphasis:
            chunk_lower = chunk_text.lower()
            chunk_emphasis = [p for p in emphasis if p.lower() in chunk_lower]
            if chunk_emphasis:
                chunk_data["emphasis"] = chunk_emphasis
        chunks.append(chunk_data)

    return chunks


def distribute_sources(sources: list, start_ms: int, end_ms: int) -> list[dict]:
    """
    Distribute sources evenly across a time range.

    Each source gets at least MIN_SOURCE_DURATION_MS. If there are too many
    sources to fit, drop the last ones until all remaining sources have
    sufficient display time.

    Returns list of dicts with source data and time ranges:
    [{"source": {...}, "start_ms": ..., "end_ms": ...}, ...]
    """
    if not sources:
        return []

    duration = end_ms - start_ms
    if duration <= 0:
        return []

    # Calculate how many sources can fit with minimum duration
    max_sources = duration // MIN_SOURCE_DURATION_MS
    if max_sources == 0:
        # Not enough time for even one source at minimum duration
        # Still show the first source for the entire duration
        return [{"source": sources[0], "start_ms": start_ms, "end_ms": end_ms}]

    # Take only as many sources as can fit
    usable_sources = sources[:max_sources]

    # Distribute evenly
    time_per_source = duration // len(usable_sources)
    result = []
    current_time = start_ms

    for i, source in enumerate(usable_sources):
        source_end = current_time + time_per_source
        # Last source gets any remaining time
        if i == len(usable_sources) - 1:
            source_end = end_ms
        result.append({
            "source": source,
            "start_ms": current_time,
            "end_ms": source_end
        })
        current_time = source_end

    return result


def get_source_for_time(source_ranges: list[dict], time_ms: int) -> dict | None:
    """Get the source that should be displayed at a given time."""
    for sr in source_ranges:
        if sr["start_ms"] <= time_ms < sr["end_ms"]:
            return sr["source"]
    return None


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
    """Extract segments with emphasis and sources data.

    Returns list of (speaker, text, emphasis, sources) tuples and list of speakers.
    Sources is now an array of source objects.
    """
    segments = []
    speakers = []

    def track(s):
        if s not in speakers:
            speakers.append(s)
        return s

    for d in data.get("script", []):
        emphasis = d.get("emphasis", [])
        sources = d.get("sources", [])
        segments.append((track(d["speaker"]), d["text"], emphasis, sources))

    for d in data.get("cooldown", []):
        emphasis = d.get("emphasis", [])
        sources = d.get("sources", [])
        segments.append((track(d["speaker"]), d["text"], emphasis, sources))

    return segments, speakers


def voice_id(name: str) -> str:
    return VOICE_IDS.get(name, name)


def generate_audio(
    dialogue_path: Union[Path, str],
    output: Union[Path, str],
    timeline: Union[Path, str],
    voice_a: str,
    voice_b: str,
    storage: StorageBackend = None,
    language: str = "pl",
):
    """Generate audio from dialogue.

    Args:
        dialogue_path: Path to dialogue JSON file
        output: Path to output audio file
        timeline: Path to output timeline file
        voice_a: Voice name for speaker A
        voice_b: Voice name for speaker B
        storage: Optional storage backend. If None, uses local filesystem.
        language: Language code for Whisper alignment (e.g. "pl", "en")
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
        alignments = []
        logger.info("Whisper alignment enabled (language=%s)", language)

        for i, (speaker, text, _emphasis, _sources) in enumerate(segments):
            out = tmp / f"seg_{i:03}.mp3"
            logger.debug("Generating segment %d/%d: %s...", i + 1, len(segments), text[:50])
            dur = generate_audio_segment(eleven_client, text, voice_map[speaker], out)
            audio_files.append(out)
            durations.append(dur)

            alignment = None
            try:
                whisper_words = transcribe_with_timestamps(out, language=language)
                alignment = align_text_to_audio(text, whisper_words, start_offset_ms=0)
                logger.debug("Aligned %d words for segment %d", len(alignment), i + 1)
            except Exception as e:
                logger.warning("Whisper alignment failed for segment %d: %s", i + 1, e)
            alignments.append(alignment)

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
            chunks = chunk_segment_aligned(aligned_offset, speaker, emphasis, sources, t, t + dur)
            timeline_segments.extend(chunks)
            logger.debug("Whisper aligned segment %d (%d chunks)", i + 1, len(chunks))
        else:
            logger.warning("No alignment for segment %d, skipping chunks", i + 1)

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
