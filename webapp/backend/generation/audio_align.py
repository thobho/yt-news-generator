#!/usr/bin/env python3
"""
Audio-text alignment using OpenAI Whisper API.

Provides word-level timestamps by transcribing generated audio with Whisper,
then aligning the transcription back to the original text.
"""

import os
import re
from pathlib import Path
from typing import Optional

from openai import OpenAI

from ..core.logging_config import get_logger

logger = get_logger(__name__)

# Lazy-loaded client
_client = None


def is_whisper_available() -> bool:
    """Check if OpenAI Whisper API is available (API key set)."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def _get_client() -> OpenAI:
    """Get or create OpenAI client."""
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def transcribe_with_timestamps(audio_path: Path, language: str = "pl") -> list[dict]:
    """
    Transcribe audio and return word-level timestamps using OpenAI Whisper API.

    Args:
        audio_path: Path to audio file (WAV or MP3)
        language: Language code (default "pl" for Polish)

    Returns:
        List of word dicts: [{"word": "Polska", "start": 0.0, "end": 0.32}, ...]
    """
    client = _get_client()
    audio_path = Path(audio_path)

    logger.debug("Transcribing %s with OpenAI Whisper API", audio_path.name)

    with open(audio_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language=language,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )

    words = []
    if hasattr(response, "words") and response.words:
        for word_data in response.words:
            words.append({
                "word": word_data.word.strip(),
                "start": word_data.start,
                "end": word_data.end,
            })

    logger.debug("Transcribed %d words from %s", len(words), audio_path.name)
    return words


def _normalize_word(word: str) -> str:
    """Normalize word for matching (lowercase, remove punctuation)."""
    return re.sub(r'[^\w]', '', word.lower())


def align_text_to_audio(
    original_text: str,
    whisper_words: list[dict],
    start_offset_ms: int = 0,
) -> list[dict]:
    """
    Align original text words to Whisper timestamps.

    Uses fuzzy matching to handle minor transcription differences.
    Falls back to proportional distribution for unmatched words.

    Args:
        original_text: Original text that was synthesized
        whisper_words: Word timestamps from Whisper
        start_offset_ms: Offset to add to all timestamps (for merged audio)

    Returns:
        List of aligned words: [{"word": "Polska", "start_ms": 0, "end_ms": 320}, ...]
    """
    original_words = original_text.split()
    if not original_words or not whisper_words:
        return []

    # Normalize for matching
    orig_normalized = [_normalize_word(w) for w in original_words]
    whisper_normalized = [_normalize_word(w["word"]) for w in whisper_words]

    # Simple alignment: match words in order, allowing skips
    aligned = []
    whisper_idx = 0

    for i, (orig_word, orig_norm) in enumerate(zip(original_words, orig_normalized)):
        matched = False

        # Look ahead in Whisper words to find a match
        for j in range(whisper_idx, min(whisper_idx + 5, len(whisper_words))):
            if whisper_normalized[j] == orig_norm or _fuzzy_match(orig_norm, whisper_normalized[j]):
                aligned.append({
                    "word": orig_word,
                    "start_ms": int(whisper_words[j]["start"] * 1000) + start_offset_ms,
                    "end_ms": int(whisper_words[j]["end"] * 1000) + start_offset_ms,
                })
                whisper_idx = j + 1
                matched = True
                break

        if not matched:
            # Interpolate from neighbors
            aligned.append({
                "word": orig_word,
                "start_ms": None,  # Will be interpolated
                "end_ms": None,
            })

    # Interpolate missing timestamps
    _interpolate_missing(aligned, start_offset_ms, whisper_words, start_offset_ms)

    return aligned


def _fuzzy_match(a: str, b: str) -> bool:
    """Check if two normalized words are similar enough."""
    if not a or not b:
        return False
    # Allow for minor differences (Polish diacritics, transcription errors)
    if a in b or b in a:
        return True
    # Check edit distance for short words
    if len(a) <= 3 or len(b) <= 3:
        return a == b
    # For longer words, allow 1-2 character difference
    common = sum(1 for ca, cb in zip(a, b) if ca == cb)
    return common >= min(len(a), len(b)) * 0.7


def _interpolate_missing(
    aligned: list[dict],
    start_offset_ms: int,
    whisper_words: list[dict],
    offset_ms: int,
):
    """Fill in missing timestamps by interpolation."""
    if not aligned:
        return

    # Get total duration from whisper words
    if whisper_words:
        total_end_ms = int(whisper_words[-1]["end"] * 1000) + offset_ms
    else:
        total_end_ms = start_offset_ms + 1000  # Fallback

    # Find anchors (words with timestamps)
    anchors = [(i, w) for i, w in enumerate(aligned) if w["start_ms"] is not None]

    if not anchors:
        # No anchors - distribute evenly
        duration = total_end_ms - start_offset_ms
        word_duration = duration // len(aligned)
        for i, w in enumerate(aligned):
            w["start_ms"] = start_offset_ms + i * word_duration
            w["end_ms"] = start_offset_ms + (i + 1) * word_duration
        return

    # Interpolate between anchors
    for idx in range(len(anchors)):
        curr_anchor_idx, curr_anchor = anchors[idx]

        # Handle words before first anchor
        if idx == 0 and curr_anchor_idx > 0:
            gap_start = start_offset_ms
            gap_end = curr_anchor["start_ms"]
            gap_words = aligned[:curr_anchor_idx]
            _distribute_in_gap(gap_words, gap_start, gap_end)

        # Handle words between anchors
        if idx < len(anchors) - 1:
            next_anchor_idx, next_anchor = anchors[idx + 1]
            gap_start = curr_anchor["end_ms"]
            gap_end = next_anchor["start_ms"]
            gap_words = aligned[curr_anchor_idx + 1:next_anchor_idx]
            if gap_words:
                _distribute_in_gap(gap_words, gap_start, gap_end)

        # Handle words after last anchor
        if idx == len(anchors) - 1 and curr_anchor_idx < len(aligned) - 1:
            gap_start = curr_anchor["end_ms"]
            gap_end = total_end_ms
            gap_words = aligned[curr_anchor_idx + 1:]
            _distribute_in_gap(gap_words, gap_start, gap_end)


def _distribute_in_gap(words: list[dict], start_ms: int, end_ms: int):
    """Distribute words evenly in a time gap."""
    if not words:
        return
    duration = end_ms - start_ms
    word_duration = max(1, duration // len(words))
    for i, w in enumerate(words):
        w["start_ms"] = start_ms + i * word_duration
        w["end_ms"] = min(start_ms + (i + 1) * word_duration, end_ms)


def build_aligned_chunks(
    text: str,
    audio_path: Path,
    start_offset_ms: int = 0,
    language: str = "pl",
) -> tuple[list[dict], int]:
    """
    Build word-aligned chunks from text and audio.

    Args:
        text: Original text
        audio_path: Path to audio file
        start_offset_ms: Offset for timestamps
        language: Language code

    Returns:
        Tuple of (aligned_words, end_ms)
    """
    whisper_words = transcribe_with_timestamps(audio_path, language)
    aligned = align_text_to_audio(text, whisper_words, start_offset_ms)

    if aligned:
        end_ms = aligned[-1]["end_ms"]
    elif whisper_words:
        end_ms = int(whisper_words[-1]["end"] * 1000) + start_offset_ms
    else:
        end_ms = start_offset_ms

    return aligned, end_ms
