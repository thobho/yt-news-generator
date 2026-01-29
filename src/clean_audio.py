#!/usr/bin/env python3
"""
Clean audio file by removing background noise while preserving voice quality.

Uses advanced techniques:
1. Spectral gating - removes noise based on frequency analysis
2. Noise gate - silences quiet portions between speech
3. High-pass filter - removes low-frequency rumble

Usage:
    python clean_audio.py input.mp3 -o output.mp3
    python clean_audio.py input.mp3  # outputs to input_cleaned.mp3
"""

import argparse
import subprocess
import tempfile
from pathlib import Path

try:
    import noisereduce as nr
    import numpy as np
    import soundfile as sf
    NOISEREDUCE_AVAILABLE = True
except ImportError:
    NOISEREDUCE_AVAILABLE = False


def clean_with_noisereduce(input_path: Path, output_path: Path,
                           prop_decrease: float = 0.8,
                           stationary: bool = True):
    """
    Clean audio using noisereduce library (spectral gating).

    This is the most advanced method - analyzes the noise profile
    and removes it while preserving voice characteristics.

    Args:
        input_path: Input audio file
        output_path: Output audio file
        prop_decrease: How much to reduce noise (0.0-1.0). Higher = more reduction.
        stationary: If True, assumes noise is constant (better for background hum/hiss)
    """
    print(f"Loading audio: {input_path}")
    audio, sample_rate = sf.read(input_path)

    # Convert to mono if stereo for processing
    if len(audio.shape) > 1:
        audio_mono = np.mean(audio, axis=1)
    else:
        audio_mono = audio

    print(f"Applying spectral noise reduction (prop_decrease={prop_decrease})...")

    # Apply noise reduction
    # stationary=True works well for constant background noise
    # stationary=False works better for varying noise but can affect voice
    cleaned = nr.reduce_noise(
        y=audio_mono,
        sr=sample_rate,
        prop_decrease=prop_decrease,
        stationary=stationary,
        n_fft=2048,
        hop_length=512,
    )

    # Normalize to prevent clipping
    max_val = np.max(np.abs(cleaned))
    if max_val > 0:
        cleaned = cleaned / max_val * 0.95

    print(f"Saving cleaned audio: {output_path}")
    sf.write(output_path, cleaned, sample_rate)


def clean_with_ffmpeg(input_path: Path, output_path: Path,
                      gate_threshold: float = 0.015,
                      highpass_freq: int = 80):
    """
    Clean audio using FFmpeg filters.

    Simpler but effective approach using:
    - High-pass filter to remove rumble
    - Noise gate to silence quiet portions

    Args:
        input_path: Input audio file
        output_path: Output audio file
        gate_threshold: Amplitude threshold for noise gate (0.0-1.0)
        highpass_freq: Frequency cutoff for high-pass filter (Hz)
    """
    print(f"Applying FFmpeg noise gate and filters...")

    # Build filter chain:
    # 1. highpass - remove low frequency rumble/hum
    # 2. agate - silence portions below threshold (the gaps between speech)
    # 3. dynaudnorm - gentle normalization for consistent volume
    filters = [
        f"highpass=f={highpass_freq}",
        f"agate=threshold={gate_threshold}:range=0:attack=5:release=50",
        "dynaudnorm=f=500:p=0.95:m=3",
    ]

    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-af", ",".join(filters),
        "-c:a", "libmp3lame", "-q:a", "2",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")

    print(f"Saved: {output_path}")


def add_ambient_noise(input_path: Path, output_path: Path,
                      noise_type: str = "pink",
                      volume: float = 0.03,
                      ambient_file: Path = None):
    """
    Add subtle ambient noise to mask imperfections.

    Args:
        input_path: Input audio file
        output_path: Output audio file
        noise_type: Type of generated noise ("pink", "brown", "white")
        volume: Volume of ambient noise (0.0-1.0), default 0.03 (very subtle)
        ambient_file: Optional custom ambient audio file to use instead of generated noise
    """
    print(f"Adding ambient background ({noise_type} noise at {volume*100:.1f}% volume)...")

    # Get input duration
    probe_cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_path)
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    duration = float(result.stdout.strip())

    if ambient_file and Path(ambient_file).exists():
        # Use custom ambient file, loop it to match duration
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-stream_loop", "-1", "-i", str(ambient_file),
            "-filter_complex",
            f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{duration},volume={volume}[ambient];"
            f"[0:a][ambient]amix=inputs=2:duration=first:weights=1 {volume}[out]",
            "-map", "[out]",
            "-c:a", "libmp3lame", "-q:a", "2",
            str(output_path)
        ]
    else:
        # Generate noise using FFmpeg
        # Pink noise: natural sounding, less harsh than white noise
        # Brown noise: even deeper, very subtle rumble
        noise_expr = {
            "pink": "random(0)*2-1",  # Approximation, true pink needs filtering
            "brown": "random(0)*2-1",
            "white": "random(0)*2-1",
        }.get(noise_type, "random(0)*2-1")

        # Pink/brown noise filter
        noise_filter = {
            "pink": "aformat=sample_fmts=fltp,lowpass=f=8000,highpass=f=50",
            "brown": "aformat=sample_fmts=fltp,lowpass=f=500,highpass=f=20",
            "white": "aformat=sample_fmts=fltp,highpass=f=100",
        }.get(noise_type, "aformat=sample_fmts=fltp,lowpass=f=8000")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-f", "lavfi", "-i", f"anoisesrc=d={duration}:c=pink:a={volume}",
            "-filter_complex",
            f"[1:a]{noise_filter},volume={volume}[noise];"
            f"[0:a][noise]amix=inputs=2:duration=first[out]",
            "-map", "[out]",
            "-c:a", "libmp3lame", "-q:a", "2",
            str(output_path)
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")

    print(f"Saved: {output_path}")


