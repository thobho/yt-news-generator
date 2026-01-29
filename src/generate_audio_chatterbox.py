#!/usr/bin/env python3
"""
Generate audio from dialogue JSON using Chatterbox TTS on AWS EC2.

This module spins up a g4dn.xlarge GPU instance, installs Chatterbox TTS,
generates audio, downloads the result, and terminates the instance.

Usage:
    python generate_audio_chatterbox.py dialogue.json -o final_audio.mp3 -t timeline.json

The interface is identical to generate_audio.py for easy swapping.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import re
from pathlib import Path
from typing import Union, Optional

import boto3
from botocore.exceptions import ClientError

from logging_config import get_logger
from storage import StorageBackend

logger = get_logger(__name__)


# ==========================
# CONFIG
# ==========================

DEFAULT_VOICE_A = "neutral"
DEFAULT_VOICE_B = "neutral"
PAUSE_BETWEEN_SEGMENTS_MS = 300

# EC2 Configuration - uses same credentials as deploy-ec2.sh
EC2_INSTANCE_TYPE = "g4dn.xlarge"
EC2_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

# Ubuntu 22.04 LTS x86_64 AMIs for GPU instances (g4dn requires x86_64, not ARM)
EC2_AMI_MAP = {
    "us-east-1": "ami-0c7217cdde317cfec",
    "us-east-2": "ami-05fb0b8c1424f266b",
    "us-west-1": "ami-0ce2cb35386fc22e9",
    "us-west-2": "ami-008fe2fc65df48dac",
    "eu-west-1": "ami-0905a3c97561e0b69",
    "eu-central-1": "ami-0faab6bdbac9486fb",
}

# Use same key/security group as main deployment
PROJECT_ROOT = Path(__file__).parent.parent
EC2_KEY_NAME = os.environ.get("EC2_KEY_NAME", "yt-news-generator-key")
EC2_SECURITY_GROUP = os.environ.get("EC2_SECURITY_GROUP", "yt-news-generator-sg")
EC2_SUBNET_ID = os.environ.get("EC2_SUBNET_ID")  # Optional

# Spot instance configuration - use spot by default (cheaper, different quota)
EC2_USE_SPOT = os.environ.get("EC2_USE_SPOT", "true").lower() in ("true", "1", "yes")
EC2_SPOT_MAX_PRICE = os.environ.get("EC2_SPOT_MAX_PRICE", "0.50")  # Max $/hr for spot

# SSH Configuration - use same key as deploy-ec2.sh
SSH_KEY_PATH = os.environ.get("SSH_KEY_PATH", str(PROJECT_ROOT / "credentials/yt-news-generator-key.pem"))
SSH_USER = "ubuntu"
SSH_TIMEOUT = 300  # seconds to wait for instance to be SSH-ready
SSH_RETRY_INTERVAL = 10  # seconds between SSH attempts

# Chatterbox Configuration
CHATTERBOX_SAMPLE_RATE = 24000

# Voice reference audio paths (optional - for voice cloning)
VOICE_REFS = {
    "neutral": None,  # Use default voice
    # Add custom voice references here:
    # "custom_voice": "/path/to/reference.wav"
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
# EC2 MANAGEMENT
# ==========================

class EC2ChatterboxInstance:
    """Manages an EC2 instance running Chatterbox TTS."""

    def __init__(self, region: str = EC2_REGION):
        self.region = region
        self.ec2 = boto3.client("ec2", region_name=region)
        self.instance_id: Optional[str] = None
        self.public_ip: Optional[str] = None
        self._setup_complete = False

    def launch(self, use_spot: bool = EC2_USE_SPOT) -> str:
        """Launch a new EC2 instance for TTS generation.

        Args:
            use_spot: If True, use spot instances (cheaper, different quota).
                      If False, use on-demand instances.
        """
        instance_type_str = "spot" if use_spot else "on-demand"
        logger.info("Launching EC2 %s instance (type: %s, region: %s)",
                    instance_type_str, EC2_INSTANCE_TYPE, self.region)

        # Get AMI for region
        ami_id = EC2_AMI_MAP.get(self.region)
        if not ami_id:
            raise ValueError(f"No AMI configured for region {self.region}. Supported: {list(EC2_AMI_MAP.keys())}")

        # User data script to install CUDA and dependencies
        user_data = self._get_user_data_script()

        launch_params = {
            "ImageId": ami_id,
            "InstanceType": EC2_INSTANCE_TYPE,
            "KeyName": EC2_KEY_NAME,
            "MinCount": 1,
            "MaxCount": 1,
            "UserData": user_data,
            "BlockDeviceMappings": [
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {
                        "VolumeSize": 100,
                        "VolumeType": "gp3",
                        "DeleteOnTermination": True
                    }
                }
            ],
            "TagSpecifications": [
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": "chatterbox-tts-worker"},
                        {"Key": "Purpose", "Value": "tts-generation"},
                        {"Key": "AutoTerminate", "Value": "true"},
                        {"Key": "InstanceType", "Value": instance_type_str}
                    ]
                }
            ]
        }

        # Add spot instance configuration
        if use_spot:
            launch_params["InstanceMarketOptions"] = {
                "MarketType": "spot",
                "SpotOptions": {
                    "MaxPrice": EC2_SPOT_MAX_PRICE,
                    "SpotInstanceType": "one-time",
                    "InstanceInterruptionBehavior": "terminate"
                }
            }

        # Add security group
        if EC2_SECURITY_GROUP:
            launch_params["SecurityGroups"] = [EC2_SECURITY_GROUP]

        # Add subnet if specified
        if EC2_SUBNET_ID:
            launch_params["SubnetId"] = EC2_SUBNET_ID
            # When using subnet, use SecurityGroupIds instead
            if EC2_SECURITY_GROUP:
                del launch_params["SecurityGroups"]
                # Get security group ID from name
                sg_response = self.ec2.describe_security_groups(
                    Filters=[{"Name": "group-name", "Values": [EC2_SECURITY_GROUP]}]
                )
                if sg_response["SecurityGroups"]:
                    launch_params["SecurityGroupIds"] = [sg_response["SecurityGroups"][0]["GroupId"]]

        response = self.ec2.run_instances(**launch_params)
        self.instance_id = response["Instances"][0]["InstanceId"]
        logger.info("Instance launched: %s (%s)", self.instance_id, instance_type_str)

        return self.instance_id

    def _get_user_data_script(self) -> str:
        """Return the user data script for instance initialization."""
        return """#!/bin/bash
