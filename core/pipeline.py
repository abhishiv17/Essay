"""End-to-end: essay text -> verified feedback report (dict)."""
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config, llm
from .llm import LLMError, generate_json
from .preprocess import prepare
from .prompts import PRACTICE_SYSTEM_PROMPT, SYSTEM_PROMPT, build_practice_prompt, build_user_prompt
from .rubric import ARGUMENT_KEYS, CRITERION_KEYS, SCORE_MAX, SCORE_MIN
from .schema import FEEDBACK_SCHEMA, PRACTICE_SCHEMA
from .verify import verify_feedback

PIPELINE_VERSION = "3"  # bump to invalidate the cache after prompt/schema changes


@dataclass
class FeedbackOptions:
    grade_level: str = "High school (Grades 9-12)"
    essay_type: str = "Argumentative"
    assignment_prompt: str = ""


def _clamp(score) -> int:
    try:
        return max(SCORE_MIN, min(SCORE_MAX, int(score)))
    except (TypeError, ValueError):
        return SCORE_MIN


_ITEM_DEFAULTS = {
    "strengths": {"quote": "", "comment": ""},
    "improvements": {"quote": "", "issue": "", "suggestion": "", "example_rewrite": ""},
    "grammar_errors": {"quote": "", "correction": "", "error_type": "grammar", "explanation": ""},
}


def _items(items, kind: str) -> list[dict]:
    """Keep dict items and fill any fields a smaller model left out."""
    defaults = _ITEM_DEFAULTS[kind]
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict):
            out.append({**defaults, **{k: ("" if v is None else v) for k, v in it.items()}})
    return out


def _strings(items) -> list[str]:
    return [str(x) for x in items if x] if isinstance(items, list) else []


def _tidy(feedback: dict) -> dict:
    """Make any model's output safe for the UI: fill missing fields, clamp scores, fix ordering.

    Claude/Gemini with strict schemas rarely need this; small local or free models sometimes do.
    """
    if isinstance(feedback, list):  # some models wrap the object in a list
        feedback = next((x for x in feedback if isinstance(x, dict)), {})
    if not isinstance(feedback, dict) or not feedback.get("criteria"):
        raise LLMError("The model returned an incomplete report. Please try again.")
    feedback["overall_score"] = _clamp(feedback.get("overall_score"))
    for key in ("overall_summary", "next_step_exercise"):
        feedback[key] = str(feedback.get(key) or "")
    for key in ("top_strengths", "top_priorities"):
        feedback[key] = _strings(feedback.get(key))

    by_key = {}
    for crit in feedback.get("criteria") or []:
        if isinstance(crit, dict) and crit.get("criterion") in CRITERION_KEYS and crit["criterion"] not in by_key:
            by_key[crit["criterion"]] = {
                "criterion": crit["criterion"],
                "score": _clamp(crit.get("score", feedback["overall_score"])),
                "summary": str(crit.get("summary") or ""),
                "strengths": _items(crit.get("strengths"), "strengths"),
                "improvements": _items(crit.get("improvements"), "improvements"),
            }
    feedback["criteria"] = [
        by_key.get(k) or {"criterion": k, "score": feedback["overall_score"], "summary": "",
                          "strengths": [], "improvements": []}
        for k in CRITERION_KEYS
    ]
    feedback["grammar_errors"] = _items(feedback.get("grammar_errors"), "grammar_errors")

    elements = {e.get("element"): e for e in feedback.get("argument_structure") or [] if isinstance(e, dict)}
    feedback["argument_structure"] = [
        {"element": k, "present": bool(elements.get(k, {}).get("present")), "quote": str(elements.get(k, {}).get("quote") or "")}
        for k in ARGUMENT_KEYS
    ]
    return feedback


def _cache_key(text: str, options: FeedbackOptions) -> str:
    payload = json.dumps(
        [PIPELINE_VERSION, config.MODEL_LABEL, config.REASONING_EFFORT, text, asdict(options)]
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def generate_feedback(
    raw_text: str,
    options: FeedbackOptions | None = None,
    use_cache: bool | None = None,
    cache_dir: Path | None = None,
) -> dict:
    """cache_dir overrides where results are cached (eval runs use eval/cache so dataset essays stay out of git)."""
    options = options or FeedbackOptions()
    use_cache = config.USE_CACHE if use_cache is None else use_cache
    essay = prepare(raw_text)

    name = f"{_cache_key(essay.text, options)}.json"
    cache_file = (cache_dir or config.CACHE_DIR) / name
    if use_cache:
        for cached in (cache_file, config.DEMO_CACHE_DIR / name):
            if cached.exists():
                result = json.loads(cached.read_text(encoding="utf-8"))
                result["from_cache"] = True
                return result

    prompt = build_user_prompt(essay, options.grade_level, options.essay_type, options.assignment_prompt)
    feedback = _tidy(generate_json(SYSTEM_PROMPT, prompt, FEEDBACK_SCHEMA))
    # Mock output was written for one sample essay, so keep its items (flagged) on other essays.
    feedback, verification = verify_feedback(feedback, essay.text, drop_unverified=not config.MOCK_LLM)

    result = {
        "essay": essay.text,
        "stats": essay.stats,
        "options": asdict(options),
        "feedback": feedback,
        "verification": verification,
        "model": llm.last_used or config.MODEL_LABEL,  # which provider actually answered
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "from_cache": False,
    }
    if use_cache:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


MOCK_PRACTICE = {
    "verdict": "getting_there",
    "feedback": "Good start: your new version fixes the verb so it agrees with its subject. "
                "The sentence still reads a little general, so the reader can't picture what you mean yet.",
    "next_tip": "Add one concrete detail, such as a specific example from your own school.",
}


def check_practice(task: str, original: str, attempt: str, grade_level: str) -> dict:
    """Short feedback on a student's practice rewrite. Not cached: every attempt is new."""
    if config.MOCK_LLM:
        return {**MOCK_PRACTICE, "model": "mock"}
    out = generate_json(PRACTICE_SYSTEM_PROMPT, build_practice_prompt(task, original, attempt, grade_level),
                        PRACTICE_SCHEMA)
    verdict = out.get("verdict") if out.get("verdict") in ("improved", "getting_there", "not_yet") else "getting_there"
    return {"verdict": verdict, "feedback": str(out.get("feedback") or ""), "next_tip": str(out.get("next_tip") or ""),
            "model": llm.last_used}
