"""Model client: returns JSON matching a schema, from the provider(s) configured in .env.

Recommended free setup: LLM_PROVIDER=gemini with LLM_FALLBACK_PROVIDER=groq. If the primary
provider is rate-limited, down, or has no key, the request is retried on the fallback provider.

Providers (core/config.py PROVIDERS):
  gemini, groq  -> OpenAI-compatible /chat/completions over HTTPS (free tiers)
  ollama        -> local Ollama /api/chat (free, offline; not available on Vercel)
  anthropic     -> Claude via the anthropic SDK (paid; optional)

Free tiers have tight rate limits, so requests retry on HTTP 429 with backoff. If a model rejects
strict JSON-schema output, we fall back to plain JSON mode with the schema in the prompt.

CLI helpers:
  python -m core.llm models   # list models each configured key can use
  python -m core.llm test     # one tiny request per configured provider
"""
import json
import re
import sys
import time

import httpx

from . import config


class LLMError(RuntimeError):
    """A user-presentable failure from the model call."""


class RetryableLLMError(LLMError):
    """Failure that another provider might not have: rate limit, outage, timeout, missing key."""


MAX_RETRIES = 2
_schema_mode_unsupported: set[str] = set()  # providers that rejected json_schema once
last_used = ""  # "provider:model" that produced the most recent result


def generate_json(system: str, user: str, schema: dict, mock_ok: bool = True) -> dict:
    """mock_ok=False for calls that aren't essay feedback (e.g. synthetic data generation)."""
    global last_used
    if config.MOCK_LLM:
        if not mock_ok:
            raise LLMError("This command needs a real model. Set MOCK_LLM=0 and configure LLM_PROVIDER.")
        last_used = "mock"
        return json.loads(config.MOCK_FILE.read_text(encoding="utf-8"))

    try:
        result = _call(config.PRIMARY, system, user, schema)
        last_used = f"{config.PRIMARY['name']}:{config.PRIMARY['model']}"
        return result
    except RetryableLLMError as primary_error:
        if not config.FALLBACK:
            raise
        print(f"[llm] {config.PRIMARY['name']} failed ({primary_error}); trying {config.FALLBACK['name']}",
              file=sys.stderr)
        try:
            result = _call(config.FALLBACK, system, user, schema)
        except LLMError as fallback_error:
            raise LLMError(f"{primary_error} | Fallback {config.FALLBACK['name']} also failed: {fallback_error}") \
                from fallback_error
        last_used = f"{config.FALLBACK['name']}:{config.FALLBACK['model']}"
        return result


def _call(s: dict, system: str, user: str, schema: dict) -> dict:
    if s["transport"] == "openai":
        return _openai_compatible(s, system, user, schema)
    if s["transport"] == "ollama":
        return _ollama(s, system, user, schema)
    return _anthropic(s, system, user, schema)


# ---------- shared helpers ----------

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
    raise RetryableLLMError("The model returned invalid JSON.")


def _schema_instruction(schema: dict) -> str:
    return ("\n\nRespond with ONLY a JSON object (no markdown, no commentary) that matches this JSON schema "
            "exactly, including every required field:\n" + json.dumps(schema))


