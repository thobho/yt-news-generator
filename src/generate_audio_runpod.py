#!/usr/bin/env python3
"""
Generate audio from dialogue JSON using Chatterbox TTS on RunPod.

This module creates a RunPod GPU pod, installs Chatterbox TTS,
generates audio, downloads the result, and terminates the pod.

No quota approval needed - just sign up at runpod.io and add credits.

Usage:
    python generate_audio_runpod.py dialogue.json -o final_audio.mp3 -t timeline.json

Environment variables:
    RUNPOD_API_KEY: Your RunPod API key (required)

The interface is identical to generate_audio.py for easy swapping.
"""

import argparse
import json
import os
import subprocess
import time
import re
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

# RunPod Configuration
# GPU types to try in order of preference (16GB+ VRAM for Chatterbox)
RUNPOD_GPU_TYPES = [
    "NVIDIA GeForce RTX 4090",      # 24GB, fastest
    "NVIDIA RTX A5000",             # 24GB
    "NVIDIA GeForce RTX 3090",      # 24GB
    "NVIDIA RTX A4000",             # 16GB
    "NVIDIA GeForce RTX 4080",      # 16GB
]
RUNPOD_GPU_TYPE = os.environ.get("RUNPOD_GPU_TYPE")  # Override if set

# Docker image - use custom image with Chatterbox pre-installed for faster startup
# Set RUNPOD_IMAGE env var to your Docker Hub image (e.g., "yourusername/chatterbox-tts:latest")
RUNPOD_IMAGE = os.environ.get("RUNPOD_IMAGE", "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04")
RUNPOD_DISK_SIZE = 50  # GB
RUNPOD_VOLUME_SIZE = 0  # GB (no persistent volume needed)

# SSH key for RunPod access
def get_ssh_public_key() -> str:
    """Get the user's SSH public key."""
    for key_file in ["~/.ssh/id_ed25519.pub", "~/.ssh/id_rsa.pub"]:
        path = Path(key_file).expanduser()
        if path.exists():
            return path.read_text().strip()
    return ""

RUNPOD_SSH_PUBLIC_KEY = os.environ.get("RUNPOD_PUBLIC_KEY", get_ssh_public_key())

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
# RUNPOD MANAGEMENT
# ==========================

