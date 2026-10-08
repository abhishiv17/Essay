# 3-minute demo script

The app is built so this demo runs smoothly. All four sample essays have **saved real reports** in `data/cache/` (generated live with Groq), so they open instantly and never depend on the free-tier quota during the demo.

**Before you start:**
- Open the deployed URL (or run `uvicorn app:app` locally).
- Use a normal browser window, zoomed to about 110%.
- Have `docs/AI_APPROACH.md` open in another tab for the architecture slide.

| Time | Do this | Say (roughly) |
|---|---|---|
| 0:00–0:15 | Landing page | "Teachers spend hours writing feedback on grammar, coherence, argument and originality, so students wait and get less of it. Existing tools mostly fix surface grammar." |
| 0:15–0:30 | **Try a Sample Essay**, then *English learner, many errors*. Show the essay box and the optional context (type, level, assignment prompt). | "You paste an essay; context is optional but makes the feedback specific to the assignment and level." |
| 0:30–0:45 | **Generate Feedback**. The pipeline steps run. | "It normalizes and segments the text, runs one rubric-guided AI analysis of all four criteria, then verifies every quote against the essay." |
| 0:45–1:20 | The **Feedback report**: overall score and summary, then the **four criteria** with scores, then *What you're doing well* and *Areas for improvement*. | "The four criteria are exactly the ones in the brief. Each improvement follows evidence, why it matters, what to do next, plus a suggested revision." |
| 1:20–1:50 | Click a quoted sentence in an improvement: the essay panel scrolls to it and highlights it. Click a red highlight in the essay: the Grammar section opens at that correction. | "Every comment is tied to the student's exact words, and quotes that can't be found are removed. This is analysis of this essay, not generic advice." |
| 1:50–2:15 | Open **Grammar & Mechanics**: most common pattern, corrections with the rule; toggle **Try it yourself**. Open **Argument Strength**: the argument map, then select *Rebuttal*. | "It teaches rather than just corrects: patterns, rules, and what each part of an argument is for." |
| 2:15–2:35 | **Samples** → *Clean but generic* → Generate. Point at grammar vs argument and originality. Optionally *Personal narrative*: the argument criterion is judged as purpose, with no penalty for lacking a thesis. | "Different essays get meaningfully different feedback. Clean grammar doesn't hide weak ideas, and narrative writing is judged as narrative." |
| 2:35–2:50 | Scroll to **How accurate is this feedback?** (or nav → **Evaluation**). | "These are measured, not claimed: planted-error detection, argument structure against PERSUADE expert annotations, score agreement with ELLIPSE human raters, and quote grounding." |
| 2:50–3:00 | **Print report**, or show the architecture diagram in `docs/AI_APPROACH.md`. | "We don't just correct essays. We automate detailed, constructive feedback that helps students improve while reducing educator workload." |

**Shortcuts:**
- `/?sample=2_esl_grammar_errors` opens a report directly (also `1_strong_argumentative`, `3_generic_cliche`, `4_narrative`).
- If a live analysis is slow or rate-limited, use a sample. Saved reports load instantly.
- To show a live run, paste a new essay. Groq usually answers in about 10 seconds.