def clean_audio(input_path: Path, output_path: Path,
                method: str = "auto",
                noise_reduction: float = 0.8,
                gate_threshold: float = 0.015,
                add_ambient: bool = False,
                ambient_volume: float = 0.03,
                ambient_type: str = "pink",
                ambient_file: Path = None):
    """
    Clean audio file using the best available method.

    Args:
        input_path: Input audio file
        output_path: Output audio file
        method: "noisereduce", "ffmpeg", or "auto" (uses noisereduce if available)
        noise_reduction: Strength of noise reduction (0.0-1.0)
        gate_threshold: Threshold for noise gate
        add_ambient: If True, add subtle ambient noise to mask imperfections
        ambient_volume: Volume of ambient noise (0.0-1.0)
        ambient_type: Type of noise ("pink", "brown", "white")
        ambient_file: Optional custom ambient audio file
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Determine method
    if method == "auto":
        method = "noisereduce" if NOISEREDUCE_AVAILABLE else "ffmpeg"

    if method == "noisereduce":
        if not NOISEREDUCE_AVAILABLE:
            print("noisereduce not available, falling back to ffmpeg")
            method = "ffmpeg"

    if method == "noisereduce":
        # noisereduce works best with WAV, so convert if needed
        if input_path.suffix.lower() != ".wav":
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_wav = Path(tmp.name)

            # Convert to WAV
            subprocess.run([
                "ffmpeg", "-y", "-i", str(input_path),
                "-ar", "44100", "-ac", "1",
                str(tmp_wav)
            ], capture_output=True, check=True)

            # Process
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp2:
                tmp_cleaned = Path(tmp2.name)

            clean_with_noisereduce(tmp_wav, tmp_cleaned, prop_decrease=noise_reduction)

            # Convert back to original format
            subprocess.run([
                "ffmpeg", "-y", "-i", str(tmp_cleaned),
                "-c:a", "libmp3lame", "-q:a", "2",
                str(output_path)
            ], capture_output=True, check=True)

            # Cleanup
            tmp_wav.unlink()
            tmp_cleaned.unlink()
        else:
            clean_with_noisereduce(input_path, output_path, prop_decrease=noise_reduction)

    elif method == "ffmpeg":
        clean_with_ffmpeg(input_path, output_path, gate_threshold=gate_threshold)

    else:
        raise ValueError(f"Unknown method: {method}")

    # Add ambient noise if requested
    if add_ambient:
        # Apply to the cleaned output
        with tempfile.NamedTemporaryFile(suffix=output_path.suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)

        # Move cleaned to temp, add ambient to final output
        import shutil
        shutil.move(output_path, tmp_path)
        add_ambient_noise(tmp_path, output_path,
                          noise_type=ambient_type,
                          volume=ambient_volume,
                          ambient_file=ambient_file)
        tmp_path.unlink()

    print("Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Clean audio by removing background noise while preserving voice"
    )
    parser.add_argument("input", type=Path, help="Input audio file")
    parser.add_argument("-o", "--output", type=Path, help="Output audio file")
    parser.add_argument(
        "--method",
        choices=["auto", "noisereduce", "ffmpeg"],
        default="auto",
        help="Cleaning method (default: auto)"
    )
    parser.add_argument(
        "--noise-reduction",
        type=float,
        default=0.8,
        help="Noise reduction strength 0.0-1.0 (default: 0.8)"
    )
    parser.add_argument(
        "--gate-threshold",
        type=float,
        default=0.015,
        help="Noise gate threshold 0.0-1.0 (default: 0.015)"
    )
    parser.add_argument(
        "--add-ambient",
        action="store_true",
        help="Add subtle ambient noise to mask imperfections"
    )
    parser.add_argument(
        "--ambient-volume",
        type=float,
        default=0.03,
        help="Ambient noise volume 0.0-1.0 (default: 0.03 = 3%%)"
    )
    parser.add_argument(
        "--ambient-type",
        choices=["pink", "brown", "white"],
        default="pink",
        help="Type of ambient noise (default: pink)"
    )
    parser.add_argument(
        "--ambient-file",
        type=Path,
        help="Custom ambient audio file (loops to match duration)"
    )

    args = parser.parse_args()

    # Default output path
    if args.output is None:
        args.output = args.input.with_stem(args.input.stem + "_cleaned")

    clean_audio(
        args.input,
        args.output,
        method=args.method,
        noise_reduction=args.noise_reduction,
        gate_threshold=args.gate_threshold,
        add_ambient=args.add_ambient,
        ambient_volume=args.ambient_volume,
        ambient_type=args.ambient_type,
        ambient_file=args.ambient_file,
    )


if __name__ == "__main__":
    main()
