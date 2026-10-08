"""Structural flaw types used in synthetic essays, and how we detect that feedback caught them.

A flaw counts as detected if an improvement (issue or suggestion) under one of the listed criteria
mentions one of the keywords. Keyword matching is deliberately simple and transparent, so
run_eval also reports a false-alarm rate (the flaw "detected" in essays that don't have it).
Review misses by hand: eval/results/synthetic.md lists them.
"""

FLAWS = {
    "missing_counterargument": {
        "instruction": "Never mention or respond to any opposing view; argue only one side.",
        "criteria": ["argument"],
        "keywords": ["counterargument", "counter-argument", "counterclaim", "opposing", "other side",
                     "rebut", "objection", "critics", "opponents", "disagree"],
    },
    "missing_evidence": {
        "instruction": "Make claims with no examples, data or reasons to back them up; just assert them.",
        "criteria": ["argument"],
        "keywords": ["evidence", "unsupported", "back up", "data", "statistic", "proof", "specific example"],
    },
    "weak_thesis": {
        "instruction": "Do not state a clear position anywhere; stay vague about what you actually believe.",
        "criteria": ["argument", "coherence"],
        "keywords": ["thesis", "stance", "central claim", "main claim", "clear position", "your position"],
    },
    "no_conclusion": {
        "instruction": "End abruptly after the last body paragraph, with no concluding paragraph.",
        "criteria": ["coherence"],
        "keywords": ["conclusion", "concluding", "ends abruptly", "abrupt", "wrap up", "closing paragraph"],
    },
    "missing_transitions": {
        "instruction": "Use no transition words or phrases between sentences or paragraphs.",
        "criteria": ["coherence"],
        "keywords": ["transition", "choppy", "linking word", "connecting word", "signpost"],
    },
    "off_topic_paragraph": {
        "instruction": "Include one body paragraph that drifts to a loosely related but off-topic subject.",
        "criteria": ["coherence", "argument"],
        "keywords": ["off-topic", "off topic", "tangent", "unrelated", "irrelevant", "drift", "digress", "strays"],
    },
    "cliche": {
        "instruction": "Open and close with stock phrases such as \"in today's world\" and \"only time will tell\".",
        "criteria": ["originality"],
        "keywords": ["clich", "generic", "overused", "stock phrase", "predictable", "formulaic", "filler"],
    },
}


def flaw_detected(flaw: str, feedback: dict) -> bool:
    spec = FLAWS[flaw]
    texts = []
    for c in feedback.get("criteria", []):
        if c["criterion"] in spec["criteria"]:
            for i in c.get("improvements", []):
                texts += [i.get("issue", ""), i.get("suggestion", "")]
    blob = " ".join(texts).lower()
    return any(k in blob for k in spec["keywords"])
