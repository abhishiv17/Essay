"""Hallucination guard: every quoted excerpt must actually appear in the essay."""
import re

_STRIP = " \t\n\"'`"
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|\u2026)\s*")


def _pattern(fragment: str) -> re.Pattern | None:
    tokens = fragment.split()
    if not tokens:
        return None
    return re.compile(r"\s+".join(re.escape(t) for t in tokens), re.IGNORECASE)


def find_span(quote: str, text: str) -> tuple[int, int] | None:
    """Locate a quote in the essay, tolerant of whitespace, case and '...' elisions."""
    quote = quote.strip(_STRIP)
    if not quote:
        return None
    parts = [p for p in _ELLIPSIS.split(quote) if p.strip(_STRIP)]
    start, pos = None, 0
    for part in parts:
        pattern = _pattern(part.strip(_STRIP))
        match = pattern.search(text, pos) if pattern else None
        if match is None:
            # Retry without trailing punctuation the model may have added.
            pattern = _pattern(part.strip(_STRIP + ".,;:!?"))
            match = pattern.search(text, pos) if pattern else None
        if match is None:
            return None
        start = match.start() if start is None else start
        pos = match.end()
    return (start, pos) if start is not None else None


def _check(items: list[dict], text: str, allow_empty: bool) -> tuple[list[dict], int]:
    kept, dropped = [], 0
    for item in items:
        quote = item.get("quote", "").strip(_STRIP)
        if not quote:
            ok = allow_empty
        else:
            ok = find_span(quote, text) is not None
        item["verified"] = ok
        if ok:
            kept.append(item)
        else:
            dropped += 1
    return kept, dropped


def verify_feedback(feedback: dict, text: str, drop_unverified: bool = True) -> tuple[dict, dict]:
    """Mark each quoted item verified/unverified; optionally drop unverified ones.

    Returns the (possibly filtered) feedback and a summary for the UI/eval.
    """
    total = dropped = 0
    for crit in feedback.get("criteria", []):
        for key in ("strengths", "improvements"):
            items = crit.get(key, [])
            kept, n_dropped = _check(items, text, allow_empty=True)
            total += len(items)
            dropped += n_dropped
            if drop_unverified:
                crit[key] = kept

    errors = feedback.get("grammar_errors", [])
    kept, n_dropped = _check(errors, text, allow_empty=False)
    total += len(errors)
    dropped += n_dropped
    if drop_unverified:
        feedback["grammar_errors"] = kept

    # Argument-structure quotes are flagged but never dropped: the present/absent judgment still counts.
    for el in feedback.get("argument_structure", []):
        quote = el.get("quote", "").strip(_STRIP)
        el["verified"] = (find_span(quote, text) is not None) if quote else True

    summary = {
        "items_checked": total,
        "items_unverified": dropped,
        "grounding_rate": round(1 - dropped / total, 3) if total else 1.0,
        "dropped": drop_unverified,
    }
    return feedback, summary
