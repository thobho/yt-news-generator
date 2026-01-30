#!/usr/bin/env python3
"""
Generate audio from dialogue JSON using Chatterbox TTS on RunPod Serverless.

All dialogue lines are joined into a single text and sent as one TTS request.
The raw WAV result is saved directly without any postprocessing.

Usage:
    python generate_audio_runpod.py dialogue.json -o output.wav

Environment variables:
    RUNPOD_API_KEY: Your RunPod API key (required)
    RUNPOD_ENDPOINT_ID: Your RunPod serverless endpoint ID (required)
    CHATTERBOX_CFG_WEIGHT: Speed control 0.2-1.0 (default 0.6)
    CHATTERBOX_EXAGGERATION: Expressiveness 0.25-2.0 (default 0.9)
"""

import argparse
import json
from pathlib import Path
from typing import Union

from logging_config import get_logger
from storage import StorageBackend
from tts_client import TTSClient

logger = get_logger(__name__)

DEFAULT_VOICE = "male"

VOICE_REFS = {
    "male": "data/voices/male.wav",
    "female": "data/voices/female.wav",
}


def load_dialogue(path: Union[Path, str], storage: StorageBackend = None) -> dict:
    """Load dialogue from file."""
    if storage is not None:
        content = storage.read_text(str(path))
        return json.loads(content)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_text(data: dict) -> str:
    """Extract all dialogue lines and join into a single text."""
    lines = []
    for d in data.get("script", []):
        lines.append(d["text"])
    for d in data.get("cooldown", []):
        lines.append(d["text"])
    if q := data.get("viewer_question"):
        lines.append(q)
    return " ".join(lines)


def generate_audio(
    dialogue_path: Union[Path, str],
    output: Union[Path, str],
    timeline: Union[Path, str] = None,
    voice_a: str = DEFAULT_VOICE,
    voice_b: str = DEFAULT_VOICE,
    storage: StorageBackend = None
):
    """Generate audio from dialogue using Chatterbox TTS on RunPod Serverless.

    Args:
        dialogue_path: Path to dialogue JSON file
        output: Path to output audio file (raw WAV)
        timeline: Unused, kept for API compatibility
        voice_a: Voice name (used for voice reference)
        voice_b: Unused, kept for API compatibility
        storage: Optional storage backend
    """
    logger.info("Generating audio from dialogue: %s", dialogue_path)

    client = TTSClient()

    data = load_dialogue(dialogue_path, storage)
    full_text = extract_text(data)
    logger.info("Combined text (%d chars): %s...", len(full_text), full_text[:80])

    voice_path = VOICE_REFS.get(voice_a)

    wav_bytes = client.generate(text=full_text, voice_ref_path=voice_path)

    # Save raw WAV directly
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if storage is not None:
        import os
        import tempfile as _tf
        with _tf.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name
        storage.copy_from_local(Path(tmp_path), str(output))
        os.unlink(tmp_path)
    else:
        output.write_bytes(wav_bytes)

    logger.info("Audio saved: %s", output)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("dialogue", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--voice", default=DEFAULT_VOICE)
    args = p.parse_args()

    generate_audio(args.dialogue, args.output, voice_a=args.voice)


if __name__ == "__main__":
    main()
