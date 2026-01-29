#!/usr/bin/env python3
"""
Test script for Chatterbox TTS on EC2.

Uses the same AWS credentials and key pair as deploy-ec2.sh.

Prerequisites:
    1. AWS credentials set via environment variables:
       - AWS_ACCESS_KEY_ID
       - AWS_SECRET_ACCESS_KEY
       - AWS_DEFAULT_REGION (optional, defaults to us-east-1)

    2. EC2 key pair at: credentials/yt-news-generator-key.pem
       (Created by deploy-ec2.sh)

Usage:
    python scripts/test_chatterbox_ec2.py
"""

import os
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def check_prerequisites():
    """Check that all prerequisites are met."""
    project_root = Path(__file__).parent.parent

    # Check AWS credentials
    if not os.environ.get("AWS_ACCESS_KEY_ID") or not os.environ.get("AWS_SECRET_ACCESS_KEY"):
        print("✗ AWS credentials not found in environment")
        print("  Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
        return False
    print("✓ AWS credentials found")

    # Check SSH key
    key_path = project_root / "credentials/yt-news-generator-key.pem"
    if not key_path.exists():
        print(f"✗ SSH key not found: {key_path}")
        print("  Run deploy-ec2.sh first to create the key pair, or create it manually")
        return False
    print(f"✓ SSH key found: {key_path}")

    return True


def run_test():
    """Run a test audio generation."""
    from generate_audio_chatterbox import generate_audio

    project_root = Path(__file__).parent.parent

    # Use existing dialogue for testing
    dialogue_path = project_root / "output/run_2026-01-27_22-54-19/dialogue.json"

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

    output_audio = output_dir / "test_audio.mp3"
    output_timeline = output_dir / "test_timeline.json"

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
    print("Chatterbox TTS on EC2 - Test Script")
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
