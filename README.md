# Essay Feedback Coach

An AI agent that reads a student essay and returns a detailed, constructive feedback report covering **grammar, coherence, argument strength and originality**. The report includes rubric scores, quoted evidence, explanations, suggested rewrites and a practice exercise.

Built for TCS Technology Day, problem statement "Education: Automated Essay Feedback Generator".

- **Team: start here:** [docs/context.md](docs/context.md) (what and why) and [docs/buildplan.md](docs/buildplan.md) (who, when, done criteria)
- Feedback criteria: [docs/FEEDBACK_CRITERIA.md](docs/FEEDBACK_CRITERIA.md)
- AI approach and evaluation: [docs/AI_APPROACH.md](docs/AI_APPROACH.md)

## Stack

**FastAPI** (Python) backend, a plain **HTML/CSS/JS** frontend, and free AI models (Google Gemini, with Groq as backup). It deploys to **Vercel** as one project.

## API keys (free)

You need two free keys. Paste them into `.env`:

| Key | Get it here |
|---|---|
| `GEMINI_API_KEY` (main model) | https://aistudio.google.com/apikey |
| `GROQ_API_KEY` (backup, used automatically if Gemini is busy) | https://console.groq.com/keys |

Check they work with `python -m core.llm test`.

- Each teammate should make **their own** keys; free limits are per person.
- Never commit `.env` (it's already git-ignored).

## Project structure

```
app.py                  FastAPI entrypoint (Vercel auto-detects `app`)
core/
  config.py             settings from env / .env
  rubric.py             feedback criteria: single source of truth
  preprocess.py         normalize, segment, readability stats
  prompts.py            system prompt + user prompt builder   <- tune quality here
  schema.py             JSON schema the model must return
  llm.py                model client: Gemini / Groq (free) with auto-fallback, + mock mode
  verify.py             checks every quote really appears in the essay
  pipeline.py           preprocess -> LLM -> verify -> cache
  report.py             Markdown export
frontend/
  index.html, styles.css, app.js     the UI (no build step)
data/
  sample_essays/        demo essays (shown as "Try a sample" chips)
  mock_feedback.json    canned output for MOCK_LLM=1
  cache/                cached results (commit demo results here for instant demos)
  raw/                  downloaded datasets (git-ignored)
  DATASETS.md           dataset sources, licenses, citations, columns
  download_datasets.py  fetches ELLIPSE / PERSUADE 2.0 / ASAP 2.0 into data/raw
  prepare_datasets.py   unpacks the Kaggle zips + builds argument-element summary
eval/
  run_eval.py           accuracy + relevance metrics
  datasets.py           dataset loaders
  generate_synthetic.py writes synthetic essays with known flaws (LLM)
  flaws.py              structural flaw types + detection keywords
  synthetic_cases.json  hand-written essays with planted errors/flaws
  results/              metric reports (JSON + Markdown)
docs/                   criteria + AI approach (deliverables)
vercel.json             function timeout + bundle excludes
```

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
copy .env.example .env            # then add GEMINI_API_KEY + GROQ_API_KEY (macOS/Linux: cp)
python -m core.llm test           # check both keys work
uvicorn app:app --reload
```

Open http://localhost:8000.

**No API key yet?** Set `MOCK_LLM=1` in `.env`. The UI then works fully using canned feedback from `data/mock_feedback.json`, which matches the "ESL grammar errors" sample.

## Deploy to Vercel

1. Push this folder to a GitHub repo, then go to **vercel.com -> Add New -> Project** and import the repo. FastAPI is detected automatically.
2. Under **Settings -> Environment Variables**, add `GEMINI_API_KEY` and `GROQ_API_KEY`. Optionally add `APP_ACCESS_CODE` (any password) so strangers can't use up your free quota.
3. Deploy. Every later push redeploys automatically.

Alternatively, use the CLI: `npm i -g vercel`, then `vercel` (preview) and `vercel --prod`.

Notes:
- `vercel.json` sets `maxDuration: 300` because model calls can take 20-60 seconds.
- The file system on Vercel is read-only except `/tmp`, so new results are cached in `/tmp` per instance. **For a reliable demo**, generate the demo essays locally first and commit `data/cache/*.json`. Vercel then serves those results instantly.

## Evaluation (the "80%+ accuracy" evidence)

Datasets (ELLIPSE, PERSUADE 2.0, ASAP 2.0, synthetic) with links, licenses and citations: [data/DATASETS.md](data/DATASETS.md).

```bash
python data/download_datasets.py                      # ELLIPSE auto; PERSUADE/ASAP via Kaggle (see DATASETS.md)
python data/prepare_datasets.py                       # unpack Kaggle zips in data/raw/ + build argument annotations
python -m eval.generate_synthetic                     # once: 8 essays with known flaws (needs API)
python -m eval.run_eval synthetic                     # planted-error + structural-flaw recall
python -m eval.run_eval ellipse --n 30                # grammar/coherence score agreement vs human raters
python -m eval.run_eval argument --n 30               # argument checklist vs PERSUADE expert annotations
python -m eval.run_eval holistic --dataset persuade   # holistic score agreement (or --dataset asap)
python -m eval.run_eval relevance-export              # then fill the sheet with 1/0
python -m eval.run_eval relevance-score
```

## Suggested team split (6 hours)

| Who | Owns | First task |
|---|---|---|
| AI | `core/prompts.py`, `core/schema.py` | Get real output on all 4 samples; tune the prompt |
| Frontend | `frontend/` | Polish the UI using `MOCK_LLM=1` (no key needed) |
| Eval and docs | `eval/`, `docs/` | Download ELLIPSE, run evals, fill the results table |
| Deploy and demo | Vercel, demo video | Deploy early (hour 1), commit the demo cache, record the video |

## Demo tips

- `http://localhost:8000/?notour` skips the onboarding tour.
- `http://localhost:8000/?sample=2_esl_grammar_errors` loads a sample and generates its report straight away.
- "Take the tour" in the top bar replays the onboarding.
- Full list of UI features: [docs/features.md](docs/features.md) §7.

## Demo checklist

- [ ] All 4 samples generate good feedback; results committed in `data/cache/`
- [ ] Deployed URL works on a phone
- [ ] Eval results pasted into `docs/AI_APPROACH.md`
- [ ] Demo video: strong essay -> ESL essay (corrections) -> generic essay (originality/argument) -> narrative
