"""Feedback criteria: the single source of truth used by prompts, UI and docs.

Keep docs/FEEDBACK_CRITERIA.md in sync when editing this file.
"""

SCORE_MIN, SCORE_MAX = 1, 5

CRITERIA = {
    "grammar": {
        "label": "Grammar & Mechanics",
        "question": "Is the writing correct and easy to read at the sentence level?",
        "look_for": [
            "spelling, punctuation and capitalization",
            "subject-verb agreement, tense consistency, articles, prepositions",
            "sentence boundaries (run-ons, fragments, comma splices)",
            "word choice and idiomatic phrasing",
        ],
        "levels": {
            5: "Virtually error-free; varied, controlled sentences.",
            4: "Minor errors that never obscure meaning.",
            3: "Noticeable patterns of error; meaning still clear.",
            2: "Frequent errors that sometimes obscure meaning.",
            1: "Errors make large parts hard to understand.",
        },
    },
    "coherence": {
        "label": "Coherence & Organization",
        "question": "Does the essay flow logically from start to finish?",
        "look_for": [
            "clear introduction, body and conclusion",
            "one main idea per paragraph, with topic sentences",
            "transitions between sentences and paragraphs",
            "logical ordering; no repetition or tangents",
        ],
        "levels": {
            5: "Purposeful structure; seamless transitions; every paragraph earns its place.",
            4: "Clear structure with minor lapses in flow.",
            3: "Basic structure present; transitions mechanical or missing in places.",
            2: "Weak structure; ideas jump around or repeat.",
            1: "No discernible organization.",
        },
    },
    "argument": {
        "label": "Argument Strength",
        "question": "Does the essay make and support a convincing point?",
        "look_for": [
            "a clear, specific thesis or central claim",
            "claims supported by evidence, examples or reasoning",
            "explanation of how evidence supports the claim",
            "acknowledgement and rebuttal of counterarguments",
            "logical fallacies or unsupported generalizations",
        ],
        "levels": {
            5: "Precise thesis; well-chosen evidence, fully explained; counterarguments handled.",
            4: "Clear thesis; mostly supported; some explanation gaps.",
            3: "Position is identifiable but support is thin or generic.",
            2: "Vague position; mostly assertion without support.",
            1: "No identifiable position or support.",
        },
    },
    "originality": {
        "label": "Originality & Voice",
        "question": "Does the writer bring their own thinking and voice?",
        "look_for": [
            "fresh angles or personal insight rather than predictable points",
            "specific, concrete details rather than generic statements",
            "cliches and filler phrases ('in today's world', 'double-edged sword')",
            "a consistent, engaged authorial voice",
        ],
        "levels": {
            5: "Distinctive perspective and voice; concrete, surprising details.",
            4: "Some original insight; mostly specific.",
            3: "Competent but predictable; some cliches.",
            2: "Largely generic or formulaic.",
            1: "Entirely cliche or copied-sounding.",
        },
        "note": "This measures originality of ideas and expression. It is NOT plagiarism detection.",
    },
}

CRITERION_KEYS = list(CRITERIA)


def rubric_as_text() -> str:
    """Render the rubric for inclusion in the prompt."""
    lines = [f"Score each criterion from {SCORE_MIN} (weakest) to {SCORE_MAX} (strongest)."]
    for key, c in CRITERIA.items():
        lines.append(f"\n## {key} - {c['label']}")
        lines.append(c["question"])
        lines.append("Look for: " + "; ".join(c["look_for"]) + ".")
        for score, desc in sorted(c["levels"].items(), reverse=True):
            lines.append(f"  {score}: {desc}")
        if c.get("note"):
            lines.append(f"Note: {c['note']}")
    return "\n".join(lines)


# Argument elements, defined as in the PERSUADE 2.0 annotation scheme (Crossley et al., 2024), so the
# model's argument-structure checklist can be compared directly with expert annotations.
ARGUMENT_ELEMENTS = {
    "lead": ("Lead", "An introduction that begins with a statistic, quotation, description or other device to "
                     "grab the reader's attention and point toward the thesis."),
    "position": ("Position", "An opinion or conclusion on the main question (the thesis)."),
    "claim": ("Claim", "A claim that supports the position."),
    "counterclaim": ("Counterclaim", "A claim that refutes another claim or gives an opposing reason to the position."),
    "rebuttal": ("Rebuttal", "A claim that refutes a counterclaim."),
    "evidence": ("Evidence", "Ideas or examples that support claims, counterclaims, rebuttals or the position."),
    "concluding_statement": ("Concluding Statement", "A concluding statement that restates the position and claims."),
}
ARGUMENT_KEYS = list(ARGUMENT_ELEMENTS)


def argument_elements_as_text() -> str:
    return "\n".join(f"- {key}: {desc}" for key, (_, desc) in ARGUMENT_ELEMENTS.items())
