"""Model client: returns JSON matching a schema, from the provider(s) configured in .env.

Default free setup: Groq first, Gemini as automatic backup. Each provider may list several models
(Gemini's free tier is per model, some only 20 requests/day), and they are tried in order. A model that
hits a rate limit is skipped until its cooldown ends, so later requests don't waste time on it.

Providers (core/config.py PROVIDERS):
  groq, gemini  -> OpenAI-compatible /chat/completions over HTTPS (free tiers)
  ollama        -> local Ollama /api/chat (free, offline; not available on Vercel)
  anthropic     -> Claude via the anthropic SDK (paid; optional)

CLI helpers:
  python -m core.llm models   # list models each configured key can use
  python -m core.llm test     # one tiny request per configured provider/model
"""
import json
import os
import re
import sys
import time

import httpx

from . import config


class LLMError(RuntimeError):
    """A user-presentable failure from the model call."""


class RetryableLLMError(LLMError):
    """A failure another model/provider might not have.

    kind: rate_limit | not_found | server | invalid_output | too_large | timeout | network | no_key | auth
    """

    def __init__(self, message: str, kind: str = "server", cooldown: float = 0):
        super().__init__(message)
        self.kind = kind
        self.cooldown = cooldown


# Kinds where trying the next model of the same provider makes sense.
ROTATE_KINDS = {"rate_limit", "not_found", "server", "invalid_output", "too_large", "timeout"}
GROQ_TPM = int(os.getenv("GROQ_TPM", "8000"))  # Groq free-tier tokens/minute: prompt + max output must fit

_schema_mode_unsupported: set[str] = set()  # provider:model pairs that rejected json_schema
_cooldown_until: dict[str, float] = {}       # provider:model -> time.time() when it may be used again
last_used = ""  # "provider:model" that produced the most recent result


def generate_json(system: str, user: str, schema: dict, mock_ok: bool = True) -> dict:
    """mock_ok=False for calls that aren't essay feedback (e.g. synthetic data generation)."""
    global last_used
    if config.MOCK_LLM:
        if not mock_ok:
            raise LLMError("This command needs a real model. Set MOCK_LLM=0 and configure LLM_PROVIDER.")
        last_used = "mock"
        return json.loads(config.MOCK_FILE.read_text(encoding="utf-8"))

    errors = []
    for s in (config.PRIMARY, config.FALLBACK):
        if not s:
            continue
        try:
            result, model = _call_provider(s, system, user, schema)
            last_used = f"{s['name']}:{model}"
            return result
        except RetryableLLMError as e:
            errors.append(f"{s['name']}: {e}")
            print(f"[llm] {s['name']} unavailable ({e})", file=sys.stderr)
    raise LLMError(" | ".join(errors) or "No model provider is configured.")


def _call_provider(s: dict, system: str, user: str, schema: dict) -> tuple[dict, str]:
    """Try the provider's models in order, skipping ones that are cooling down."""
    if s["transport"] == "ollama":
        return _ollama(s, system, user, schema), s["model"]
    if s["transport"] == "anthropic":
        return _anthropic(s, system, user, schema), s["model"]

    last_error = None
    now = time.time()
    candidates = [m for m in s["models"] if _cooldown_until.get(f"{s['name']}:{m}", 0) <= now]
    if not candidates:
        soonest = min(_cooldown_until.get(f"{s['name']}:{m}", 0) for m in s["models"]) - now
        raise RetryableLLMError(f"all {s['name']} models are rate-limited for about {_human(soonest)}", "rate_limit")
    for model in candidates:
        try:
            return _openai_compatible(s, model, system, user, schema), model
        except RetryableLLMError as e:
            last_error = e
            if e.cooldown:
                _cooldown_until[f"{s['name']}:{model}"] = time.time() + e.cooldown
            if e.kind not in ROTATE_KINDS:
                raise
            if len(candidates) > 1:
                print(f"[llm] {s['name']}:{model} failed ({e.kind}); trying next model", file=sys.stderr)
    raise last_error


# ---------- shared helpers ----------

