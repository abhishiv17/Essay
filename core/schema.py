"""JSON schema the model must return (enforced via structured outputs)."""
from .rubric import ARGUMENT_KEYS, CRITERION_KEYS, SCORE_MAX, SCORE_MIN

_QUOTE_DESC = (
    "Exact, verbatim excerpt copied from the essay (a phrase or one sentence). "
    "Use an empty string only when the point concerns the essay as a whole or something missing."
)

_strength = {
    "type": "object",
    "properties": {
        "quote": {"type": "string", "description": _QUOTE_DESC},
        "comment": {"type": "string", "description": "Why this works, so the student can repeat it."},
    },
    "required": ["quote", "comment"],
    "additionalProperties": False,
}

_improvement = {
    "type": "object",
    "properties": {
        "quote": {"type": "string", "description": _QUOTE_DESC},
        "issue": {"type": "string", "description": "What the problem is and why it matters to the reader."},
        "suggestion": {"type": "string", "description": "A concrete, actionable step to fix it."},
        "example_rewrite": {
            "type": "string",
            "description": "A short model rewrite of the quoted text, or empty string if not applicable.",
        },
    },
    "required": ["quote", "issue", "suggestion", "example_rewrite"],
    "additionalProperties": False,
}

_criterion = {
    "type": "object",
    "properties": {
        "criterion": {"type": "string", "enum": CRITERION_KEYS},
        "score": {"type": "integer", "description": f"Integer from {SCORE_MIN} to {SCORE_MAX}."},
        "summary": {"type": "string", "description": "Two or three sentences on this criterion."},
        "strengths": {"type": "array", "items": _strength},
        "improvements": {"type": "array", "items": _improvement},
    },
    "required": ["criterion", "score", "summary", "strengths", "improvements"],
    "additionalProperties": False,
}

ERROR_TYPES = ["spelling", "grammar", "punctuation", "capitalization", "word_choice", "sentence_structure"]

_error = {
    "type": "object",
    "properties": {
        "quote": {"type": "string", "description": "The exact erroneous text copied from the essay (short)."},
        "correction": {"type": "string", "description": "The corrected version of the quoted text."},
        "error_type": {"type": "string", "enum": ERROR_TYPES},
        "explanation": {"type": "string", "description": "The rule, explained simply for the student."},
    },
    "required": ["quote", "correction", "error_type", "explanation"],
    "additionalProperties": False,
}

_element = {
    "type": "object",
    "properties": {
        "element": {"type": "string", "enum": ARGUMENT_KEYS},
        "present": {"type": "boolean", "description": "True only if the essay actually contains this element."},
        "quote": {"type": "string", "description": "Verbatim excerpt showing the element; empty string if absent."},
    },
    "required": ["element", "present", "quote"],
    "additionalProperties": False,
}

FEEDBACK_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "integer", "description": f"Holistic score, {SCORE_MIN} to {SCORE_MAX}."},
        "overall_summary": {"type": "string", "description": "Three or four encouraging, honest sentences."},
        "top_strengths": {"type": "array", "items": {"type": "string"}, "description": "Up to 3."},
        "top_priorities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Up to 3 highest-impact things to work on next, most important first.",
        },
        "next_step_exercise": {
            "type": "string",
            "description": "One small, specific practice task targeting the top priority.",
        },
        "criteria": {"type": "array", "items": _criterion, "description": "Exactly one entry per criterion."},
        "grammar_errors": {"type": "array", "items": _error},
        "argument_structure": {
            "type": "array",
            "items": _element,
            "description": "Exactly one entry per argument element, in the order given.",
        },
    },
    "required": [
        "overall_score",
        "overall_summary",
        "top_strengths",
        "top_priorities",
        "next_step_exercise",
        "criteria",
        "grammar_errors",
        "argument_structure",
    ],
    "additionalProperties": False,
}
