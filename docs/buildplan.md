# Build Plan: Essay Feedback Coach (6-hour hackathon)

> Read `context.md` first for the what and why. This file covers who does what, when, and what "done" means.
> Times are relative to the start (`H+0:00`). Written for 4 people; for a team of 3, see the "Team of 3" note under section 1.

---

## 0. Where we are at the start

The skeleton is **already built and working in mock mode**: backend, frontend, verifier, eval scripts and docs. We are **not** starting from zero. Today's work is:

1. **Make it real.** Connect the free Groq + Gemini models and get good feedback on real essays.
2. **Make it good.** Tune the prompt until the feedback is accurate, specific and teaches something.
3. **Prove it.** Produce eval numbers that support the 80%+ accuracy and relevance claim.
4. **Ship it.** Live Vercel URL, finished docs, demo video.

---

## 1. Roles and file ownership

Each area has **one owner**, which prevents merge conflicts. Touching someone else's files? Tell them first.

| Role | Person | Owns (files) | Mission |
|---|---|---|---|
| **A: AI / Prompt** | ____ | `core/prompts.py`, `core/schema.py`, `core/rubric.py`, `core/llm.py` | Feedback is accurate, specific, grounded and teaches something |
| **B: Frontend** | ____ | `frontend/*` | UI is clear, polished and works on a phone |
| **C: Eval and Docs** | ____ | `eval/*`, `docs/*`, `data/raw/` | Real numbers for the 80% claim; docs complete |
| **D: Integration, Deploy, Demo** | ____ | `app.py`, `core/pipeline.py`, `vercel.json`, `data/cache/`, `data/sample_essays/`, README | Live URL, reliable demo, video, submission |

**Team of 3:** merge D into C. The eval person also deploys and records the demo, and A helps with the video.

**Shared rule:** if you change the response JSON shape, follow the checklist in `context.md` §5 and tell everyone.

---

## 2. Timeline at a glance

| Time | Phase | Ends with |
|---|---|---|
| H+0:00 – 0:20 | **Kickoff and setup** | Everyone runs the app locally |
| H+0:20 – 1:00 | **Phase 1: First real output** | ✅ **Checkpoint 1:** live Vercel URL + real feedback on all 4 samples |
| H+1:00 – 3:00 | **Phase 2: Quality and evidence** | ✅ **Checkpoint 2:** prompt passes the quality checklist; first eval numbers |
| H+3:00 – 4:30 | **Phase 3: One stretch feature + final evals** | ✅ **Checkpoint 3:** feature done or dropped; final eval numbers in docs |
| **H+4:30** | 🔒 **SCOPE LOCK: no new features after this** | |
| H+4:30 – 5:15 | **Phase 4: Polish, freeze, demo prep** | ✅ Final deploy; demo cache committed |
| H+5:15 – 6:00 | **Phase 5: Record and submit** | ✅ Video + submission done (aim to finish 10 minutes early) |

At each checkpoint, the team takes a **5-minute standup**: what's done, what's blocked, and whether to cut anything.

---

## 3. Kickoff: H+0:00 – 0:20 (everyone)

- [ ] Everyone reads `context.md` (10 minutes, really).
- [ ] D creates the GitHub repo, pushes the skeleton, and adds everyone as collaborators.
- [ ] Everyone clones the repo and sets up the environment:
  ```bash
  python -m venv .venv
  .venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
  pip install -r requirements-dev.txt
  copy .env.example .env          # set MOCK_LLM=1 if you have no key yet
  uvicorn app:app --reload        # http://localhost:8000
  ```
- [ ] **Everyone creates their own free keys** (quotas are per account, so 4 people = 4× the quota):
  - Groq (main): https://console.groq.com/keys → `GROQ_API_KEY`
  - Gemini (backup): https://aistudio.google.com/apikey → `GEMINI_API_KEY`

  Put them in your own `.env` (never in git), then run `python -m core.llm test`. B can also work in mock mode.
- [ ] D keeps one **separate pair of keys for the deployed demo**, so eval runs never use up the demo's quota.
- [ ] Fill in names in the role table above.

**Done when:** every laptop shows the UI, and clicking the "ESL grammar errors" sample then Generate shows a report.

---

## 4. Phase 1: First real output (H+0:20 – 1:00)

