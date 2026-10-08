"""Export a feedback result as a Markdown report (for download / sharing with the student)."""
from .rubric import ARGUMENT_ELEMENTS, CRITERIA, SCORE_MAX


def to_markdown(result: dict) -> str:
    fb = result["feedback"]
    opts = result["options"]
    out = [
        "# Essay Feedback Report",
        f"*{opts['essay_type']} essay - {opts['grade_level']} - generated {result['generated_at']}*",
        "",
        f"## Overall: {fb['overall_score']}/{SCORE_MAX}",
        fb["overall_summary"],
        "",
        "| Criterion | Score |",
        "|---|---|",
    ]
    out += [f"| {CRITERIA[c['criterion']]['label']} | {c['score']}/{SCORE_MAX} |" for c in fb["criteria"]]

    out += ["", "### What you did well"] + [f"- {s}" for s in fb["top_strengths"]]
    out += ["", "### Focus on next"] + [f"{i}. {p}" for i, p in enumerate(fb["top_priorities"], 1)]
    out += ["", "### Practice exercise", fb["next_step_exercise"], ""]

    if fb.get("argument_structure") and opts["essay_type"] not in ("Narrative", "Descriptive"):
        out += ["### Argument structure checklist"]
        for el in fb["argument_structure"]:
            label = ARGUMENT_ELEMENTS[el["element"]][0]
            mark = "[x]" if el["present"] else "[ ]"
            quote = f' - "{el["quote"]}"' if el["present"] and el["quote"] else ""
            out.append(f"- {mark} {label}{quote}")
        out.append("")

    for crit in fb["criteria"]:
        out += [f"## {CRITERIA[crit['criterion']]['label']} ({crit['score']}/{SCORE_MAX})", crit["summary"], ""]
        if crit["strengths"]:
            out.append("**Strengths**")
            for s in crit["strengths"]:
                quote = f'> "{s["quote"]}"\n\n' if s["quote"] else ""
                out.append(f"{quote}- {s['comment']}\n")
        if crit["improvements"]:
            out.append("**To improve**")
            for imp in crit["improvements"]:
                if imp["quote"]:
                    out.append(f'> "{imp["quote"]}"\n')
                out.append(f"- **Issue:** {imp['issue']}")
                out.append(f"- **Try:** {imp['suggestion']}")
                if imp["example_rewrite"]:
                    out.append(f"- **Example:** *{imp['example_rewrite']}*")
                out.append("")

    if fb["grammar_errors"]:
        out += ["## Grammar & mechanics corrections", "", "| Original | Correction | Why |", "|---|---|---|"]
        for e in fb["grammar_errors"]:
            out.append(f"| {e['quote']} | {e['correction']} | {e['explanation']} |")

    return "\n".join(out) + "\n"
