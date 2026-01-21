#!/usr/bin/env python3
"""
Generate audio from dialogue JSON using ElevenLabs API.

Usage:
    python generate_audio.py output.json -o final_audio.mp3
    python generate_audio.py output.json --voice-a "Adam" --voice-b "Rachel" -o final_audio.mp3
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from elevenlabs import ElevenLabs


DEFAULT_VOICE_A = "Adam"
DEFAULT_VOICE_B = "Rachel"
PAUSE_BETWEEN_SEGMENTS_MS = 300

# Hardcoded voice IDs for common ElevenLabs voices
VOICE_IDS = {
    "Adam": "pNInz6obpgDQGcFmaJgB",
    "Rachel": "21m00Tcm4TlvDq8ikWAM",
    "Domi": "AZnzlk1XvdvUeBnXmlld",
    "Bella": "EXAVITQu4vr4xnSDxMaL",
    "Antoni": "ErXwobaYiN019PkySvjV",
    "Elli": "MF3mGyEYCl7XYWbV9V6O",
    "Josh": "TxGEqnHWrfWFTfGW9XjX",
    "Arnold": "VR6AewLTigWG4xSOukaG",
    "Sam": "yoZ06aMxZJJ28mfd3POQ",
}


def load_dialogue(dialogue_path: Path) -> dict:
    """Load dialogue data from JSON file."""
    with open(dialogue_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_segments(dialogue_data: dict) -> list[tuple[str, str]]:
    """
    Extract all text segments in order with their speaker.
    Returns list of (speaker, text) tuples.
    Order: hook -> dialogue -> common_ground -> viewer_question -> call_to_action
    """
    segments = []

    # Hook (narrator = Speaker A)
    if hook := dialogue_data.get("hook"):
        segments.append(("A", hook))

    # Dialogue entries
    for entry in dialogue_data.get("dialogue", []):
        segments.append((entry["speaker"], entry["text"]))

    # Common ground entries
    for entry in dialogue_data.get("common_ground", []):
        segments.append((entry["speaker"], entry["text"]))

    # Viewer question (narrator = Speaker A)
    if viewer_question := dialogue_data.get("viewer_question"):
        segments.append(("A", viewer_question))

    # Call to action (narrator = Speaker A)
    if call_to_action := dialogue_data.get("call_to_action"):
        segments.append(("A", call_to_action))

    return segments


def get_audio_duration_ms(audio_path: Path) -> int:
    """Get duration of audio file in milliseconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path)
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    duration_seconds = float(result.stdout.strip())
    return int(duration_seconds * 1000)


def generate_audio_segment(
    client: ElevenLabs, text: str, voice: str, output_path: Path
) -> int:
    """Generate audio for a single text segment using ElevenLabs. Returns duration in ms."""
    audio_generator = client.text_to_speech.convert(
        voice_id=voice,
        text=text,
        model_id="eleven_multilingual_v2",
    )

    # Write audio bytes to file
    with open(output_path, "wb") as f:
        for chunk in audio_generator:
            f.write(chunk)

    return get_audio_duration_ms(output_path)


def merge_audio_files(audio_files: list[Path], output_path: Path, pause_ms: int) -> None:
    """Merge multiple audio files into a single MP3 with pauses between segments using ffmpeg."""
    if not audio_files:
        raise ValueError("No audio files to merge")

    # Create a concat file list for ffmpeg with silence between segments
    temp_dir = audio_files[0].parent
    concat_list = temp_dir / "concat_list.txt"
    silence_file = temp_dir / "silence.mp3"

    # Generate silence file using ffmpeg
    silence_seconds = pause_ms / 1000.0
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(silence_seconds),
            "-q:a", "9",
            str(silence_file)
        ],
        capture_output=True,
        check=True,
    )

    # Write concat list file
    with open(concat_list, "w") as f:
        for i, audio_file in enumerate(audio_files):
            f.write(f"file '{audio_file}'\n")
            if i < len(audio_files) - 1:
                f.write(f"file '{silence_file}'\n")

    # Merge using ffmpeg concat
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:a", "libmp3lame", "-q:a", "2",
            str(output_path)
        ],
        capture_output=True,
        check=True,
    )


