"""Gemini API helpers: validation, connection test, error classification."""

from __future__ import annotations

import re
import time

from google import genai

# Preferred models — each has its own free-tier RPM bucket.
# Deprecated IDs (gemini-1.5-flash, gemini-1.5-flash-8b) are excluded; the API
# list is queried at runtime so only live models are used.
MODEL_FALLBACK_CHAIN = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]

DEFAULT_MODEL = MODEL_FALLBACK_CHAIN[0]

MAX_API_RETRIES = 5
CONNECT_ATTEMPTS_PER_MODEL = 3
CONNECT_FULL_CHAIN_ROUNDS = 2  # retry entire chain once after a cooldown
BASE_RETRY_WAIT = 15  # seconds
RATE_LIMIT_COOLDOWN = 60  # seconds between full-chain retries


def normalize_api_key(api_key: str) -> str:
    key = api_key.strip().strip('"').strip("'")
    if key.startswith("GEMINI_API_KEY="):
        key = key.split("=", 1)[1].strip().strip('"').strip("'")
    return key


def validate_api_key_present(api_key: str) -> str | None:
    """Return error message if key is missing, else None."""
    if not api_key or api_key in ("paste_your_key_here", "your_gemini_api_key_here"):
        return (
            "GEMINI_API_KEY is not set. Add your key to the .env file.\n"
            "  Get a free key: https://aistudio.google.com/apikey"
        )
    if len(api_key) < 10:
        return "GEMINI_API_KEY looks too short. Check your .env file."
    return None


def classify_api_error(err: str) -> str:
    """Return: auth | rate_limit | model_not_found | unavailable | other"""
    upper = err.upper()
    if any(
        token in upper
        for token in (
            "API_KEY_INVALID",
            "API KEY NOT VALID",
            "INVALID API KEY",
            "PERMISSION_DENIED",
            "UNAUTHENTICATED",
            "401",
            "403",
        )
    ):
        return "auth"
    if "INVALID_ARGUMENT" in upper and "API" in upper and "KEY" in upper:
        return "auth"
    if any(token in upper for token in ("429", "RESOURCE_EXHAUSTED", "RATE LIMIT", "QUOTA")):
        return "rate_limit"
    if any(
        token in upper
        for token in (
            "404",
            "NOT_FOUND",
            "NOT FOUND",
            "MODEL_NOT_FOUND",
            "IS NOT SUPPORTED",
            "DOES NOT EXIST",
        )
    ):
        return "model_not_found"
    if any(token in upper for token in ("503", "UNAVAILABLE", "OVERLOADED")):
        return "unavailable"
    return "other"


def parse_retry_seconds(err: str) -> float | None:
    """Extract server-suggested retry delay from Gemini error JSON/text."""
    match = re.search(r"Please retry in ([\d.]+)s", err)
    if match:
        return float(match.group(1))
    match = re.search(r'"retryDelay":\s*"(\d+)s"', err)
    if match:
        return float(match.group(1))
    return None


def is_daily_quota_exhausted(err: str) -> bool:
    upper = err.upper()
    return "FREE_TIER" in upper and ("PERDAY" in upper or "PER_DAY" in upper or "DAILY" in upper)


def list_generate_content_models(client: genai.Client) -> set[str]:
    """Return model IDs that support generateContent for this API key."""
    names: set[str] = set()
    for entry in client.models.list():
        actions = entry.supported_actions or []
        if "generateContent" not in actions:
            continue
        name = entry.name or ""
        if name.startswith("models/"):
            name = name[len("models/") :]
        if name:
            names.add(name)
    return names


def resolve_model_chain(client: genai.Client, preferred: list[str]) -> list[str]:
    """
    Keep preferred order but drop models the API does not expose.
    Raises RuntimeError if nothing usable remains.
    """
    available = list_generate_content_models(client)
    if not available:
        raise RuntimeError(
            "Could not list Gemini models. Check your API key and network.\n"
            "  https://aistudio.google.com/apikey"
        )

    chain: list[str] = []
    seen: set[str] = set()
    for model in preferred:
        if model in available and model not in seen:
            chain.append(model)
            seen.add(model)
        elif model not in available:
            print(f"  Skipping unavailable model: {model}")

    if chain:
        return chain

    for fallback in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
        if fallback in available:
            print(f"  Using fallback model: {fallback}")
            return [fallback]

    raise RuntimeError(
        "No supported Gemini generateContent models found for this API key.\n"
        "  Run demo mode: ./run.sh --demo"
    )


