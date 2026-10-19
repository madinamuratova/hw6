"""Paths, model, and limits for the Campus Customs agent team."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "backend" / "prompts"
OUTPUT_DIR = ROOT / "output"
AUDIT_PATH = Path(os.environ.get("CAMPUS_CUSTOMS_AUDIT", OUTPUT_DIR / "audit_trail.json"))  # env only for tests
# Same file (and same test override) the MCP server writes drafts to; the API only reads it.
DRAFTS_PATH = Path(os.environ.get("CAMPUS_CUSTOMS_DRAFTS", OUTPUT_DIR / "drafts.json"))
# The MCP server owns the file; this is for display (shows the scratch copy when a test points the server at one).
WORKING_DB_LABEL = os.environ.get("CAMPUS_CUSTOMS_DB", "data/campus_customs_new.db")
MCP_CONFIG_PATH = ROOT / ".mcp.json"  # same file Claude Code uses (Problem 4)
MCP_SERVER_NAME = "campus-customs"

# The only model every agent uses. OPENAI_MODEL in .env is ignored on purpose.
MODEL_NAME = "gpt-6-luna"
DEFAULT_PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
REQUEST_TIMEOUT_SECONDS = 120  # a stuck model call fails instead of hanging the whole team
REQUEST_MAX_RETRIES = 2

# Token and loop controls (shared across the whole team for one run).
USAGE_LIMITS = UsageLimits(request_limit=60, total_tokens_limit=400_000)
MAX_DELEGATION_DEPTH = 2  # Boss (0) -> specialist (1) -> one peer consult (2), no further

# Project .env first (if any), then the course .env one folder up.
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")


def build_model() -> OpenAIResponsesModel:
    """gpt-6-luna through Portkey, using PORTKEY_API_KEY."""
    api_key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set in the course .env file.")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=os.getenv("PORTKEY_BASE_URL", DEFAULT_PORTKEY_BASE_URL).rstrip("/"),
        default_headers={
            "x-portkey-api-key": api_key,
            # Portkey can replay a stored response for a repeated request (found in Problem 3).
            # Force a real model call so every run's answers and token usage are real.
            "x-portkey-cache-force-refresh": "true",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=REQUEST_MAX_RETRIES,
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
