"""Text normalization, segmentation and surface statistics."""
import re
import unicodedata
from dataclasses import dataclass, field

from . import config

_CHAR_MAP = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": " - ", "\u2026": "...",
    "\u00a0": " ", "\u200b": "",
})

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")
_WORD = re.compile(r"[A-Za-z0-9']+")
_VOWEL_GROUPS = re.compile(r"[aeiouy]+")
LONG_SENTENCE_WORDS = 35


@dataclass
class PreparedEssay:
    text: str
    paragraphs: list[str]
    sentences: list[str]
    stats: dict = field(default_factory=dict)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_CHAR_MAP)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # Essays pasted with single newlines between paragraphs
    if len(paragraphs) == 1 and "\n" in text:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return paragraphs


def split_sentences(paragraph: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(paragraph) if s.strip()]


def count_syllables(word: str) -> int:
    """Heuristic syllable count (good enough for Flesch scores)."""
    word = word.lower().strip("'")
    if len(word) <= 3:
        return 1
    if word.endswith("e") and not word.endswith(("le", "ee")):
        word = word[:-1]
    return max(1, len(_VOWEL_GROUPS.findall(word)))


def compute_stats(text: str, paragraphs: list[str], sentences: list[str]) -> dict:
    words = _WORD.findall(text)
    sentence_lengths = [len(_WORD.findall(s)) for s in sentences] or [0]
    unique = {w.lower() for w in words}
    n_words, n_sents = max(len(words), 1), max(len(sentences), 1)
    syllables_per_word = sum(count_syllables(w) for w in words) / n_words
    words_per_sentence = n_words / n_sents
    return {
        "words": len(words),
        "sentences": len(sentences),
        "paragraphs": len(paragraphs),
        "avg_sentence_length": round(sum(sentence_lengths) / max(len(sentences), 1), 1),
        "long_sentences": sum(1 for n in sentence_lengths if n > LONG_SENTENCE_WORDS),
        "lexical_diversity": round(len(unique) / max(len(words), 1), 2),
        "flesch_reading_ease": round(206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word, 1),
        "grade_level": round(0.39 * words_per_sentence + 11.8 * syllables_per_word - 15.59, 1),
    }


def prepare(raw_text: str) -> PreparedEssay:
    text = normalize(raw_text)
    paragraphs = split_paragraphs(text)
    sentences = [s for p in paragraphs for s in split_sentences(p)]
    stats = compute_stats(text, paragraphs, sentences)
    if stats["words"] < config.MIN_WORDS:
        raise ValueError(f"Essay is too short ({stats['words']} words). Minimum is {config.MIN_WORDS}.")
    if stats["words"] > config.MAX_WORDS:
        raise ValueError(f"Essay is too long ({stats['words']} words). Maximum is {config.MAX_WORDS}.")
    return PreparedEssay(text="\n\n".join(paragraphs), paragraphs=paragraphs, sentences=sentences, stats=stats)
