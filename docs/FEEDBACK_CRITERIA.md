# Feedback Criteria

Every essay is scored on four criteria, each from **1 (weakest) to 5 (strongest)**, plus a holistic overall score.
The rubric lives in code at `core/rubric.py` and is sent to the model verbatim, so the scores and comments always follow the same standard. Keep this page in sync with that file.

| Criterion | Question it answers |
|---|---|
| Grammar & Mechanics | Is the writing correct and easy to read at the sentence level? |
| Coherence & Organization | Does the essay flow logically from start to finish? |
| Argument Strength | Does the essay make and support a convincing point? |
| Originality & Voice | Does the writer bring their own thinking and voice? |

## Grammar & Mechanics
**Looks for:** spelling, punctuation, capitalization; subject-verb agreement, tense, articles, prepositions; run-ons, fragments, comma splices; word choice and idiom.

| Score | Descriptor |
|---|---|
| 5 | Virtually error-free; varied, controlled sentences. |
| 4 | Minor errors that never obscure meaning. |
| 3 | Noticeable patterns of error; meaning still clear. |
| 2 | Frequent errors that sometimes obscure meaning. |
| 1 | Errors make large parts hard to understand. |

## Coherence & Organization
**Looks for:** clear introduction/body/conclusion; one main idea per paragraph with topic sentences; transitions; logical order without repetition or tangents.

| Score | Descriptor |
|---|---|
| 5 | Purposeful structure; seamless transitions; every paragraph earns its place. |
| 4 | Clear structure with minor lapses in flow. |
| 3 | Basic structure present; transitions mechanical or missing in places. |
| 2 | Weak structure; ideas jump around or repeat. |
| 1 | No discernible organization. |

## Argument Strength
**Looks for:** a clear, specific thesis; claims backed by evidence, examples or reasoning; explanation of *how* evidence supports the claim; counterarguments and rebuttals; fallacies or unsupported generalizations.

| Score | Descriptor |
|---|---|
| 5 | Precise thesis; well-chosen evidence, fully explained; counterarguments handled. |
| 4 | Clear thesis; mostly supported; some explanation gaps. |
| 3 | Position is identifiable but support is thin or generic. |
| 2 | Vague position; mostly assertion without support. |
| 1 | No identifiable position or support. |

For narrative and descriptive essays the model treats "argument" as the essay's central purpose or insight and how well the details serve it.

## Originality & Voice
**Looks for:** fresh angles or personal insight; concrete, specific details; cliches and filler ("in today's world", "double-edged sword"); a consistent, engaged voice.

| Score | Descriptor |
|---|---|
| 5 | Distinctive perspective and voice; concrete, surprising details. |
| 4 | Some original insight; mostly specific. |
| 3 | Competent but predictable; some cliches. |
| 2 | Largely generic or formulaic. |
| 1 | Entirely cliche or copied-sounding. |

> Originality here means freshness of ideas and expression. It is **not** plagiarism detection, and the system never accuses students of copying.

## Argument structure checklist

For argumentative and persuasive essays, the report also gives a checklist of the seven parts of a strong argument. Each part is marked present or missing and quoted when present. The definitions come from the **PERSUADE 2.0** annotation scheme, so the checklist can be compared directly with expert annotations (see `data/DATASETS.md`).

| Element | Definition |
|---|---|
| Lead | An introduction that grabs attention (statistic, quotation, description...) and points toward the thesis |
| Position | The writer's opinion on the main question (the thesis) |
| Claim | A reason that supports the position |
| Counterclaim | An opposing view or reason |
| Rebuttal | A response that refutes the counterclaim |
| Evidence | Ideas or examples that support a claim, counterclaim, rebuttal or the position |
| Concluding Statement | A conclusion that restates the position and claims |

Missing elements, especially **Counterclaim** and **Rebuttal**, are the most common gaps: experts found them in only 29% and 23% of PERSUADE essays. That makes them high-value, concrete feedback for students.

## What every feedback item must include

1. **Evidence:** a verbatim quote from the student's essay, or an explicit "whole essay / something missing" note.
2. **The why:** the underlying skill or rule, so the student can apply it next time.
3. **A next step:** a concrete action, and a short model rewrite where useful.

The report also gives the student:
- the **top 3 strengths** and **top 3 priorities**, ranked by impact
- **one practice exercise** aimed at the top priority
- a **corrections table** listing each distinct grammar or mechanics error with a plain-language rule
