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
import tempfile
from pathlib import Path
from typing import Union

from generate_audio import (
    PAUSE_BETWEEN_SEGMENTS_MS,
    chunk_segment,
    extract_segments,
    merge_audio,
)
from logging_config import get_logger
from storage import StorageBackend
from storage_config import get_data_storage
from tts_client import TTSClient

logger = get_logger(__name__)

DEFAULT_VOICE_A = "male"
DEFAULT_VOICE_B = "female"

VOICE_REFS = {
    "male": "voices/male.wav",
    "female": "voices/female.wav",
}


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
    voice_a: str = DEFAULT_VOICE_A,
    voice_b: str = DEFAULT_VOICE_B,
    storage: StorageBackend = None,
):
    """Generate audio from dialogue using Chatterbox TTS on RunPod Serverless.

    Each dialogue line is generated as a separate segment with the appropriate
    voice reference (male/female). Segments are merged with silence gaps and
    converted to MP3. A timeline.json is produced for subtitle rendering.

    Args:
        dialogue_path: Path to dialogue JSON file
        output: Path to output audio file (MP3)
        timeline: Path to output timeline JSON file
        voice_a: Voice name for first speaker (default "male")
        voice_b: Voice name for second speaker (default "female")
        storage: Optional storage backend
    """
    logger.info("Generating audio from dialogue: %s", dialogue_path)

    client = TTSClient()

    data = load_dialogue(dialogue_path, storage)
    segments, speakers = extract_segments(data)
    logger.info("Found %d segments with speakers: %s", len(segments), speakers)

    # Build voice map: first speaker -> voice_a, second speaker -> voice_b
    voice_refs = [VOICE_REFS.get(voice_a), VOICE_REFS.get(voice_b)]
    voice_map = {s: voice_refs[i % 2] for i, s in enumerate(speakers)}
    logger.debug("Voice mapping: %s", voice_map)

    # Voice files live under data/ storage (not run storage)
    data_storage = get_data_storage() if storage is not None else None

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        audio_files = []
        durations = []

        for i, (speaker, text, _emphasis, _source) in enumerate(segments):
            out = tmp / f"seg_{i:03}.wav"
            logger.debug(
                "Generating segment %d/%d (%s): %s...",
                i + 1, len(segments), speaker, text[:50],
            )
            result = client.generate_with_metadata(
                text=text,
                voice_ref_path=voice_map[speaker],
                storage=data_storage,
            )
            out.write_bytes(result["audio"])
            audio_files.append(out)
            durations.append(result["duration_ms"])

        logger.info("Merging %d audio segments", len(audio_files))

        # Merge WAV segments into MP3 with silence gaps
        temp_output = tmp / "merged.mp3"
        merge_audio(audio_files, temp_output, PAUSE_BETWEEN_SEGMENTS_MS)

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

        for i, ((speaker, text, emphasis, source), dur) in enumerate(
            zip(segments, durations)
        ):
            base = {
                "speaker": speaker,
                "text": text,
                "start_ms": t,
                "end_ms": t + dur,
                "emphasis": emphasis,
            }
            if source:
                base["source"] = source

            timeline_segments.extend(chunk_segment(base))
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
    p.add_argument("--voice-a", default=DEFAULT_VOICE_A)
    p.add_argument("--voice-b", default=DEFAULT_VOICE_B)
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
