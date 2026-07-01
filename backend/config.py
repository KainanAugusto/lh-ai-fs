"""Central configuration, loaded once from the environment.

The whole pipeline talks to the LLM through the OpenAI SDK, but every knob is
env-driven so the same code runs against OpenAI (the challenge default, what
reviewers use) or any OpenAI-compatible endpoint (e.g. Google Gemini's
``/v1beta/openai/`` gateway) just by changing ``.env`` — no code changes.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


# Model used for every agent call. Defaults to OpenAI's gpt-4o so reviewers who
# only set OPENAI_API_KEY get a working pipeline out of the box.
MODEL: str = os.getenv("MODEL", "gpt-4o")

# Base URL for the OpenAI-compatible API. Leave unset for OpenAI itself; point it
# at Gemini's gateway (https://generativelanguage.googleapis.com/v1beta/openai/)
# or any other compatible provider for free local development.
OPENAI_BASE_URL: str | None = os.getenv("OPENAI_BASE_URL") or None

# API key for whichever provider OPENAI_BASE_URL targets.
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")

# Deterministic by default: temperature 0 keeps agent output stable, which the
# eval suite relies on for reproducible precision/recall numbers.
TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0"))

# Per-call output ceiling. 0 (the default) means "don't send max_tokens" — let the
# provider use its own default. This matters for reasoning models such as
# gemini-2.5-flash: forcing a high ceiling makes them think/generate up to it,
# blowing past the request timeout. Set a positive value ONLY for providers that
# truncate without it (e.g. SiliconFlow's gpt-oss, which needs headroom for its
# hidden reasoning). See llm.py — it is only sent when > 0.
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "0"))

# Fail fast instead of hanging. A slow or rate-limited provider (e.g. a 429 with
# a long Retry-After) would otherwise leave the pipeline — and the UI — stuck
# "analyzing" indefinitely. Cap the per-request wall-clock and the automatic
# retries so the failure surfaces quickly as a graceful, reported error.
REQUEST_TIMEOUT: float = float(os.getenv("REQUEST_TIMEOUT", "60"))
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "1"))