def get_voice_id(voice_name: str) -> str:
    """Get voice ID for a voice name. Uses hardcoded IDs or treats input as ID."""
    # Check if it's a known voice name
    if voice_name in VOICE_IDS:
        return VOICE_IDS[voice_name]
    # Assume it's already a voice ID
    return voice_name


def get_voice_map(voice_a_name: str, voice_b_name: str) -> dict:
    """Get voice IDs for the specified voice names."""
    return {
        "A": get_voice_id(voice_a_name),
        "B": get_voice_id(voice_b_name),
    }


def generate_audio(
    dialogue_path: Path,
    output_path: Path,
    timeline_path: Path | None = None,
    voice_a: str = DEFAULT_VOICE_A,
    voice_b: str = DEFAULT_VOICE_B,
) -> dict:
    """Generate audio from dialogue JSON file. Returns timeline data."""
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY environment variable not set")

    client = ElevenLabs(api_key=api_key)

    # Load dialogue and extract segments
    dialogue_data = load_dialogue(dialogue_path)
    segments = extract_segments(dialogue_data)

    if not segments:
        raise ValueError("No segments found in dialogue")

    # Get voice IDs
    voice_map = get_voice_map(voice_a, voice_b)

    print(f"Generating audio for {len(segments)} segments...", file=sys.stderr)

    # Generate audio for each segment in temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        audio_files = []
        segment_durations = []

        for i, (speaker, text) in enumerate(segments):
            output_file = temp_path / f"segment_{i:03d}.mp3"
            voice_id = voice_map[speaker]

            print(f"  [{i + 1}/{len(segments)}] Speaker {speaker}: {text[:50]}...", file=sys.stderr)
            duration_ms = generate_audio_segment(client, text, voice_id, output_file)
            audio_files.append(output_file)
            segment_durations.append(duration_ms)

        # Merge all audio files
        print("Merging audio segments...", file=sys.stderr)
        merge_audio_files(audio_files, output_path, PAUSE_BETWEEN_SEGMENTS_MS)

    # Build timeline data
    timeline_segments = []
    current_time_ms = 0

    for i, ((speaker, text), duration_ms) in enumerate(zip(segments, segment_durations)):
        timeline_segments.append({
            "speaker": speaker,
            "text": text,
            "start_ms": current_time_ms,
            "end_ms": current_time_ms + duration_ms,
        })
        current_time_ms += duration_ms
        # Add pause after each segment except the last
        if i < len(segments) - 1:
            current_time_ms += PAUSE_BETWEEN_SEGMENTS_MS

    timeline_data = {
        "audio_file": output_path.name,
        "segments": timeline_segments,
    }

    # Write timeline file if path provided
    if timeline_path:
        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump(timeline_data, f, ensure_ascii=False, indent=2)
        print(f"Timeline generated: {timeline_path}", file=sys.stderr)

    print(f"Audio generated: {output_path}", file=sys.stderr)
    return timeline_data


def main():
    parser = argparse.ArgumentParser(
        description="Generate audio from dialogue JSON using ElevenLabs"
    )
    parser.add_argument("dialogue", type=Path, help="Path to dialogue JSON file")
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="Output MP3 file path"
    )
    parser.add_argument(
        "-t", "--timeline", type=Path, help="Output timeline JSON file path"
    )
    parser.add_argument(
        "--voice-a",
        default=DEFAULT_VOICE_A,
        help=f"Voice name for Speaker A (default: {DEFAULT_VOICE_A})",
    )
    parser.add_argument(
        "--voice-b",
        default=DEFAULT_VOICE_B,
        help=f"Voice name for Speaker B (default: {DEFAULT_VOICE_B})",
    )

    args = parser.parse_args()

    if not args.dialogue.exists():
        print(f"Error: Dialogue file not found: {args.dialogue}", file=sys.stderr)
        sys.exit(1)

    try:
        generate_audio(
            args.dialogue, args.output, args.timeline, args.voice_a, args.voice_b
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error generating audio: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