def _human(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600}h {seconds % 3600 // 60}m" if seconds >= 3600 else f"{max(1, seconds // 60)} min"


def _parse_json(text: str) -> dict:
    """Parse model output, tolerating ```json fences or chatter around the object."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise RetryableLLMError("the model returned invalid JSON", "invalid_output")


def _schema_instruction(schema: dict) -> str:
    return ("\n\nRespond with ONLY a JSON object (no markdown, no commentary) that matches this JSON schema "
            "exactly, including every required field:\n" + json.dumps(schema))


def _rate_limit_cooldown(resp: httpx.Response) -> float:
    """How long to skip a model after a 429: daily quotas -> until reset, per-minute -> about a minute."""
    text = resp.text
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', text)
    if m:
        return float(m.group(1))
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(\d+(?:\.\d+)?)s", text, re.IGNORECASE)
    if m:
        h, mi, se = (float(x) if x else 0 for x in m.groups())
        return h * 3600 + mi * 60 + se
    try:
        return float(resp.headers.get("retry-after", ""))
    except ValueError:
        return 3600 if "per day" in text.lower() or "perday" in text.lower() else 60


def _post(s: dict, url: str, payload: dict, headers: dict, timeout: float) -> httpx.Response:
    """POST with one short retry on transient errors. Long waits are left to model rotation instead."""
    for attempt in range(2):
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
        except httpx.TimeoutException as e:
            raise RetryableLLMError(f"{s['name']} took longer than {int(timeout)}s", "timeout", cooldown=60) from e
        except httpx.HTTPError as e:
            raise RetryableLLMError(f"could not reach {s['name']}: {e}", "network") from e
        short_429 = resp.status_code == 429 and _rate_limit_cooldown(resp) <= 6
        if attempt == 0 and (short_429 or resp.status_code in (500, 502, 503, 504)):
            time.sleep(min(6, max(2, _rate_limit_cooldown(resp) if short_429 else 2)))
            continue
        return resp
    return resp


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        body = body[0] if isinstance(body, list) else body
        return str(body.get("error", {}).get("message") or resp.text)[:400]
    except ValueError:
        return resp.text[:400]


def _raise_for(s: dict, model: str, resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    name, detail = s["name"], _error_message(resp)
    if resp.status_code in (401, 403):
        raise RetryableLLMError(f"{name} rejected the API key; check {s['key_env']} in .env ({detail})", "auth")
    if resp.status_code == 404:
        raise RetryableLLMError(f"model '{model}' isn't available on {name} ({detail})", "not_found", cooldown=86400)
    if resp.status_code == 429:
        wait = _rate_limit_cooldown(resp)
        raise RetryableLLMError(f"{name}:{model} free-tier limit reached (resets in about {_human(wait)})", "rate_limit", cooldown=wait)
    if resp.status_code >= 500:
        raise RetryableLLMError(f"{name}:{model} is overloaded or down ({resp.status_code})", "server", cooldown=30)
    if resp.status_code == 413 or "too large" in detail.lower() or "reduce the length" in detail.lower():
        raise RetryableLLMError(f"request too large for {name}:{model}'s free tier", "too_large")
    raise LLMError(f"{name} error {resp.status_code}: {detail}")


# ---------- OpenAI-compatible (Groq, Gemini, custom LLM_BASE_URL) ----------

def _max_tokens(s: dict, system: str, user: str) -> int:
    if s["name"] != "groq":
        return s["max_tokens"]
    # Groq's free tier rejects requests whose prompt + max output exceed its tokens-per-minute limit.
    prompt_estimate = int((len(system) + len(user)) / 3.2)
    return max(2500, min(s["max_tokens"], GROQ_TPM - prompt_estimate - 300))


def _openai_compatible(s: dict, model: str, system: str, user: str, schema: dict) -> dict:
    if not s["api_key"]:
        raise RetryableLLMError(f"no API key for {s['name']}; set {s['key_env']} in .env", "no_key")
    headers = {"Authorization": f"Bearer {s['api_key']}"}
    url = f"{s['base_url']}/chat/completions"
    key = f"{s['name']}:{model}"

    def payload(strict: bool) -> dict:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system if strict else system + _schema_instruction(schema)},
                {"role": "user", "content": user},
            ],
            "max_tokens": _max_tokens(s, system, user),
            "response_format": (
                {"type": "json_schema", "json_schema": {"name": "result", "schema": schema, "strict": True}}
                if strict else {"type": "json_object"}
            ),
        }
        if config.REASONING_EFFORT:
            body["reasoning_effort"] = config.REASONING_EFFORT
        if config.TEMPERATURE is not None:
            body["temperature"] = config.TEMPERATURE
        return body

    strict = key not in _schema_mode_unsupported
    resp = _post(s, url, payload(strict), headers, timeout=240)

    if resp.status_code == 400:
        err = _error_json(resp)
        if err.get("code") == "json_validate_failed":
            # The model produced output that failed the provider's own JSON check (often cut off).
            # Use it if it's parseable after all; otherwise let the next model/provider try.
            try:
                return _parse_json(err.get("failed_generation", ""))
            except RetryableLLMError:
                raise RetryableLLMError(f"{key} produced incomplete JSON", "invalid_output")
        if strict and any(w in str(err.get("message", "")).lower() for w in ("json_schema", "response_format", "schema")):
            print(f"[llm] {key} rejected json_schema; using JSON mode", file=sys.stderr)
            _schema_mode_unsupported.add(key)
            resp = _post(s, url, payload(False), headers, timeout=240)
    _raise_for(s, model, resp)

    choice = resp.json()["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RetryableLLMError(f"{key}'s answer was cut off", "invalid_output")
    return _parse_json(choice["message"].get("content") or "")


def _error_json(resp: httpx.Response) -> dict:
    try:
        body = resp.json()
        body = body[0] if isinstance(body, list) else body
        return body.get("error", {}) if isinstance(body, dict) else {}
    except ValueError:
        return {}


# ---------- Ollama (local) ----------

def _ollama(s: dict, system: str, user: str, schema: dict) -> dict:
    body = {
        "model": s["model"],
        "messages": [{"role": "system", "content": system + _schema_instruction(schema)},
                     {"role": "user", "content": user}],
        "format": schema,  # Ollama constrains generation to this JSON schema
        "stream": False,
        "options": {"num_ctx": config.OLLAMA_NUM_CTX, "num_predict": s["max_tokens"],
                    "temperature": 0.2 if config.TEMPERATURE is None else config.TEMPERATURE},
    }
    try:
        resp = httpx.post(f"{s['base_url']}/api/chat", json=body, timeout=900)
    except httpx.ConnectError as e:
        raise RetryableLLMError("Ollama isn't running (open the Ollama app or run `ollama serve`)", "network") from e
    except httpx.TimeoutException as e:
        raise RetryableLLMError("Ollama took longer than 15 minutes", "timeout") from e
    if resp.status_code == 404:
        raise RetryableLLMError(f"Ollama model '{s['model']}' isn't downloaded; run: ollama pull {s['model']}", "not_found")
    _raise_for(s, s["model"], resp)
    data = resp.json()
    if data.get("done_reason") == "length":
        raise RetryableLLMError("Ollama's answer was cut off; raise LLM_MAX_TOKENS or OLLAMA_NUM_CTX", "invalid_output")
    return _parse_json(data.get("message", {}).get("content", ""))


# ---------- Anthropic (paid, optional) ----------

def _anthropic(s: dict, system: str, user: str, schema: dict) -> dict:
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("LLM_PROVIDER=anthropic needs `pip install anthropic`.") from e
    try:
        response = anthropic.Anthropic().beta.messages.create(
            model=s["model"],
            max_tokens=s["max_tokens"],
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": config.EFFORT, "format": {"type": "json_schema", "schema": schema}},
            # On a safety-classifier decline, the API retries on Anthropic's recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as e:
        raise RetryableLLMError("Claude authentication failed; set ANTHROPIC_API_KEY in .env", "auth") from e
    except anthropic.RateLimitError as e:
        raise RetryableLLMError("Claude rate limit reached", "rate_limit") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude API error {e.status_code}: {e.message} (request id: {e.request_id})") from e
    except anthropic.APIConnectionError as e:
        raise RetryableLLMError("could not reach the Claude API", "network") from e
    except anthropic.AnthropicError as e:
        raise LLMError(f"Claude client error: {e}") from e
    if response.stop_reason == "refusal":
        raise LLMError("The model declined to review this text.")
    if response.stop_reason == "max_tokens":
        raise RetryableLLMError("Claude's answer was cut off; increase CLAUDE_MAX_TOKENS", "invalid_output")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise LLMError("The model returned no feedback.")
    return json.loads(text)


# ---------- CLI ----------

def _configured() -> list[dict]:
    return [s for s in (config.PRIMARY, config.FALLBACK) if s]


def _list_models() -> None:
    for s in _configured():
        role = "primary" if s is config.PRIMARY else "fallback"
        print(f"\n== {s['name']} ({role}), tried in order: {', '.join(s['models'])}")
        try:
            if s["transport"] == "ollama":
                names = [m["name"] for m in httpx.get(f"{s['base_url']}/api/tags", timeout=10).json().get("models", [])]
            elif s["transport"] == "openai":
                if not s["api_key"]:
                    print(f"   (no key: set {s['key_env']} in .env)")
                    continue
                resp = httpx.get(f"{s['base_url']}/models", headers={"Authorization": f"Bearer {s['api_key']}"}, timeout=30)
                _raise_for(s, "", resp)
                names = sorted(m["id"].removeprefix("models/") for m in resp.json().get("data", []))
            else:
                print("   (listing not supported for anthropic)")
                continue
        except (LLMError, httpx.HTTPError) as e:
            print(f"   error: {e}")
            continue
        for n in names:
            print(("  * " if n in s["models"] else "    ") + n)


def _smoke_test() -> None:
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}, "word": {"type": "string"}},
              "required": ["ok", "word"], "additionalProperties": False}
    for s in _configured():
        role = "primary" if s is config.PRIMARY else "fallback"
        for model in s.get("models", [s["model"]]):
            t = time.time()
            try:
                if s["transport"] == "openai":
                    out = _openai_compatible(s, model, "You are a test endpoint.", 'Return ok=true and word="essay".', schema)
                else:
                    out, _ = _call_provider(s, "You are a test endpoint.", 'Return ok=true and word="essay".', schema)
                print(f"[ok]   {role:8} {s['name']}:{model} answered in {time.time() - t:.1f}s -> {out}")
            except LLMError as e:
                print(f"[fail] {role:8} {s['name']}:{model}: {e}")


if __name__ == "__main__":
    if config.MOCK_LLM:
        sys.exit("MOCK_LLM=1 is set in .env; set it to 0 to test real providers.")
    _list_models() if (sys.argv[1:] or ["test"])[0] == "models" else _smoke_test()
