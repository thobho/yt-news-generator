"""
RunPod Serverless handler for Chatterbox Multilingual TTS.

The model is loaded once at module level and persists across requests
on the same worker (RunPod workers are long-lived containers).

Input schema:
    {
        "text": str,                    # Text to synthesize (required)
        "language_id": str,             # Language code, default "pl"
        "cfg_weight": float,            # Speed control (0.2-1.0), default 0.6
        "exaggeration": float,          # Expressiveness (0.25-2.0), default 0.9
        "voice_ref_base64": str | None  # Base64-encoded WAV for voice cloning
    }

Output schema:
    {
        "audio_base64": str,    # Base64-encoded WAV audio
        "sample_rate": int,     # Sample rate of output audio
        "duration_ms": int      # Duration in milliseconds
    }
"""

import base64
import io
import os
import tempfile

import torch
import torchaudio
import runpod

from chatterbox.mtl_tts import ChatterboxMultilingualTTS

# Load model once at startup (persists across requests on same worker)
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading ChatterboxMultilingualTTS on {device}...")
model = ChatterboxMultilingualTTS.from_pretrained(device=device)
print("Model loaded successfully!")


def handler(job):
    """Handle a single TTS generation request."""
    job_input = job["input"]

    text = job_input["text"]
    language_id = job_input.get("language_id", "pl")
    cfg_weight = float(job_input.get("cfg_weight", 0.6))
    exaggeration = float(job_input.get("exaggeration", 0.9))
    voice_ref_b64 = job_input.get("voice_ref_base64")

    audio_prompt_path = None
    tmp_voice_file = None

    if voice_ref_b64:
        voice_bytes = base64.b64decode(voice_ref_b64)
        tmp_voice_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_voice_file.write(voice_bytes)
        tmp_voice_file.close()
        audio_prompt_path = tmp_voice_file.name

    try:
        generate_kwargs = {
            "language_id": language_id,
            "cfg_weight": cfg_weight,
            "exaggeration": exaggeration,
        }
        if audio_prompt_path:
            generate_kwargs["audio_prompt_path"] = audio_prompt_path

        wav = model.generate(text, **generate_kwargs)

        buffer = io.BytesIO()
        torchaudio.save(buffer, wav, model.sr, format="wav")
        audio_bytes = buffer.getvalue()
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        num_samples = wav.shape[-1]
        duration_ms = int(num_samples / model.sr * 1000)

        return {
            "audio_base64": audio_b64,
            "sample_rate": model.sr,
            "duration_ms": duration_ms,
        }

    finally:
        if tmp_voice_file and os.path.exists(tmp_voice_file.name):
            os.unlink(tmp_voice_file.name)


runpod.serverless.start({"handler": handler})
