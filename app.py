"""FastAPI entrypoint. Vercel auto-detects `app` here; locally run `uvicorn app:app --reload`.

Routes:
  GET  /api/health    -> status + whether mock mode is on
  GET  /api/rubric    -> feedback criteria (for the UI legend)
  GET  /api/samples   -> demo essays from data/sample_essays
  GET  /api/evaluation -> measured accuracy metrics (data/evaluation_summary.json), never estimated
  POST /api/feedback  -> generate the feedback report (includes a Markdown export)
  POST /api/practice  -> check a student's rewrite for the practice task
  /                   -> static UI from frontend/
"""
import json

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core import config
from core.llm import LLMError
from core.pipeline import FeedbackOptions, check_practice, generate_feedback
from core.report import to_markdown
from core.rubric import ARGUMENT_ELEMENTS, CRITERIA, SCORE_MAX, SCORE_MIN

app = FastAPI(title="Essay Feedback Coach")


class FeedbackRequest(BaseModel):
    essay: str = Field(..., max_length=30000)
    grade_level: str = "High school (Grades 9-12)"
    essay_type: str = "Argumentative"
    assignment_prompt: str = Field("", max_length=2000)
    use_cache: bool = True


class PracticeRequest(BaseModel):
    task: str = Field(..., min_length=3, max_length=1500)
    original: str = Field("", max_length=2000)
    attempt: str = Field(..., min_length=3, max_length=2000)
    grade_level: str = "High school (Grades 9-12)"


def _check_access(code: str | None) -> None:
    if config.ACCESS_CODE and code != config.ACCESS_CODE:
        raise HTTPException(status_code=401, detail="Access code required.")


@app.get("/api/health")
def health():
    return {"ok": True, "mock": config.MOCK_LLM, "provider": "mock" if config.MOCK_LLM else config.PROVIDER,
            "fallback": config.FALLBACK_PROVIDER or None, "model": config.MODEL_LABEL,
            "access_code_required": bool(config.ACCESS_CODE)}


@app.get("/api/rubric")
def rubric():
    return {"min": SCORE_MIN, "max": SCORE_MAX, "criteria": CRITERIA,
            "argument_elements": {k: {"label": label, "description": desc}
                                  for k, (label, desc) in ARGUMENT_ELEMENTS.items()}}


@app.get("/api/evaluation")
def evaluation():
    """Measured evaluation results (written by eval/run_eval.py). Empty list if nothing has been measured."""
    path = config.DATA_DIR / "evaluation_summary.json"
    if not path.exists():
        return {"metrics": [], "generated_at": None}
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/samples")
def samples():
    out = []
    for path in sorted(config.SAMPLE_DIR.glob("*.txt")):
        title = path.stem.split("_", 1)[-1] if path.stem[0].isdigit() else path.stem
        out.append({"id": path.stem, "title": title.replace("_", " ").capitalize().replace("Esl ", "ESL "),
                    "text": path.read_text(encoding="utf-8")})
    return out


@app.post("/api/feedback")
def feedback(req: FeedbackRequest, x_access_code: str | None = Header(default=None)):
    _check_access(x_access_code)
    options = FeedbackOptions(req.grade_level, req.essay_type, req.assignment_prompt)
    try:
        result = generate_feedback(req.essay, options, use_cache=req.use_cache and config.USE_CACHE)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    result["markdown"] = to_markdown(result)
    return result


@app.post("/api/practice")
def practice(req: PracticeRequest, x_access_code: str | None = Header(default=None)):
    """Check a student's rewrite for the practice task (the "Now let's improve it" step)."""
    _check_access(x_access_code)
    try:
        return check_practice(req.task, req.original, req.attempt, req.grade_level)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))


# Declared last so the /api routes above take priority. On Vercel this is promoted to the CDN.
# Path is relative to the project root (run uvicorn from the project root).
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
