"""
Reusable client for Chatterbox TTS on RunPod Serverless.

Provides a simple interface to generate speech from text using
a RunPod Serverless endpoint running the Chatterbox TTS handler.

Environment variables:
    RUNPOD_API_KEY: Your RunPod API key (required)
    RUNPOD_ENDPOINT_ID: Your RunPod serverless endpoint ID (required)

Usage:
    from tts_client import TTSClient

    client = TTSClient()
    wav_bytes = client.generate("Cześć, jak się masz?")

    # With voice cloning and custom parameters
    wav_bytes = client.generate(
        "Cześć!",
        voice_ref_path="data/voices/polish_native_cleaned.wav",
        cfg_weight=0.4,
        exaggeration=1.3,
        language_id="pl",
    )
"""

import base64
import os
from pathlib import Path
from typing import Optional

import runpod

from ..core.logging_config import get_logger
from ..core.storage import StorageBackend

logger = get_logger(__name__)

# Defaults
DEFAULT_LANGUAGE_ID = "pl"
DEFAULT_CFG_WEIGHT = float(os.environ.get("CHATTERBOX_CFG_WEIGHT", "0.4"))
DEFAULT_EXAGGERATION = float(os.environ.get("CHATTERBOX_EXAGGERATION", "0.7"))
DEFAULT_TIMEOUT = int(os.environ.get("RUNPOD_REQUEST_TIMEOUT", "300"))


class TTSClient:
    """Client for Chatterbox TTS on RunPod Serverless."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key or os.environ.get("RUNPOD_API_KEY")
        if not self.api_key:
            raise RuntimeError("RUNPOD_API_KEY environment variable not set")

        self.endpoint_id = endpoint_id or os.environ.get("RUNPOD_ENDPOINT_ID")
        if not self.endpoint_id:
            raise RuntimeError(
                "RUNPOD_ENDPOINT_ID environment variable not set.\n"
                "Create a serverless endpoint at https://www.runpod.io/console/serverless"
            )

        self.timeout = timeout
        runpod.api_key = self.api_key
        self._endpoint = runpod.Endpoint(self.endpoint_id)
        self._voice_cache: dict[str, str] = {}

    def _encode_voice_ref(self, path: str, storage: Optional[StorageBackend] = None) -> Optional[str]:
        """Base64-encode a voice reference WAV file (cached).

        Args:
            path: Path to voice reference WAV file (local or storage key)
            storage: Optional storage backend for loading from S3/remote
        """
        if path in self._voice_cache:
            return self._voice_cache[path]

        if storage is not None:
            try:
                wav_bytes = storage.read_bytes(path)
            except Exception:
                logger.warning("Voice reference not found in storage: %s", path)
                return None
        else:
            p = Path(path)
            if not p.exists():
                logger.warning("Voice reference not found: %s", path)
                return None
            wav_bytes = p.read_bytes()

        b64 = base64.b64encode(wav_bytes).decode("utf-8")
        self._voice_cache[path] = b64
        logger.info("Encoded voice reference: %s (%d bytes)", path, len(wav_bytes))
        return b64

    def _run_tts(
        self,
        text: str,
        voice_ref_path: Optional[str] = None,
        language_id: str = DEFAULT_LANGUAGE_ID,
        cfg_weight: float = DEFAULT_CFG_WEIGHT,
        exaggeration: float = DEFAULT_EXAGGERATION,
        storage: Optional[StorageBackend] = None,
    ) -> tuple[bytes, int]:
        """Run TTS and return (wav_bytes, duration_ms)."""
        payload = {
            "text": text,
            "language_id": language_id,
            "cfg_weight": cfg_weight,
            "exaggeration": exaggeration,
        }

        if voice_ref_path:
            voice_b64 = self._encode_voice_ref(voice_ref_path, storage=storage)
            if voice_b64:
                payload["voice_ref_base64"] = voice_b64

        job = self._endpoint.run({"input": payload})
        logger.debug("Submitted job %s for text: %s...", job.job_id, text[:50])

        try:
            output = job.output(timeout=self.timeout)
        except TimeoutError:
            logger.error("Job timed out after %ds for: %s...", self.timeout, text[:50])
            try:
                job.cancel()
            except Exception:
                pass
            raise RuntimeError(f"TTS generation timed out for: {text[:50]}...")

        if output is None:
            status = job.status()
            raise RuntimeError(f"TTS job failed with status: {status}")

        wav_bytes = base64.b64decode(output["audio_base64"])
        duration_ms = output["duration_ms"]
        logger.info("Generated %.1fs of audio for: %s...", duration_ms / 1000, text[:50])

        return wav_bytes, duration_ms

    def generate(
        self,
        text: str,
        voice_ref_path: Optional[str] = None,
        language_id: str = DEFAULT_LANGUAGE_ID,
        cfg_weight: float = DEFAULT_CFG_WEIGHT,
        exaggeration: float = DEFAULT_EXAGGERATION,
        storage: Optional[StorageBackend] = None,
    ) -> bytes:
        """Generate speech audio from text.

        Args:
            text: Text to synthesize
            voice_ref_path: Optional path to voice reference WAV for cloning
            language_id: Language code (default "pl")
            cfg_weight: Speed control 0.2-1.0 (lower = slower)
            exaggeration: Expressiveness 0.25-2.0 (higher = more dramatic)
            storage: Optional storage backend for loading voice refs from S3

        Returns:
            Raw WAV bytes
        """
        wav_bytes, _ = self._run_tts(
            text, voice_ref_path, language_id, cfg_weight, exaggeration, storage
        )
        return wav_bytes

    def generate_with_metadata(
        self,
        text: str,
        voice_ref_path: Optional[str] = None,
        language_id: str = DEFAULT_LANGUAGE_ID,
        cfg_weight: float = DEFAULT_CFG_WEIGHT,
        exaggeration: float = DEFAULT_EXAGGERATION,
        storage: Optional[StorageBackend] = None,
    ) -> dict:
        """Generate speech audio and return audio bytes with duration.

        Args:
            text: Text to synthesize
            voice_ref_path: Optional path to voice reference WAV for cloning
            language_id: Language code (default "pl")
            cfg_weight: Speed control 0.2-1.0 (lower = slower)
            exaggeration: Expressiveness 0.25-2.0 (higher = more dramatic)
            storage: Optional storage backend for loading voice refs from S3

        Returns:
            Dict with "audio" (bytes) and "duration_ms" (int)
        """
        wav_bytes, duration_ms = self._run_tts(
            text, voice_ref_path, language_id, cfg_weight, exaggeration, storage
        )
        return {"audio": wav_bytes, "duration_ms": duration_ms}