### A: AI / Prompt
- [ ] Set `MOCK_LLM=0` with your Groq and Gemini keys, then run all 4 samples through the UI.
- [ ] Note how long each essay takes and which model answered (shown at the bottom of the results).
- [ ] Check the grounding rate in the results footer. If items are being dropped, find out why: the model may be paraphrasing quotes.
- [ ] Write down the 3 worst problems you see in the output (vague comments, wrong scores, missed errors and so on). These are your Phase 2 targets.

### B: Frontend
- [ ] Work in mock mode. Click through every tab, highlight, the download button and the error states (empty essay, too-short essay).
- [ ] Test at phone width in browser devtools (375px) and fix anything broken.
- [ ] List UI improvements for Phase 2, in priority order.

### C: Eval and Docs
- [ ] Read `data/DATASETS.md`.
- [ ] Get the datasets: `python data/download_datasets.py` fetches ELLIPSE. Download the PERSUADE 2.0 and ASAP 2.0 zips from Kaggle into `data/raw/`, then run `python data/prepare_datasets.py`. (Or copy the prepared `data/raw/` folder from the teammate who already has it; it's git-ignored, so use a USB stick or shared drive.)
- [ ] Once A confirms the API works: `python -m eval.generate_synthetic` (8 essays with known flaws), then **read them**. Each should really contain its planted flaws, and the control essay should really be clean.
- [ ] `python -m eval.run_eval synthetic` for a baseline.

### D: Integration and Deploy
- [ ] Import the repo into Vercel and add `GEMINI_API_KEY`, `GROQ_API_KEY` and `APP_ACCESS_CODE` (any password; share it with the team). Use the demo key pair.
- [ ] Deploy and test on the live URL: health, samples, one real feedback run. Check function logs for errors or timeouts.
- [ ] Open the live URL on your phone.

### ✅ Checkpoint 1 (H+1:00)
- Live URL works with a real model call.
- A has real outputs for all 4 samples and a top-3 problem list.
- **If the API is blocked** (key or quota trouble): A keeps tuning against the mock, D escalates, and everyone else continues. Nothing else depends on the API until Phase 2.

---

## 5. Phase 2: Quality and evidence (H+1:00 – 3:00)

### A: Prompt quality (the most important work of the day)

Tune `core/prompts.py` until **every row passes**:

| Sample | Must be true |
|---|---|
| Strong argumentative | Overall 4–5. Strengths name specifics (thesis, rebuttal paragraph, evidence). Improvements are real but minor, not invented. |
| ESL grammar errors | Grammar ≤ 2. Catches most of: agreement, plurals, "more better", "dont", "there/their", "suprised", "must to". Explanations are simple and kind. |
| Generic / cliché | Grammar ≥ 4 (it is clean), **but** originality ≤ 3 and argument ≤ 3. Calls out "double-edged sword", "in today's fast-paced world" and the lack of evidence. |
| Narrative | Doesn't penalize it for lacking a thesis or counterargument. Praises concrete details (the wax "7" candle, 7:42 p.m.). |
| All argumentative | The Argument tab checklist matches what's really in the essay. The ESL essay has a counterclaim ("However technology have also disadvantage") but no real rebuttal. The cliché essay has no lead, no counterclaim and no evidence. |
| All | Grounding rate ≥ 95%. Every improvement has a concrete "Try" step. No generic comments like "add more detail" without saying where. |

Tips:
- Change one thing at a time and re-run. Pass `use_cache: false` in the request, or set `USE_CACHE=0`, while tuning.
- If scores are miscalibrated, add short calibration guidance to the system prompt (for example, "fluent grammar does not imply a strong argument").
- Each time the prompt or schema changes, bump `PIPELINE_VERSION` in `core/pipeline.py` so stale cache entries are ignored.
- Tell C whenever a prompt version is better, so they re-run the evals.

### B: Frontend polish

Pick from this list in order and stop when it's good:
1. Loading state: progress messages are there already; make sure a slow (45s+) response still feels alive.
2. Make the highlighted essay the hero of the demo: smooth click-to-explain, a clear legend.
3. Empty state: a short "how it works" (3 steps) and the 4 criteria with one-line descriptions (from `/api/rubric`).
4. A print-friendly view or nicer Markdown export (optional).
5. Small visual polish: spacing, colors, score colors, favicon.

**Done when:** a first-time user understands the report in 10 seconds, and it looks good at 375px and 1440px.

### C: Evaluation (first pass)
- [ ] `python -m eval.run_eval synthetic`: planted-error recall + structural-flaw recall (check the false-alarm column too).
- [ ] `python -m eval.run_eval ellipse --n 30`: grammar and coherence score agreement.
- [ ] `python -m eval.run_eval argument --n 30`: argument checklist vs PERSUADE expert annotations. **This is our strongest "argument feedback" evidence.**
- [ ] `python -m eval.run_eval holistic --dataset persuade --n 30`: holistic agreement on independent essays (main). Optionally `--dataset asap` as a source-based secondary check. *Free-tier budget: each essay is one request. Groq allows about 1,000 requests a day and about 8,000 tokens a minute (roughly one essay every 40 to 60 seconds at full speed), so a 30-essay run takes 20 to 30 minutes. Gemini models allow as few as 20 a day each. Split eval runs across teammates' keys, and start with `--n 10`. Results are cached in `eval/cache/`, so re-runs are free.*
- [ ] After the samples and ELLIPSE runs have produced cached results: `python -m eval.run_eval relevance-export`, then split the sheet among teammates. Each rates about 25 rows with 1 (relevant and accurate) or 0. Then run `relevance-score`.
- [ ] Share the numbers with A. If a metric is under 80%, find the failure pattern (which error types are missed, which criterion is off).

**Targets:**

| Metric | Target |
|---|---|
| Planted grammar-error recall (synthetic) | ≥ 80% |
| Structural-flaw recall (synthetic), with false alarms low | ≥ 80% |
| Argument-element accuracy vs PERSUADE experts | ≥ 80% |
| Overall score within 1 point of human (PERSUADE independent) | ≥ 70% (1–6 scale is harder) |
| Grammar score within 1 point of human (ELLIPSE) | ≥ 80% |
| Coherence score within 1 point of human (ELLIPSE) | ≥ 80% |
| Feedback items rated relevant | ≥ 80% |
| Grounding rate | ≥ 95% |

If a target isn't met, **report it honestly** along with what you tried. Judges respect real numbers more than claims.

### D: Integration hardening
- [ ] Redeploy after each of A's prompt improvements and smoke-test the live URL.
- [ ] Check the Vercel function logs: duration per request, errors.
- [ ] Find 2–3 more **diverse** essays for the demo (different topics and levels). Add the best one to `data/sample_essays/` if it adds variety.
- [ ] Draft the demo video script (section 9) and pick the essays.

### ✅ Checkpoint 2 (H+3:00)
- The prompt passes the quality checklist (or the remaining gaps are known).
- First eval numbers exist.
- **Decide the stretch feature now**, or decide to skip it.

---

## 6. Phase 3: One stretch feature + final evals (H+3:00 – 4:30)

**Pick at most ONE** at Checkpoint 2. Skip it if the core still has quality problems; quality beats features.

| Feature | Value to judges | Files | Size |
|---|---|---|---|
| **Revision mode:** submit a revised draft and show score changes and which issues were fixed | Shows "student improvement" over time, which the problem statement emphasizes | `frontend/*`, new route in `app.py` (or client-side comparison of two results) | M |
| **Teacher batch mode:** upload several essays (.txt or CSV) and get a class summary of the most common weaknesses | Directly addresses "reduce educator workload" | new `/api/batch` route, new UI section | M–L |
| **Custom rubric:** teacher pastes their own criteria or weights | Flexibility for real classrooms | `core/prompts.py`, `frontend/*` | M |
| **Feedback language toggle:** explanations in Hindi or another language for English learners | Inclusive; strong demo moment | `core/prompts.py` (one option), `frontend/*` (one select) | S |

**Recommended:** the *feedback language toggle* (small and memorable). Add *revision mode* if time allows.

Meanwhile:
- **C:** re-run all evals on the final prompt version. Paste the tables into `docs/AI_APPROACH.md` → "Results". Check that `docs/FEEDBACK_CRITERIA.md` matches `core/rubric.py`.
- **D:** keep the live deploy green and review the README.

### ✅ Checkpoint 3 (H+4:30): 🔒 SCOPE LOCK
- The stretch feature is merged and working, or **cut**. No half-features in the demo.
- From here on: bug fixes, polish, docs and the demo only.

---

## 7. Phase 4: Polish, freeze, demo prep (H+4:30 – 5:15)

- [ ] **A:** freeze the prompt. Bump `PIPELINE_VERSION` one last time if you changed anything.
- [ ] **D:** generate fresh results locally for every demo essay (with the exact options you'll use in the video), then **commit `data/cache/*.json`** and redeploy. The live demo then loads instantly and can't fail on stage.
- [ ] **B:** final UI pass on the live URL, on both phone and laptop.
- [ ] **C:** docs final check: README, `docs/FEEDBACK_CRITERIA.md`, `docs/AI_APPROACH.md` with results filled in.
- [ ] **Everyone:** run the full demo flow once on the live URL and fix only real bugs.

---

## 8. Phase 5: Record and submit (H+5:15 – 6:00)

- [ ] Record the demo video (section 9). Do one rehearsal first, and keep a backup recording.
- [ ] Final submission checklist (section 11).
- [ ] Submit by **H+5:50**; don't cut it close.

---

## 9. Demo video script (about 3 minutes)

> **Updated script for the realigned product: [docs/DEMO.md](DEMO.md).** The table below is the original plan.

| Time | Show | Say (roughly) |
|---|---|---|
| 0:00–0:20 | Title or landing page | "Teachers spend hours on essay feedback, and existing tools only fix grammar. We built an AI writing coach that gives teacher-quality feedback in seconds." |
| 0:20–0:50 | **ESL essay** → report → corrections tab → click highlights | "It catches errors and explains the rule in simple language, so students learn rather than just copy fixes." |
| 0:50–1:30 | **Generic/cliché essay** | "This essay is grammatically clean, but it's generic. Our coach scores it low on originality and argument, and shows exactly which phrases are clichés and how to fix them. Grammar checkers can't do this." |
| 1:30–1:55 | **Strong essay** | "It recognizes real strengths: the rebuttal, the evidence. It doesn't invent problems." |
| 1:55–2:15 | **Narrative** + stretch feature | "It adapts to essay type and student level." (Show the stretch feature here.) |
| 2:15–2:45 | Grounding note + **eval results table** | "Every quote is checked against the essay, so there are no hallucinated comments. We measured X% error-detection recall, Y% agreement with human graders and Z% relevance." |
| 2:45–3:00 | Architecture slide or closing | "FastAPI on Vercel with free-tier Groq and automatic Gemini backup, rubric-driven, quote-grounded. Thank you." |

Recording tips: 1080p, browser zoom 110–125%, close other tabs, use cached results for instant loads, and use a clean browser profile without bookmarks.

---

## 10. Risks and fallbacks

| Risk | Fallback |
|---|---|
| API key or quota problems | Gemini fallback kicks in automatically; mock mode for UI work; cached results for the demo; use a teammate's key |
| Slow responses (> 45s) | The demo uses the committed cache, so it's instant |
| Free-tier quota used up | Automatic Gemini fallback (several models); teammates' keys; committed demo cache; the quota resets daily |
| Vercel deploy breaks | Check the function logs; roll back to the previous deployment in the Vercel dashboard (one click); demo locally as a last resort |
| Venue Wi-Fi fails | Record the video early with cached results; phone hotspot |
| Merge conflicts | File ownership (section 1); pull before you push; small commits |
| Prompt keeps getting worse | Keep the last good version in git; `git checkout <commit> -- core/prompts.py` |
| Running out of time | Cut the stretch feature first, then UI polish. **Never cut evals, docs or the video**; they're required deliverables. |
| Leaked API key | Keys live only in `.env` and Vercel env vars. If one is pushed by accident, revoke it in the Anthropic console immediately. |

---

## 11. Final submission checklist

**Product**
- [ ] Live Vercel URL works (share the access code with judges if one is set)
- [ ] All demo essays load instantly from the cache
- [ ] Works on phone and laptop

**Required deliverables**
- [ ] AI agent: essay in, detailed constructive report out (strengths + improvements)
- [ ] Simple UI for submission and viewing
- [ ] `docs/FEEDBACK_CRITERIA.md` (feedback criteria)
- [ ] `docs/AI_APPROACH.md` (AI approach + **eval results filled in**)
- [ ] `data/DATASETS.md` (dataset sources, licenses, citations)
- [ ] Demo video showing **diverse** essays
- [ ] Evidence for the 80%+ accuracy and relevance metric

**Repo hygiene**
- [ ] No `.env` or API keys committed
- [ ] README has setup steps and the live URL
- [ ] Final commit pushed; the live deploy matches it

---

## 12. Git workflow (keep it simple)

- One branch: `main`. Small, frequent commits with clear messages (`prompt: stricter grounding rule`, `ui: mobile tabs fix`).
- `git pull --rebase` before every push.
- Vercel auto-deploys `main`, so **don't push broken code**. Run locally first.
- Bigger experiments (the stretch feature) go on a branch. Vercel gives each branch a preview URL; merge when it works.