def test_connection(client: genai.Client, model: str) -> None:
    """Raise on auth/connection failure before starting the agent loop."""
    client.models.generate_content(model=model, contents="Say OK")


def _wait_for_rate_limit(model: str, err: str, attempt: int, max_attempts: int) -> bool:
    """Sleep and return True if caller should retry the same model."""
    server_wait = parse_retry_seconds(err)
    if server_wait is not None and server_wait <= 120:
        secs = int(server_wait) + 2
    else:
        secs = retry_wait_seconds(attempt + 1)
    print(f"  Rate limit on {model} — waiting {secs}s (attempt {attempt + 1}/{max_attempts})...")
    time.sleep(secs)
    return True


def connect_gemini(client: genai.Client, models: list[str]) -> str:
    """
    Find a working model. Retries each model with backoff, then cycles the
    full fallback chain once after a cooldown if every model is rate-limited.
    Raises RuntimeError with a clear message on failure.
    """
    last_err = ""
    for chain_round in range(CONNECT_FULL_CHAIN_ROUNDS):
        if chain_round > 0:
            print(f"  All models busy — waiting {RATE_LIMIT_COOLDOWN}s before retrying chain...")
            time.sleep(RATE_LIMIT_COOLDOWN)

        for model in models:
            for attempt in range(CONNECT_ATTEMPTS_PER_MODEL):
                try:
                    test_connection(client, model)
                    return model
                except Exception as exc:
                    last_err = str(exc)
                    kind = classify_api_error(last_err)

                    if kind == "auth":
                        raise RuntimeError(
                            "Gemini rejected your API key. Check GEMINI_API_KEY in .env\n"
                            "  Create a key: https://aistudio.google.com/apikey"
                        ) from exc

                    if kind == "model_not_found":
                        print(f"  {model}: model not available, trying next...")
                        break

                    if kind == "rate_limit":
                        if attempt + 1 < CONNECT_ATTEMPTS_PER_MODEL:
                            _wait_for_rate_limit(
                                model, last_err, attempt, CONNECT_ATTEMPTS_PER_MODEL
                            )
                            continue
                        print(f"  {model}: quota/rate limit, trying next model...")
                        break

                    if kind == "unavailable":
                        if attempt + 1 < CONNECT_ATTEMPTS_PER_MODEL:
                            secs = retry_wait_seconds(attempt + 1)
                            print(
                                f"  {model}: temporarily unavailable — "
                                f"waiting {secs}s (attempt {attempt + 1}/{CONNECT_ATTEMPTS_PER_MODEL})..."
                            )
                            time.sleep(secs)
                            continue
                        print(f"  {model}: temporarily unavailable, trying next...")
                        break

                    raise

    if is_daily_quota_exhausted(last_err):
        raise RuntimeError(
            "Gemini free-tier daily quota exhausted.\n"
            "  Options:\n"
            "  1. Wait until tomorrow (quota resets daily)\n"
            "  2. Use a fresh API key from a different Google account in .env\n"
            "  3. Run demo mode: ./run.sh --demo"
        )

    raise RuntimeError(
        f"Could not connect to Gemini API.\n  Last error: {last_err[:400]}"
    )


def retry_wait_seconds(attempt: int) -> int:
    """Exponential backoff capped at 2 minutes."""
    return min(120, BASE_RETRY_WAIT * (2 ** max(0, attempt - 1)))


def next_model(
    current: str,
    models: list[str],
    *,
    blocked: set[str] | None = None,
) -> str | None:
    """Next model in chain, skipping blocked IDs."""
    skip = blocked or set()
    try:
        start = models.index(current) + 1
    except ValueError:
        start = 0
    for model in models[start:]:
        if model not in skip:
            return model
    return None