class RunPodChatterboxInstance:
    """Manages a RunPod pod running Chatterbox TTS."""

    def __init__(self):
        api_key = os.environ.get("RUNPOD_API_KEY")
        if not api_key:
            raise RuntimeError("RUNPOD_API_KEY environment variable not set")
        runpod.api_key = api_key
        self.pod_id: Optional[str] = None
        self.ssh_host: Optional[str] = None
        self.ssh_port: Optional[int] = None
        self._setup_complete = False

    def launch(self) -> str:
        """Launch a new RunPod pod for TTS generation."""
        if not RUNPOD_SSH_PUBLIC_KEY:
            raise RuntimeError(
                "No SSH public key found. Either:\n"
                "  1. Generate one: ssh-keygen -t ed25519\n"
                "  2. Set RUNPOD_PUBLIC_KEY environment variable"
            )

        # Try each GPU type until one works
        gpu_types = [RUNPOD_GPU_TYPE] if RUNPOD_GPU_TYPE else RUNPOD_GPU_TYPES
        last_error = None

        for gpu_type in gpu_types:
            logger.info("Trying to launch RunPod pod (GPU: %s)", gpu_type)
            try:
                pod = runpod.create_pod(
                    name="chatterbox-tts-worker",
                    image_name=RUNPOD_IMAGE,
                    gpu_type_id=gpu_type,
                    cloud_type="COMMUNITY",  # Cheaper than SECURE
                    container_disk_in_gb=RUNPOD_DISK_SIZE,
                    volume_in_gb=RUNPOD_VOLUME_SIZE,
                    ports="22/tcp",  # Enable SSH
                    docker_args="",
                    env={
                        "PUBLIC_KEY": RUNPOD_SSH_PUBLIC_KEY,
                    }
                )
                logger.info("Successfully created pod with GPU: %s", gpu_type)
                break
            except Exception as e:
                logger.warning("Failed to create pod with %s: %s", gpu_type, e)
                last_error = e
                continue
        else:
            raise RuntimeError(f"Could not create pod with any GPU type. Last error: {last_error}")

        self.pod_id = pod["id"]
        logger.info("Pod created: %s", self.pod_id)

        return self.pod_id

    def wait_for_running(self, timeout: int = 300):
        """Wait for the pod to be in running state."""
        logger.info("Waiting for pod to be running...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            pod = runpod.get_pod(self.pod_id)
            status = pod.get("desiredStatus")
            runtime = pod.get("runtime")

            if status == "RUNNING" and runtime:
                # Extract SSH connection info
                ports = runtime.get("ports", [])
                for port in ports:
                    if port.get("privatePort") == 22:
                        self.ssh_host = port.get("ip")
                        self.ssh_port = port.get("publicPort")
                        break

                if self.ssh_host and self.ssh_port:
                    logger.info("Pod running - SSH: %s:%s", self.ssh_host, self.ssh_port)
                    return

            logger.debug("Pod status: %s, waiting...", status)
            time.sleep(5)

        raise TimeoutError(f"Pod not running after {timeout} seconds")

    def wait_for_ssh(self, timeout: int = 120):
        """Wait for SSH to become available."""
        logger.info("Waiting for SSH to be available...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self._check_ssh():
                logger.info("SSH is available")
                return
            time.sleep(5)

        raise TimeoutError(f"SSH not available after {timeout} seconds")

    def _get_ssh_key_path(self) -> str:
        """Get the path to the SSH private key."""
        for key_file in ["~/.ssh/id_ed25519", "~/.ssh/id_rsa"]:
            path = Path(key_file).expanduser()
            if path.exists():
                return str(path)
        return ""

    def _check_ssh(self) -> bool:
        """Check if SSH is available."""
        try:
            ssh_cmd = [
                "ssh", "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=5",
                "-o", "BatchMode=yes",
                "-o", "UserKnownHostsFile=/dev/null",
                "-p", str(self.ssh_port),
            ]
            key_path = self._get_ssh_key_path()
            if key_path:
                ssh_cmd.extend(["-i", key_path])
            ssh_cmd.extend([f"root@{self.ssh_host}", "echo 'SSH OK'"])

            result = subprocess.run(ssh_cmd, capture_output=True, timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False

    def setup_chatterbox(self):
        """Install Chatterbox TTS on the pod (skipped if using pre-built image)."""
        # Check if chatterbox is already installed (custom image)
        check_result = self._ssh_exec("python3 -c 'import chatterbox' 2>/dev/null && echo 'INSTALLED'", timeout=30)

        if "INSTALLED" in check_result:
            logger.info("Chatterbox TTS already installed (using pre-built image)")
            self._setup_complete = True
            return

        logger.info("Installing Chatterbox TTS...")

        setup_script = """
set -e
pip install --quiet chatterbox-tts
pip install --quiet soundfile
echo 'SETUP_COMPLETE'
"""
        result = self._ssh_exec(setup_script, timeout=300)

        if "SETUP_COMPLETE" not in result:
            raise RuntimeError(f"Chatterbox setup failed: {result}")

        logger.info("Chatterbox TTS installed successfully")
        self._setup_complete = True

    def _ssh_exec(self, command: str, timeout: int = 300) -> str:
        """Execute a command on the pod via SSH."""
        ssh_cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-o", "UserKnownHostsFile=/dev/null",
            "-p", str(self.ssh_port),
        ]
        key_path = self._get_ssh_key_path()
        if key_path:
            ssh_cmd.extend(["-i", key_path])
        ssh_cmd.extend([f"root@{self.ssh_host}", command])

        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            logger.error("SSH command failed: %s", result.stderr)
        return result.stdout + result.stderr

    def _scp_upload(self, local_path: Path, remote_path: str):
        """Upload a file to the pod."""
        scp_cmd = [
            "scp", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-P", str(self.ssh_port),
        ]
        key_path = self._get_ssh_key_path()
        if key_path:
            scp_cmd.extend(["-i", key_path])
        scp_cmd.extend([str(local_path), f"root@{self.ssh_host}:{remote_path}"])

        subprocess.run(scp_cmd, check=True, capture_output=True)

    def _scp_download(self, remote_path: str, local_path: Path):
        """Download a file from the pod."""
        scp_cmd = [
            "scp", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-P", str(self.ssh_port),
        ]
        key_path = self._get_ssh_key_path()
        if key_path:
            scp_cmd.extend(["-i", key_path])
        scp_cmd.extend([f"root@{self.ssh_host}:{remote_path}", str(local_path)])

        subprocess.run(scp_cmd, check=True, capture_output=True)

    def generate_audio_segment(self, text: str, output_path: Path, voice_ref: Optional[str] = None):
        """Generate audio for a text segment using Chatterbox TTS.

        Args:
            text: Text to synthesize
            output_path: Local path to save the audio
            voice_ref: Optional path to voice reference WAV for cloning (on remote pod)
        """
        # Escape text for Python string
        escaped_text = text.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")

        # Build generate() call with parameters
        generate_params = [
            'text',
            'language_id="pl"',
            f'cfg_weight={CHATTERBOX_CFG_WEIGHT}',
            f'exaggeration={CHATTERBOX_EXAGGERATION}',
        ]

        # Add voice reference for cloning if provided
        if voice_ref:
            generate_params.append(f'audio_prompt_path="{voice_ref}"')

        generate_call = f"model.generate({', '.join(generate_params)})"

        script = f'''
import torch
import torchaudio
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

device = "cuda" if torch.cuda.is_available() else "cpu"
model = ChatterboxMultilingualTTS.from_pretrained(device=device)

text = """{escaped_text}"""
wav = {generate_call}
torchaudio.save("/tmp/output.wav", wav, model.sr)
print("GENERATION_COMPLETE")
'''

        # Execute generation (first run downloads model, so needs longer timeout)
        result = self._ssh_exec(f"python3 -c '{script}'", timeout=300)

        if "GENERATION_COMPLETE" not in result:
            raise RuntimeError(f"Audio generation failed: {result}")

        # Download the generated audio
        self._scp_download("/tmp/output.wav", output_path)

    def terminate(self):
        """Terminate the RunPod pod."""
        if self.pod_id:
            logger.info("Terminating pod: %s", self.pod_id)
            try:
                runpod.terminate_pod(self.pod_id)
            except Exception as e:
                logger.warning("Failed to terminate pod: %s", e)
            self.pod_id = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.terminate()


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
    """Generate audio from dialogue using Chatterbox TTS on RunPod.

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

    with RunPodChatterboxInstance() as pod:
        # Launch and wait for pod
        pod.launch()
        pod.wait_for_running()
        pod.wait_for_ssh()
        pod.setup_chatterbox()

        # Upload voice reference files to the pod
        remote_voice_map = {}
        for speaker, local_path in voice_map.items():
            if local_path and Path(local_path).exists():
                remote_path = f"/tmp/voice_{speaker}.wav"
                logger.info("Uploading voice reference for %s: %s", speaker, local_path)
                pod._scp_upload(Path(local_path), remote_path)
                remote_voice_map[speaker] = remote_path
            else:
                remote_voice_map[speaker] = None

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audio_files = []
            durations = []

            for i, (speaker, text, _emphasis, _source) in enumerate(segments):
                out = tmp / f"seg_{i:03}.wav"
                logger.info("Generating segment %d/%d: %s...", i + 1, len(segments), text[:50])
                pod.generate_audio_segment(text, out, remote_voice_map[speaker])
                dur = get_audio_duration_ms(out)
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

    # Pod is terminated automatically via context manager

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
