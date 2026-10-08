"""Generate synthetic test essays with KNOWN flaws, so we can check that our feedback catches them.

  python -m eval.generate_synthetic            # generate all specs below (skips ones already done)
  python -m eval.generate_synthetic --force    # regenerate everything

The LLM writes each essay to a spec (topic, level, planted grammar errors, structural flaws) and
returns the exact text of every planted error. We keep only planted errors whose quote really
appears in the essay, then save to eval/synthetic_generated.json, which `run_eval synthetic`
picks up automatically alongside the hand-written eval/synthetic_cases.json.
Needs a real model (MOCK_LLM=0). One request per essay (free tier is fine).
"""
import argparse
import json

from core import config
from core.llm import generate_json
from core.schema import ERROR_TYPES
from core.verify import find_span

from .flaws import FLAWS

OUT = config.EVAL_DIR / "synthetic_generated.json"

# 8 specs: together with the 2 hand-written cases this gives 10 synthetic essays,
# covering every flaw type, several levels, and one flawless control essay.
SPECS = [
    {"id": "gen_homework_esl", "topic": "Should homework be optional?", "level": "English language learner",
     "essay_type": "Argumentative", "grammar_errors": 10, "flaws": []},
    {"id": "gen_car_free_downtown", "topic": "Should cities ban private cars from downtown areas?",
     "level": "High school (Grades 9-12)", "essay_type": "Argumentative", "grammar_errors": 5,
     "flaws": ["missing_counterargument"]},
    {"id": "gen_voting_age", "topic": "Should the voting age be lowered to 16?",
     "level": "High school (Grades 9-12)", "essay_type": "Argumentative", "grammar_errors": 0,
     "flaws": ["missing_evidence", "cliche"]},
    {"id": "gen_four_day_week", "topic": "Should schools switch to a four-day week?",
     "level": "Middle school (Grades 6-8)", "essay_type": "Argumentative", "grammar_errors": 8,
     "flaws": ["no_conclusion"]},
    {"id": "gen_ai_creativity", "topic": "Does AI help or hurt human creativity?", "level": "Undergraduate",
     "essay_type": "Argumentative", "grammar_errors": 4, "flaws": ["weak_thesis"]},
    {"id": "gen_uniforms", "topic": "Should students wear school uniforms?", "level": "High school (Grades 9-12)",
     "essay_type": "Argumentative", "grammar_errors": 5, "flaws": ["off_topic_paragraph", "missing_transitions"]},
    {"id": "gen_online_classes", "topic": "Are online classes as good as in-person classes?",
     "level": "English language learner", "essay_type": "Argumentative", "grammar_errors": 8,
     "flaws": ["missing_counterargument", "missing_evidence"]},
    {"id": "gen_free_museums_control", "topic": "Should museums be free to enter?",
     "level": "High school (Grades 9-12)", "essay_type": "Argumentative", "grammar_errors": 0, "flaws": []},
]

SYSTEM = """You create realistic student essays for testing an automated essay-feedback system. \
Each essay must contain exactly the flaws requested, and nothing else that a teacher would flag as a \
major problem, so that we know the ground truth. Write like a real student at the given level, not \
like a professional writer."""

SCHEMA = {
    "type": "object",
    "properties": {
        "essay": {"type": "string", "description": "The full essay, paragraphs separated by a blank line."},
        "planted": {
            "type": "array",
            "description": "Every planted grammar/mechanics error, one entry each.",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string", "description": "2-6 words copied EXACTLY from the essay containing the error; unique in the essay."},
                    "type": {"type": "string", "enum": ERROR_TYPES},
                    "correction": {"type": "string"},
                },
                "required": ["quote", "type", "correction"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["essay", "planted"],
    "additionalProperties": False,
}


def _prompt(spec: dict) -> str:
    flaw_lines = "\n".join(f"- {FLAWS[f]['instruction']}" for f in spec["flaws"]) or \
        "- None. The structure, argument and originality should be solid for this level."
    if spec["grammar_errors"]:
        errors = (f"Plant exactly {spec['grammar_errors']} grammar/mechanics errors typical of this level "
                  f"(mix types: {', '.join(ERROR_TYPES)}). Every other sentence must be correct.")
    else:
        errors = "Plant NO grammar or mechanics errors. The writing must be correct throughout."
    return f"""Write a {spec['essay_type'].lower()} essay of 300-450 words.

Topic: {spec['topic']}
Student level: {spec['level']}

Grammar and mechanics:
{errors}

Structural flaws to build in (and no others):
{flaw_lines}

Return the essay and the list of planted grammar/mechanics errors (empty list if none). Each quote must
be copied character-for-character from the essay and must not appear anywhere else in it."""


def generate(spec: dict) -> dict:
    data = generate_json(SYSTEM, _prompt(spec), SCHEMA, mock_ok=False)
    essay = data["essay"].strip()
    kept, dropped = [], []
    for p in data["planted"]:
        (kept if find_span(p["quote"], essay) else dropped).append(p)
    if dropped:
        print(f"  dropped {len(dropped)} planted errors whose quote wasn't found: {[p['quote'] for p in dropped]}")
    return {
        "id": spec["id"],
        "source": "generated",
        "grade_level": spec["level"],
        "essay_type": spec["essay_type"],
        "essay": essay,
        "planted": [{"quote": p["quote"], "type": p["type"], "correction": p["correction"]} for p in kept],
        "flaws": spec["flaws"],
        "control": not spec["flaws"] and not spec["grammar_errors"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="regenerate essays that already exist")
    args = parser.parse_args()

    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    done = {c["id"] for c in existing} if not args.force else set()
    cases = [c for c in existing if c["id"] in done]
    for spec in SPECS:
        if spec["id"] in done:
            print(f"[skip] {spec['id']} (already generated)")
            continue
        print(f"[gen]  {spec['id']}: {spec['topic']}")
        cases.append(generate(spec))
        OUT.write_text(json.dumps(cases, indent=2), encoding="utf-8")  # save after each, so a failure loses nothing
    print(f"{len(cases)} generated cases in {OUT}. Review them by eye before trusting the eval numbers.")


if __name__ == "__main__":
    main()