def _post(s: dict, url: str, payload: dict, headers: dict, timeout: float) -> httpx.Response:
    """POST with retries on rate limits (429) and transient server errors."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
        except httpx.TimeoutException as e:
            raise RetryableLLMError(f"{s['name']} took longer than {int(timeout)}s") from e
        except httpx.HTTPError as e:
            raise RetryableLLMError(f"could not reach {s['name']}: {e}") from e
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
            wait = _retry_after(resp, attempt)
            # Don't sit out long waits when a fallback provider can answer right away.
            if config.FALLBACK and s["name"] == config.PRIMARY["name"] and wait > 10:
                return resp
            print(f"[llm] {s['name']} returned {resp.status_code}; retrying in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
            continue
        return resp
    return resp


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    try:
        return min(60.0, float(resp.headers.get("retry-after", "")))
    except ValueError:
        return min(60.0, 5.0 * (2 ** attempt))


def _raise_for(s: dict, resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    detail = resp.text[:300]
    name = s["name"]
    if resp.status_code in (401, 403):
        raise RetryableLLMError(f"{name} rejected the API key; check {s['key_env']} in .env ({detail})")
    if resp.status_code == 404:
        raise RetryableLLMError(f"model '{s['model']}' not found on {name}; run `python -m core.llm models` "
                                f"and set the model in .env ({detail})")
    if resp.status_code == 429:
        raise RetryableLLMError(f"{name} free-tier rate limit reached; wait a minute or until the daily reset "
                                f"({detail})")
    if resp.status_code >= 500:
        raise RetryableLLMError(f"{name} server error {resp.status_code} ({detail})")
    if resp.status_code == 413 or "too large" in detail.lower():
        raise RetryableLLMError(f"request too large for {name}'s free tier ({detail})")
    raise LLMError(f"{name} error {resp.status_code}: {detail}")


# ---------- OpenAI-compatible (Gemini, Groq, custom LLM_BASE_URL) ----------

def _openai_compatible(s: dict, system: str, user: str, schema: dict) -> dict:
    if not s["api_key"]:
        raise RetryableLLMError(f"no API key for {s['name']}; set {s['key_env']} in .env")
    headers = {"Authorization": f"Bearer {s['api_key']}"}
    url = f"{s['base_url']}/chat/completions"

    def payload(strict: bool) -> dict:
        body = {
            "model": s["model"],
            "messages": [
                {"role": "system", "content": system if strict else system + _schema_instruction(schema)},
                {"role": "user", "content": user},
            ],
            "max_tokens": s["max_tokens"],
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

    strict = s["name"] not in _schema_mode_unsupported
    resp = _post(s, url, payload(strict), headers, timeout=240)
    if strict and resp.status_code == 400:
        # Some models/providers don't accept strict JSON schemas; retry once in plain JSON mode.
        print(f"[llm] {s['name']}/{s['model']} rejected json_schema; using JSON mode. ({resp.text[:160]})",
              file=sys.stderr)
        _schema_mode_unsupported.add(s["name"])
        resp = _post(s, url, payload(False), headers, timeout=240)
    _raise_for(s, resp)

    choice = resp.json()["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RetryableLLMError(f"{s['name']}'s answer was cut off (raise its max tokens or lower LLM_REASONING_EFFORT)")
    return _parse_json(choice["message"].get("content") or "")


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
        raise RetryableLLMError("Ollama isn't running (open the Ollama app or run `ollama serve`)") from e
    except httpx.TimeoutException as e:
        raise RetryableLLMError("Ollama took longer than 15 minutes") from e
    if resp.status_code == 404:
        raise RetryableLLMError(f"Ollama model '{s['model']}' isn't downloaded; run: ollama pull {s['model']}")
    _raise_for(s, resp)
    data = resp.json()
    if data.get("done_reason") == "length":
        raise RetryableLLMError("Ollama's answer was cut off; raise LLM_MAX_TOKENS or OLLAMA_NUM_CTX")
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
        raise RetryableLLMError("Claude authentication failed; set ANTHROPIC_API_KEY in .env") from e
    except anthropic.RateLimitError as e:
        raise RetryableLLMError("Claude rate limit reached") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude API error {e.status_code}: {e.message} (request id: {e.request_id})") from e
    except anthropic.APIConnectionError as e:
        raise RetryableLLMError("could not reach the Claude API") from e
    except anthropic.AnthropicError as e:
        raise LLMError(f"Claude client error: {e}") from e
    if response.stop_reason == "refusal":
        raise LLMError("The model declined to review this text.")
    if response.stop_reason == "max_tokens":
        raise RetryableLLMError("Claude's answer was cut off; increase CLAUDE_MAX_TOKENS")
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
        print(f"\n== {s['name']} ({role}), selected model: {s['model']}")
        try:
            if s["transport"] == "ollama":
                names = [m["name"] for m in httpx.get(f"{s['base_url']}/api/tags", timeout=10).json().get("models", [])]
            elif s["transport"] == "openai":
                if not s["api_key"]:
                    print(f"   (no key: set {s['key_env']} in .env)")
                    continue
                resp = httpx.get(f"{s['base_url']}/models", headers={"Authorization": f"Bearer {s['api_key']}"},
                                 timeout=30)
                _raise_for(s, resp)
                names = sorted(m["id"].removeprefix("models/") for m in resp.json().get("data", []))
            else:
                print("   (listing not supported for anthropic)")
                continue
        except (LLMError, httpx.HTTPError) as e:
            print(f"   error: {e}")
            continue
        for n in names:
            print(("  * " if n == s["model"] else "    ") + n)


def _smoke_test() -> None:
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}, "word": {"type": "string"}},
              "required": ["ok", "word"], "additionalProperties": False}
    for s in _configured():
        role = "primary" if s is config.PRIMARY else "fallback"
        t = time.time()
        try:
            out = _call(s, "You are a test endpoint.", 'Return ok=true and word="essay".', schema)
            print(f"[ok]   {role:8} {s['name']}:{s['model']} answered in {time.time() - t:.1f}s -> {out}")
        except LLMError as e:
            print(f"[fail] {role:8} {s['name']}:{s['model']}: {e}")


if __name__ == "__main__":
    if config.MOCK_LLM:
        sys.exit("MOCK_LLM=1 is set in .env; set it to 0 to test real providers.")
    _list_models() if (sys.argv[1:] or ["test"])[0] == "models" else _smoke_test()