set -e

# Log output
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "Starting instance setup..."

# Update system
apt-get update
apt-get install -y python3-pip python3-venv ffmpeg git

# Install NVIDIA drivers and CUDA (for g4dn instances)
apt-get install -y nvidia-driver-535 nvidia-cuda-toolkit

# Create working directory
mkdir -p /opt/chatterbox
cd /opt/chatterbox

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install PyTorch with CUDA support
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

# Install Chatterbox TTS
pip install chatterbox-tts

# Create ready marker
touch /opt/chatterbox/.setup_complete

echo "Setup complete!"
"""

    def wait_for_running(self, timeout: int = 300):
        """Wait for the instance to be in running state."""
        logger.info("Waiting for instance to be running...")
        waiter = self.ec2.get_waiter("instance_running")
        waiter.wait(
            InstanceIds=[self.instance_id],
            WaiterConfig={"Delay": 5, "MaxAttempts": timeout // 5}
        )

        # Get public IP
        response = self.ec2.describe_instances(InstanceIds=[self.instance_id])
        self.public_ip = response["Reservations"][0]["Instances"][0].get("PublicIpAddress")
        logger.info("Instance running with IP: %s", self.public_ip)

    def wait_for_ssh(self, timeout: int = SSH_TIMEOUT):
        """Wait for SSH to become available."""
        logger.info("Waiting for SSH to be available...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self._check_ssh():
                logger.info("SSH is available")
                return
            time.sleep(SSH_RETRY_INTERVAL)

        raise TimeoutError(f"SSH not available after {timeout} seconds")

    def _check_ssh(self) -> bool:
        """Check if SSH is available."""
        try:
            result = subprocess.run(
                [
                    "ssh", "-o", "StrictHostKeyChecking=no",
                    "-o", "ConnectTimeout=5",
                    "-o", "BatchMode=yes",
                    "-i", SSH_KEY_PATH,
                    f"{SSH_USER}@{self.public_ip}",
                    "echo 'SSH OK'"
                ],
                capture_output=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False

    def wait_for_setup(self, timeout: int = 600):
        """Wait for Chatterbox setup to complete."""
        logger.info("Waiting for Chatterbox setup to complete...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            result = self._ssh_exec("test -f /opt/chatterbox/.setup_complete && echo 'ready'")
            if "ready" in result:
                logger.info("Chatterbox setup complete")
                self._setup_complete = True
                return
            logger.debug("Setup not complete yet, waiting...")
            time.sleep(30)

        raise TimeoutError(f"Chatterbox setup not complete after {timeout} seconds")

    def _ssh_exec(self, command: str, timeout: int = 300) -> str:
        """Execute a command on the remote instance via SSH."""
        result = subprocess.run(
            [
                "ssh", "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                "-i", SSH_KEY_PATH,
                f"{SSH_USER}@{self.public_ip}",
                command
            ],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode != 0:
            logger.error("SSH command failed: %s", result.stderr)
        return result.stdout + result.stderr

    def _scp_upload(self, local_path: Path, remote_path: str):
        """Upload a file to the instance."""
        subprocess.run(
            [
                "scp", "-o", "StrictHostKeyChecking=no",
                "-i", SSH_KEY_PATH,
                str(local_path),
                f"{SSH_USER}@{self.public_ip}:{remote_path}"
            ],
            check=True,
            capture_output=True
        )

    def _scp_download(self, remote_path: str, local_path: Path):
        """Download a file from the instance."""
        subprocess.run(
            [
                "scp", "-o", "StrictHostKeyChecking=no",
                "-i", SSH_KEY_PATH,
                f"{SSH_USER}@{self.public_ip}:{remote_path}",
                str(local_path)
            ],
            check=True,
            capture_output=True
        )

    def generate_audio_segment(self, text: str, output_path: Path, voice_ref: Optional[str] = None) -> int:
        """Generate audio for a text segment using Chatterbox TTS."""
        # Create remote script for generation
        script = f'''
import torch
import torchaudio
from chatterbox.tts import ChatterboxTTS

model = ChatterboxTTS.from_pretrained(device="cuda")

text = """{text.replace('"', '\\"')}"""
'''

        if voice_ref:
            script += f'''
# Use voice reference for cloning
wav = model.generate(text, audio_prompt_path="{voice_ref}")
'''
        else:
            script += '''
# Use default voice
wav = model.generate(text)
'''

        script += f'''
torchaudio.save("/tmp/output.wav", wav, {CHATTERBOX_SAMPLE_RATE})
print("GENERATION_COMPLETE")
'''

        # Write script to temp file and upload
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            script_path = Path(f.name)

        try:
            self._scp_upload(script_path, "/tmp/generate.py")

            # Execute generation
            result = self._ssh_exec(
                "cd /opt/chatterbox && source venv/bin/activate && python /tmp/generate.py",
                timeout=120
            )

            if "GENERATION_COMPLETE" not in result:
                raise RuntimeError(f"Audio generation failed: {result}")

            # Download the generated audio
            self._scp_download("/tmp/output.wav", output_path)

            return get_audio_duration_ms(output_path)

        finally:
            script_path.unlink(missing_ok=True)

    def terminate(self):
        """Terminate the EC2 instance."""
        if self.instance_id:
            logger.info("Terminating instance: %s", self.instance_id)
            self.ec2.terminate_instances(InstanceIds=[self.instance_id])
            self.instance_id = None
            self.public_ip = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.terminate()


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
    """Generate audio from dialogue using Chatterbox TTS on EC2.

    Args:
        dialogue_path: Path to dialogue JSON file
        output: Path to output audio file
        timeline: Path to output timeline file
        voice_a: Voice name for speaker A
        voice_b: Voice name for speaker B
        storage: Optional storage backend. If None, uses local filesystem.
    """
    logger.info("Generating audio from dialogue: %s", dialogue_path)

    data = load_dialogue(dialogue_path, storage)
    segments, speakers = extract_segments(data)
    logger.info("Found %d segments with speakers: %s", len(segments), speakers)

    voices = [voice_ref(voice_a), voice_ref(voice_b)]
    voice_map = {s: voices[i % 2] for i, s in enumerate(speakers)}
    logger.debug("Voice mapping: %s", voice_map)

    with EC2ChatterboxInstance() as ec2_instance:
        # Launch and wait for instance
        ec2_instance.launch()
        ec2_instance.wait_for_running()
        ec2_instance.wait_for_ssh()
        ec2_instance.wait_for_setup()

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audio_files = []
            durations = []

            for i, (speaker, text, _emphasis, _source) in enumerate(segments):
                out = tmp / f"seg_{i:03}.wav"
                logger.debug("Generating segment %d/%d: %s...", i + 1, len(segments), text[:50])
                dur = ec2_instance.generate_audio_segment(text, out, voice_map[speaker])
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

    # Instance is terminated automatically via context manager

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
