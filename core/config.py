"""Central settings. Override any of these in .env (see .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ---------- LLM provider ----------
# Recommended free setup: LLM_PROVIDER=gemini (best free quality) + LLM_FALLBACK_PROVIDER=groq
# (separate free quota; used automatically when Gemini is rate-limited or unavailable).
# ollama (local, no key) and anthropic (paid) are also supported.
PROVIDERS = {
    "gemini": {
        "transport": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
        "model": "gemini-flash-latest",  # alias that tracks Google's current Flash model
        "max_tokens": 16000,
    },
    "groq": {
        "transport": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model": "openai/gpt-oss-120b",
        # Free tier allows ~8k tokens/minute (prompt + max output), so keep output modest.
        "max_tokens": 4500,
    },
    "ollama": {
        "transport": "ollama",
        "base_url": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        "key_env": None,
        "model": "llama3.1:8b",
        "max_tokens": 6000,
    },
    "anthropic": {
        "transport": "anthropic",
        "key_env": "ANTHROPIC_API_KEY",
        "model": os.getenv("CLAUDE_MODEL", "claude-opus-5-5"),
        "max_tokens": int(os.getenv("CLAUDE_MAX_TOKENS", "16000")),
    },
}

# MOCK_LLM=1 returns data/mock_feedback.json instead of calling any model (UI work without a key).
MOCK_LLM = os.getenv("MOCK_LLM", "0") == "1"


def _provider_name(var: str, default: str) -> str:
    name = (os.getenv(var) or default).strip().lower()
    if name and name not in PROVIDERS:
        raise RuntimeError(f"{var} must be one of {list(PROVIDERS)}, got {name!r}")
    return name


PROVIDER = _provider_name("LLM_PROVIDER", "gemini")
FALLBACK_PROVIDER = _provider_name("LLM_FALLBACK_PROVIDER", "groq")
if FALLBACK_PROVIDER == PROVIDER:
    FALLBACK_PROVIDER = ""


def provider_settings(name: str) -> dict:
    """Resolved settings for one provider. LLM_MODEL / LLM_MAX_TOKENS / LLM_BASE_URL apply to the
    primary provider; <NAME>_MODEL (e.g. GROQ_MODEL) overrides the model for any provider."""
    preset = PROVIDERS[name]
    primary = name == PROVIDER
    return {
        "name": name,
        "transport": preset["transport"],
        "model": os.getenv(f"{name.upper()}_MODEL") or (os.getenv("LLM_MODEL") if primary else "") or preset["model"],
        "base_url": ((os.getenv("LLM_BASE_URL") if primary else "") or preset.get("base_url", "")).rstrip("/"),
        "key_env": preset["key_env"],
        "api_key": os.getenv(preset["key_env"], "") if preset["key_env"] else "",
        "max_tokens": int((os.getenv("LLM_MAX_TOKENS") if primary else "") or preset["max_tokens"]),
    }


PRIMARY = provider_settings(PROVIDER)
FALLBACK = provider_settings(FALLBACK_PROVIDER) if FALLBACK_PROVIDER else None
MODEL = PRIMARY["model"]

# Optional: "low" | "medium" | "high" for models that think before answering (Gemini, gpt-oss).
# "low" keeps responses fast and within free-tier token limits. Empty = provider default.
REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "low")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE")) if os.getenv("LLM_TEMPERATURE") else None
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "16384"))  # Ollama's default context is too small for our prompt
EFFORT = os.getenv("CLAUDE_EFFORT", "medium")  # anthropic only

MODEL_LABEL = "mock" if MOCK_LLM else f"{PROVIDER}:{MODEL}" + (f" (fallback {FALLBACK_PROVIDER}:{FALLBACK['model']})" if FALLBACK else "")

# USE_CACHE=1 reuses earlier results for identical essay + options (makes the demo instant and safe).
USE_CACHE = os.getenv("USE_CACHE", "1") == "1"

ON_VERCEL = bool(os.getenv("VERCEL"))

DATA_DIR = ROOT / "data"
SAMPLE_DIR = DATA_DIR / "sample_essays"
# Committed demo results live in data/cache (read-only on Vercel); new results go to a writable dir.
DEMO_CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR = Path("/tmp/essay-cache") if ON_VERCEL else DEMO_CACHE_DIR
MOCK_FILE = DATA_DIR / "mock_feedback.json"
EVAL_DIR = ROOT / "eval"

# If set, the API requires this code in the X-Access-Code header (protects your free-tier quota once deployed).
ACCESS_CODE = os.getenv("APP_ACCESS_CODE", "")

MIN_WORDS = 50
MAX_WORDS = 3000
