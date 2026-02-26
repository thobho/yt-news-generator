"""
OpenRouter service — routes all LLM chat completions through openrouter.ai.

Provides per-task model constants tuned for cost/quality balance.

DALL-E image generation and Whisper transcription remain on OpenAI directly
since OpenRouter does not support those API endpoints.
"""

import os

from openai import OpenAI

# ── Per-task model constants ────────────────────────────────────────────────
# Pass model= explicitly to any generation function to override these.
#
# All three dialogue models require strict json_schema structured output support.
# DeepSeek R1 is excluded because it does not support json_schema strict mode.
#
# Cost reference (input / output per 1M tokens, Feb 2026):
#   anthropic/claude-opus-4.6     $5.00 / $25.00   — top creative + reasoning + Polish
#   anthropic/claude-sonnet-4.6   $3.00 / $15.00   — strong alternative, 40% cheaper
#   google/gemini-2.5-pro         $1.25 / $10.00   — best value; 84% GPQA, json_schema ✓
#   google/gemini-2.0-flash-001   $0.10 /  $0.40   — cheap, good enough for support tasks

# Step 1 — creative dialogue generation
#   Winner: claude-opus-4.6 — #1 on Mazur creative writing benchmark (score 8.56),
#   best character voice, narrative tension, and Polish idiomatic generation.
#   Alternatives: anthropic/claude-sonnet-4.6 (close quality, 40% cheaper),
#                 google/gemini-2.5-pro ($1.25/1M, #1 on LMArena human preference)
DIALOGUE_GENERATE = "google/gemini-2.5-pro"

# Step 2 — structural/logic refinement and fact-checking
#   Winner: claude-opus-4.6 — 91.3% GPQA Diamond (best among json_schema-compatible
#   models). Identifies logical contradictions and structural inconsistencies reliably.
#   Alternatives: google/gemini-2.5-pro (84% GPQA, $1.25/1M, 1M context window),
#                 deepseek/deepseek-r1 ($0.70/1M, best reasoning per dollar — but
#                 does NOT support json_schema strict mode, requires prompt workaround)
DIALOGUE_REFINE = "google/gemini-2.5-pro"

# Step 3 — Polish language naturalness and style polish
#   Winner: claude-opus-4.6 — ranked #1 in Scientific Reports Polish medical exam
#   study; ranked #1 in 9/11 language pairs in WMT24 translation naturalness.
#   Best at preserving tone, register, and idiomatic Polish without translation artifacts.
#   Alternatives: google/gemini-2.5-pro ($1.25/1M, strong multilingual, 89.8% MMLU),
#                 anthropic/claude-sonnet-4.6 ($3.00/1M)
DIALOGUE_POLISH = "anthropic/claude-opus-4.6"

# Creative visual reasoning from dialogue text
IMAGE_PROMPTS = "google/gemini-2.0-flash-001"

# Simple structured output (json_object, not strict schema); free model works
YT_METADATA = "meta-llama/llama-3.3-70b-instruct:free"

# Analytical pattern recognition over historical performance data
NEWS_SELECTION = "google/gemini-2.0-flash-001"


def get_chat_client() -> OpenAI:
    """Return an OpenAI-compatible client pointed at OpenRouter.

    Used for all chat completion tasks (dialogue, image prompts, metadata,
    news selection). DALL-E and Whisper must use get_openai_client() instead.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY is not set. Get your key at https://openrouter.ai/keys"
        )
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "https://github.com/yt-centric-generator",
            "X-Title": "YT Centric Generator",
        },
    )


def get_openai_client() -> OpenAI:
    """Return a standard OpenAI client.

    Use only for endpoints OpenRouter does not support:
    - DALL-E image generation  (client.images.generate)
    - Whisper transcription    (client.audio.transcriptions.create)
    """
    return OpenAI()
