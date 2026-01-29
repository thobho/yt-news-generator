#!/usr/bin/env python3
"""
Test script for Chatterbox TTS on RunPod Serverless.

Prerequisites:
    1. RunPod account with credits: https://runpod.io
    2. API key set: export RUNPOD_API_KEY=your_key
    3. Serverless endpoint created and ID set: export RUNPOD_ENDPOINT_ID=your_endpoint_id

Usage:
    python scripts/test_chatterbox_runpod.py
"""

import os
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def check_prerequisites():
    """Check that all prerequisites are met."""
    # Check RunPod API key
    if not os.environ.get("RUNPOD_API_KEY"):
        print("✗ RUNPOD_API_KEY not set")
        print("  Get your API key from: https://runpod.io/console/user/settings")
        print("  Then run: export RUNPOD_API_KEY=your_key")
        return False
    print("✓ RUNPOD_API_KEY found")

    # Check RunPod Endpoint ID
    if not os.environ.get("RUNPOD_ENDPOINT_ID"):
        print("✗ RUNPOD_ENDPOINT_ID not set")
        print("  Create a serverless endpoint at: https://www.runpod.io/console/serverless")
        print("  Then run: export RUNPOD_ENDPOINT_ID=your_endpoint_id")
        return False
    print("✓ RUNPOD_ENDPOINT_ID found")

    return True


def run_test():
    """Run a test audio generation."""
    from generate_audio_runpod import generate_audio

    project_root = Path(__file__).parent.parent

    # Use existing dialogue for testing
    dialogue_path = project_root / "output/run_2026-01-23_16-01-36/dialogue.json"

    if not dialogue_path.exists():
        # Create a simple test dialogue
        import json
        dialogue_path = Path(tempfile.mktemp(suffix=".json"))
        test_dialogue = {
            "topic_id": "test",
            "scene": "Test scene",
            "hook": "This is a test.",
            "script": [
                {
                    "speaker": "Adam",
                    "text": "Hello, this is a test of the Chatterbox text to speech system.",
                    "emphasis": ["test", "Chatterbox"]
                },
                {
                    "speaker": "Ewa",
                    "text": "The audio quality should be good for YouTube shorts.",
                    "emphasis": ["quality", "YouTube"]
                }
            ],
            "climax_line": "Testing complete.",
            "viewer_question": "What do you think of this voice?"
        }
        dialogue_path.write_text(json.dumps(test_dialogue, indent=2))
        print(f"Created test dialogue at {dialogue_path}")

    output_dir = project_root / "output/chatterbox_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_audio = output_dir / "test_audio_runpod.mp3"
    output_timeline = output_dir / "test_timeline_runpod.json"

    print(f"\nGenerating audio...")
    print(f"  Dialogue: {dialogue_path}")
    print(f"  Output: {output_audio}")
    print(f"  Timeline: {output_timeline}")

    generate_audio(
        dialogue_path=dialogue_path,
        output=output_audio,
        timeline=output_timeline,
        voice_a="neutral",
        voice_b="neutral"
    )

    print(f"\n✓ Audio generated successfully!")
    print(f"  Audio file: {output_audio}")
    print(f"  Timeline: {output_timeline}")


def main():
    print("=" * 60)
    print("Chatterbox TTS on RunPod Serverless - Test Script")
    print("=" * 60)
    print()

    if not check_prerequisites():
        sys.exit(1)

    print()
    print("=" * 60)
    print("Running audio generation test...")
    print("=" * 60)

    try:
        run_test()
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print()
    print("=" * 60)
    print("Test completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
