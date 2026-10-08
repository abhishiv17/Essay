"""Loaders for the public evaluation datasets (see data/DATASETS.md).

Run `python data/prepare_datasets.py` first to unpack the Kaggle zips into the paths below.
Column names are matched case-insensitively against candidates, so the loaders also work with the
original GitHub releases and the Kaggle competition versions. If a column can't be found, the
error lists the columns that do exist.
"""
import csv
import sys
from pathlib import Path

# Essays can be long; the default CSV field limit (128 KB) is too small for some rows.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

DEFAULT_PATHS = {
    "ellipse": RAW / "ellipse_train.csv",
    "persuade": RAW / "persuade_2.0" / "persuade_2.0_human_scores_demo_id_github.csv",
    "persuade_elements": RAW / "persuade_2.0" / "discourse_summary.csv",
    "asap": RAW / "asap_2.0" / "ASAP2_train_sourcetexts.csv",
}

_ID = ["text_id_kaggle", "text_id", "essay_id_comp", "essay_id", "id"]
_TEXT = ["full_text", "text", "essay"]
_HOLISTIC = ["holistic_essay_score", "score", "holistic_score"]

# PERSUADE discourse types -> our argument element keys (core/rubric.py ARGUMENT_ELEMENTS)
PERSUADE_ELEMENTS = {
    "Lead": "lead", "Position": "position", "Claim": "claim", "Counterclaim": "counterclaim",
    "Rebuttal": "rebuttal", "Evidence": "evidence", "Concluding Statement": "concluding_statement",
}


def _read(path: Path) -> tuple[list[dict], dict[str, str]]:
    if not path.exists():
        sys.exit(f"{path} not found. Put the downloads in data/raw/ and run: python data/prepare_datasets.py "
                 f"(see data/DATASETS.md)")
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f"{path} is empty.")
    lower = {name.lower(): name for name in rows[0]}
    return rows, lower


def _col(lower: dict[str, str], candidates: list[str], path: Path, what: str, required: bool = True) -> str | None:
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    if required:
        sys.exit(f"{path.name}: no {what} column (tried {candidates}). Columns present: {list(lower.values())}")
    return None


def _level(grade: str, ell: str) -> str:
    """Map dataset demographics onto the student-level options our UI offers."""
    if ell.strip().lower() == "yes":
        return "English language learner"
    try:
        return "Middle school (Grades 6-8)" if int(float(grade)) <= 8 else "High school (Grades 9-12)"
    except ValueError:
        return "High school (Grades 9-12)"


def load_ellipse(path: Path | None = None) -> list[dict]:
    """ELLIPSE: analytic scores 1.0-5.0 (0.5 steps) for Cohesion, Grammar, etc.

    Works with the GitHub/Kaggle corpus file (ELLIPSE_Final_github*.csv) and with the
    Kaggle competition train.csv (lowercase columns, no Overall).
    """
    path = path or DEFAULT_PATHS["ellipse"]
    rows, lower = _read(path)
    id_c, text_c = _col(lower, _ID, path, "id"), _col(lower, _TEXT, path, "text")
    traits = {k: _col(lower, [k], path, f"'{k}' score")
              for k in ["cohesion", "syntax", "vocabulary", "phraseology", "grammar", "conventions"]}
    # The Kaggle competition version (Feedback Prize - English Language Learning) has no Overall column.
    overall_c = _col(lower, ["overall"], path, "overall", required=False)
    if overall_c:
        traits["overall"] = overall_c
    set_c = _col(lower, ["set"], path, "set", required=False)
    out = []
    for r in rows:
        if set_c and r[set_c].strip().lower() not in {"train", ""}:
            continue  # the Kaggle mirror bundles the test split too; evaluate on train only
        try:
            scores = {k: float(r[c]) for k, c in traits.items()}
        except ValueError:
            continue
        out.append({"id": r[id_c], "text": r[text_c], "scores": scores})
    return out


def load_holistic(name: str, path: Path | None = None, task: str = "all") -> list[dict]:
    """PERSUADE 2.0 / ASAP 2.0: one holistic score 1-6 per essay.

    task: "independent" keeps only essays written without a source article (PERSUADE only;
    every ASAP 2.0 essay is source-based), "all" keeps everything.
    """
    path = path or DEFAULT_PATHS[name]
    rows, lower = _read(path)
    id_c, text_c = _col(lower, _ID, path, "id"), _col(lower, _TEXT, path, "text")
    score_c = _col(lower, _HOLISTIC, path, "holistic score")
    prompt_c = _col(lower, ["prompt_name", "prompt"], path, "prompt", required=False)
    assign_c = _col(lower, ["assignment"], path, "assignment", required=False)
    task_c = _col(lower, ["task"], path, "task", required=False)
    grade_c = _col(lower, ["grade_level", "grade"], path, "grade", required=False)
    ell_c = _col(lower, ["ell_status"], path, "ell status", required=False)

    out, seen = [], set()
    for r in rows:
        essay_id = r[id_c]
        if essay_id in seen:  # PERSUADE 2.0 has a few duplicate ids
            continue
        seen.add(essay_id)
        essay_task = r[task_c].strip() if task_c else "Text dependent"
        if task == "independent" and essay_task != "Independent":
            continue
        try:
            score = int(float(r[score_c]))
        except ValueError:
            continue
        out.append({
            "id": essay_id,
            "text": r[text_c],
            "score": score,
            "prompt": r[prompt_c] if prompt_c else "",
            "assignment": r[assign_c] if assign_c else "",
            "task": essay_task,
            "level": _level(r[grade_c] if grade_c else "", r[ell_c] if ell_c else ""),
        })
    return out


def load_persuade_with_elements(task: str = "independent") -> list[dict]:
    """PERSUADE 2.0 essays joined with expert argument-element annotations.

    Adds "elements": {our_key: True/False} (was the element annotated at least once).
    Needs data/raw/persuade_2.0/discourse_summary.csv from data/prepare_datasets.py.
    """
    path = DEFAULT_PATHS["persuade_elements"]
    if not path.exists():
        sys.exit(f"{path} not found. Run: python data/prepare_datasets.py (needs persuade_corpus_1.0.csv "
                 f"from the PERSUADE Kaggle download)")
    with path.open(encoding="utf-8", newline="") as f:
        summary = {r["essay_id_comp"]: r for r in csv.DictReader(f)}
    out = []
    for e in load_holistic("persuade", task=task):
        counts = summary.get(e["id"])
        if counts is None:
            continue
        e["elements"] = {key: int(counts[name]) > 0 for name, key in PERSUADE_ELEMENTS.items()}
        out.append(e)
    return out
