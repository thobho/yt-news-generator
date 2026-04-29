#!/usr/bin/env python3
"""
Audio-text alignment using Montreal Forced Aligner (MFA).

Given audio and known text, MFA produces word-level timestamps via forced
alignment — no transcription or fuzzy matching needed.

MFA runs as a CLI subprocess (same pattern as ffmpeg).  TextGrid output is
parsed with the ``praatio`` library.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from praatio import textgrid

from ..core.logging_config import get_logger

logger = get_logger(__name__)

# ── MFA binary resolution ────────────────────────────────────────────────────

_MFA_CMD: list[str] | None = None


def _resolve_mfa_cmd() -> list[str]:
    """Detect how to invoke MFA: bare ``mfa`` or ``conda run -n mfa mfa``."""
    global _MFA_CMD
    if _MFA_CMD is not None:
        return _MFA_CMD

    # 1. Try bare binary (e.g. installed globally or active conda env)
    if shutil.which("mfa"):
        _MFA_CMD = ["mfa"]
        return _MFA_CMD

    # 2. Try via conda in a dedicated "mfa" env
    conda = shutil.which("conda")
    if conda:
        try:
            subprocess.run(
                ["conda", "run", "-n", "mfa", "mfa", "version"],
                capture_output=True,
                check=True,
                timeout=30,
            )
            _MFA_CMD = ["conda", "run", "-n", "mfa", "mfa"]
            return _MFA_CMD
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pass

    _MFA_CMD = []  # empty = not available
    return _MFA_CMD


def is_aligner_available() -> bool:
    """Check if MFA binary is reachable."""
    return bool(_resolve_mfa_cmd())


# ── MFA model management ─────────────────────────────────────────────────────

_MODELS_CHECKED: set[str] = set()

# Map language codes to MFA model names
_LANGUAGE_MODELS: dict[str, tuple[str, str]] = {
    "pl": ("polish_mfa", "polish_mfa"),
    "en": ("english_mfa", "english_mfa"),
}


def _ensure_mfa_models(language: str) -> tuple[str, str]:
    """Download acoustic model + dictionary for *language* if not yet present.

    Returns (acoustic_model_name, dictionary_name).
    """
    acoustic, dictionary = _LANGUAGE_MODELS.get(language, (f"{language}_mfa", f"{language}_mfa"))

    if language in _MODELS_CHECKED:
        return acoustic, dictionary

    cmd = _resolve_mfa_cmd()
    if not cmd:
        raise RuntimeError("MFA binary not found")

    for model_type, model_name in [("acoustic", acoustic), ("dictionary", dictionary)]:
        try:
            subprocess.run(
                [*cmd, "model", "inspect", model_type, model_name],
                capture_output=True,
                check=True,
                timeout=30,
            )
        except subprocess.CalledProcessError:
            logger.info("Downloading MFA %s model: %s", model_type, model_name)
            subprocess.run(
                [*cmd, "model", "download", model_type, model_name],
                capture_output=True,
                check=True,
                timeout=300,
            )

    _MODELS_CHECKED.add(language)
    return acoustic, dictionary


# ── Post-processing ──────────────────────────────────────────────────────────

_STRIP_RE = re.compile(r"[^\w\u0080-\uFFFF]", re.UNICODE)


def _clean(word: str) -> str:
    """Lowercase and strip punctuation — mirrors MFA normalisation."""
    return _STRIP_RE.sub("", word).lower()


def _restore_original_text(
    mfa_words: list[dict], original_text: str
) -> list[dict]:
    """Replace MFA word labels with the original tokens (capitalisation + punctuation).

    Walks both sequences in order; skips unmatched original tokens so that
    OOV words or MFA-inserted entries keep their MFA form without breaking
    the mapping for subsequent words.
    """
    original_tokens = original_text.split()
    orig_idx = 0
    result = []

    for w in mfa_words:
        mfa_clean = _clean(w["word"])
        matched = False
        for j in range(orig_idx, len(original_tokens)):
            if _clean(original_tokens[j]) == mfa_clean:
                result.append({
                    "word": original_tokens[j],
                    "start_ms": w["start_ms"],
                    "end_ms": w["end_ms"],
                })
                orig_idx = j + 1
                matched = True
                break
        if not matched:
            result.append(w)

    return result


# ── Forced alignment ────────────────────────────────────────────────────────


def mfa_forced_align(
    audio_path: Path,
    text: str,
    language: str = "pl",
) -> list[dict]:
    """Run MFA forced alignment and return word-level timestamps.

    Args:
        audio_path: Path to a WAV audio file.
        text: The transcript that was spoken in the audio.
        language: Language code (default ``"pl"``).

    Returns:
        List of word dicts::

            [{"word": "Polska", "start_ms": 0, "end_ms": 320}, ...]
    """
    cmd = _resolve_mfa_cmd()
    if not cmd:
        raise RuntimeError(
            "MFA binary not found. Install with: "
            "conda create -n mfa -c conda-forge montreal-forced-aligner"
        )

    acoustic, dictionary = _ensure_mfa_models(language)
    audio_path = Path(audio_path)

    with tempfile.TemporaryDirectory(prefix="mfa_") as tmpdir:
        corpus = Path(tmpdir) / "corpus"
        output = Path(tmpdir) / "output"
        corpus.mkdir()
        output.mkdir()

        # MFA expects a .wav and a matching .lab file in the corpus dir
        wav_dest = corpus / "segment.wav"
        lab_dest = corpus / "segment.lab"

        shutil.copy2(audio_path, wav_dest)
        lab_dest.write_text(text.strip(), encoding="utf-8")

        # Run MFA
        result = subprocess.run(
            [
                *cmd, "align",
                str(corpus),
                dictionary,
                acoustic,
                str(output),
                "--clean",
                "--single_speaker",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            logger.error("MFA stderr:\n%s", result.stderr)
            raise RuntimeError(f"MFA alignment failed (rc={result.returncode}): {result.stderr[:500]}")

        # Parse TextGrid output
        tg_path = output / "corpus" / "segment.TextGrid"
        if not tg_path.exists():
            # Some MFA versions output directly without the corpus subdirectory
            tg_path = output / "segment.TextGrid"
        if not tg_path.exists():
            raise FileNotFoundError(
                f"MFA did not produce expected TextGrid. "
                f"Output dir contents: {list(output.rglob('*'))}"
            )

        tg = textgrid.openTextgrid(str(tg_path), includeEmptyIntervals=False)

        # MFA produces a "words" tier
        word_tier = tg.getTier("words")
        words = []
        for interval in word_tier.entries:
            label = interval.label.strip()
            if not label:
                continue
            words.append({
                "word": label,
                "start_ms": int(round(interval.start * 1000)),
                "end_ms": int(round(interval.end * 1000)),
            })

    # Restore original capitalisation & punctuation from the source text.
    # MFA strips punctuation and lowercases words in the TextGrid output,
    # so we walk both lists in order and replace MFA labels with the
    # original tokens when the stripped forms match.
    words = _restore_original_text(words, text)

    logger.debug("MFA aligned %d words from %s", len(words), audio_path.name)
    return words


def build_aligned_chunks(
    text: str,
    audio_path: Path,
    start_offset_ms: int = 0,
    language: str = "pl",
) -> tuple[list[dict], int]:
    """Build word-aligned chunks from text and audio.

    Args:
        text: Original text.
        audio_path: Path to audio file.
        start_offset_ms: Offset for timestamps.
        language: Language code.

    Returns:
        Tuple of (aligned_words, end_ms).
    """
    aligned = mfa_forced_align(audio_path, text, language)

    if start_offset_ms:
        for w in aligned:
            w["start_ms"] += start_offset_ms
            w["end_ms"] += start_offset_ms

    end_ms = aligned[-1]["end_ms"] if aligned else start_offset_ms
    return aligned, end_ms
