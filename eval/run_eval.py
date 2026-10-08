"""Measure feedback accuracy and relevance. Run from the project root.

Datasets: see data/DATASETS.md. Download with `python data/download_datasets.py`.

  python -m eval.generate_synthetic        (once, needs the API: writes eval/synthetic_generated.json)
  python -m eval.run_eval synthetic
      On essays with KNOWN flaws (eval/synthetic_cases.json + synthetic_generated.json):
      recall of planted grammar errors, recall of structural flaws (missing counterargument,
      no conclusion, ...), and scores on flawless control essays.

  python -m eval.run_eval ellipse --n 30
      Analytic score agreement with human raters on ELLIPSE (English-learner essays, grades 8-12):
      our grammar vs Grammar, coherence vs Cohesion, overall vs Overall (all 1-5 scales).

  python -m eval.run_eval holistic --dataset persuade --n 30      (or --dataset asap)
      Holistic score agreement on PERSUADE 2.0 / ASAP 2.0 (argumentative essays, grades 6-12,
      human score 1-6). Sample is stratified across score levels. PERSUADE defaults to
      independent-writing essays; ASAP 2.0 is all source-based (judged without the article).

  python -m eval.run_eval argument --n 30
      Our argument-structure checklist (lead, position, claim, counterclaim, rebuttal, evidence,
      concluding statement) vs PERSUADE 2.0 expert annotations, balanced on counterclaim present/absent.

  python -m eval.run_eval relevance-export
      Writes every feedback item from cached results to eval/results/relevance_sheet.csv.
      Teammates fill the `relevant` column with 1 or 0.

  python -m eval.run_eval relevance-score
      Reads the filled sheet and reports % of feedback items rated relevant and accurate.

Results are written to eval/results/ as JSON + Markdown. Model outputs for dataset essays are
cached in eval/cache/ (git-ignored) so re-runs are free and dataset text never gets committed.
"""
import argparse
import csv
import json
import random
import sys
from datetime import datetime

from core import config
from core.pipeline import FeedbackOptions, generate_feedback
from core.verify import find_span

from .datasets import PERSUADE_ELEMENTS, load_ellipse, load_holistic, load_persuade_with_elements
from .flaws import FLAWS, flaw_detected

RESULTS_DIR = config.EVAL_DIR / "results"
EVAL_CACHE = config.EVAL_DIR / "cache"
SHEET = RESULTS_DIR / "relevance_sheet.csv"

# Our criterion -> ELLIPSE trait it is compared against
ELLIPSE_MAP = {"grammar": "grammar", "coherence": "cohesion", "overall": "overall"}
DATASET_NAMES = {"ellipse": "ELLIPSE", "persuade": "PERSUADE 2.0", "asap": "ASAP 2.0"}


def _save(name: str, data: dict, markdown: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    data["run_at"] = datetime.now().isoformat(timespec="seconds")
    data["model"] = config.MODEL_LABEL
    (RESULTS_DIR / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (RESULTS_DIR / f"{name}.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"Saved to {RESULTS_DIR / name}.json / .md")


def _scores(result: dict) -> dict:
    fb = result["feedback"]
    out = {c["criterion"]: c["score"] for c in fb["criteria"]}
    out["overall"] = fb["overall_score"]
    return out


def _run(text: str, options: FeedbackOptions) -> dict | None:
    try:
        return generate_feedback(text, options, cache_dir=EVAL_CACHE)
    except Exception as e:  # keep going; one bad essay shouldn't kill the run
        print(f"  skipped: {e}")
        return None


# ---------- metrics ----------

def quadratic_weighted_kappa(a: list[int], b: list[int], lo: int, hi: int) -> float:
    n = hi - lo + 1
    observed = [[0] * n for _ in range(n)]
    for x, y in zip(a, b):
        observed[x - lo][y - lo] += 1
    total = len(a)
    hist_a = [sum(row) for row in observed]
    hist_b = [sum(observed[i][j] for i in range(n)) for j in range(n)]
    num = den = 0.0
    for i in range(n):
        for j in range(n):
            w = (i - j) ** 2 / (n - 1) ** 2
            num += w * observed[i][j]
            den += w * hist_a[i] * hist_b[j] / total
    return 1.0 - num / den if den else 1.0


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = _ranks(a), _ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((y - mb) ** 2 for y in rb) ** 0.5
    return cov / (va * vb) if va and vb else 0.0


# ---------- synthetic essays: planted errors + structural flaws ----------

def _load_synthetic() -> list[dict]:
    cases = []
    for name in ("synthetic_cases.json", "synthetic_generated.json"):
        path = config.EVAL_DIR / name
        if path.exists():
            cases += json.loads(path.read_text(encoding="utf-8"))
    return cases


def run_synthetic(_args) -> None:
    cases = _load_synthetic()
    rows = []
    found_total = planted_total = extra_total = 0
    flaw_hits: dict[str, list[int]] = {}
    false_alarms: dict[str, list[int]] = {}  # flaw "detected" in essays that don't have it
    controls = []
    for case in cases:
        print(f"- {case['id']}")
        result = _run(case["essay"], FeedbackOptions(case["grade_level"], case["essay_type"]))
        if result is None:
            continue
        essay, fb = result["essay"], result["feedback"]

        # 1. Planted grammar/mechanics errors: a hit if any flagged quote overlaps the planted span.
        flagged = [e["quote"] for e in fb["grammar_errors"]]
        flagged += [i["quote"] for c in fb["criteria"] if c["criterion"] == "grammar" for i in c["improvements"]]
        flagged_spans = [s for s in (find_span(q, essay) for q in flagged) if s]
        planted_spans = [(p, find_span(p["quote"], essay)) for p in case["planted"]]
        missed = [p["quote"] for p, span in planted_spans
                  if not (span and any(fs[0] < span[1] and span[0] < fs[1] for fs in flagged_spans))]
        found_total += len(case["planted"]) - len(missed)
        planted_total += len(case["planted"])
        extra = [fs for fs in flagged_spans
                 if not any(sp and fs[0] < sp[1] and sp[0] < fs[1] for _, sp in planted_spans)]
        extra_total += len(extra)

        # 2. Structural flaws: a hit if the relevant criterion's feedback mentions the flaw.
        flaws_missed = []
        for flaw in case.get("flaws", []):
            hit = flaw_detected(flaw, fb)
            flaw_hits.setdefault(flaw, []).append(int(hit))
            if not hit:
                flaws_missed.append(flaw)
        for flaw in FLAWS:
            if flaw not in case.get("flaws", []):
                false_alarms.setdefault(flaw, []).append(int(flaw_detected(flaw, fb)))

        scores = _scores(result)
        if case.get("control"):
            controls.append({"id": case["id"], "scores": scores})
        rows.append({"id": case["id"], "source": case.get("source", ""), "planted": len(case["planted"]),
                     "detected": len(case["planted"]) - len(missed), "missed": missed, "extra_flags": len(extra),
                     "flaws": case.get("flaws", []), "flaws_missed": flaws_missed, "scores": scores})

    recall = found_total / planted_total if planted_total else 0.0
    n_flaws = sum(len(v) for v in flaw_hits.values())
    flaw_recall = sum(sum(v) for v in flaw_hits.values()) / n_flaws if n_flaws else 0.0
    data = {"cases": len(rows), "error_recall": round(recall, 3), "planted": planted_total, "detected": found_total,
            "extra_flags": extra_total, "flaw_recall": round(flaw_recall, 3), "flaws_total": n_flaws,
            "flaw_recall_by_type": {k: round(sum(v) / len(v), 3) for k, v in flaw_hits.items()},
            "false_alarm_by_type": {k: round(sum(v) / len(v), 3) for k, v in false_alarms.items()},
            "controls": controls, "per_case": rows}

    md = ["# Synthetic essays: planted errors and structural flaws\n",
          f"{len(rows)} essays ({sum(r['source'] == 'generated' for r in rows)} generated, "
          f"{sum(r['source'] == 'hand-written' for r in rows)} hand-written).\n",
          f"- **Grammar/mechanics error recall: {recall:.0%}** ({found_total}/{planted_total} planted errors flagged)",
          f"- **Structural flaw recall: {flaw_recall:.0%}** ({sum(sum(v) for v in flaw_hits.values())}/{n_flaws} flaws mentioned in feedback)",
          f"- Extra grammar flags (not planted; may be real issues or false positives): {extra_total}\n"]
    if flaw_hits:
        md += ["| Structural flaw | Essays with flaw | Detected | False alarms (essays without it) |", "|---|---|---|---|"]
        for k, v in sorted(flaw_hits.items()):
            fa = false_alarms.get(k, [])
            fa_text = f"{sum(fa) / len(fa):.0%} of {len(fa)}" if fa else "-"
            md.append(f"| {k} | {len(v)} | {sum(v) / len(v):.0%} | {fa_text} |")
        md.append("")
    if controls:
        md.append("**Control essays** (no planted flaws; scores should be high): " +
                  "; ".join(f"{c['id']}: " + ", ".join(f"{k} {v}" for k, v in c["scores"].items()) for c in controls) + "\n")
    md += ["| Case | Errors planted | Detected | Missed errors | Flaws missed |", "|---|---|---|---|---|"]
    md += [f"| {r['id']} | {r['planted']} | {r['detected']} | {', '.join(r['missed']) or '-'} | "
           f"{', '.join(r['flaws_missed']) or '-'} |" for r in rows]
    _save("synthetic", data, "\n".join(md) + "\n")


# ---------- ELLIPSE analytic score agreement ----------

def run_ellipse(args) -> None:
    essays = load_ellipse()
    random.Random(args.seed).shuffle(essays)
    essays = essays[: args.n]

    ours: dict[str, list[int]] = {k: [] for k in ELLIPSE_MAP}
    human: dict[str, list[float]] = {k: [] for k in ELLIPSE_MAP}
    for i, e in enumerate(essays, 1):
        print(f"[{i}/{len(essays)}] {e['id']}")
        result = _run(e["text"], FeedbackOptions("English language learner", "Argumentative"))
        if result is None:
            continue
        scores = _scores(result)
        for key, trait in ELLIPSE_MAP.items():
            if key in scores and trait in e["scores"]:
                ours[key].append(scores[key])
                human[key].append(e["scores"][trait])

    report = {}
    md = ["# Score agreement with human raters: ELLIPSE\n",
          f"Sample: {len(essays)} random essays from the ELLIPSE train split (seed {args.seed}). "
          "Human scores are 1.0-5.0 in 0.5 steps; ours are integers 1-5.\n",
          "| Our score | ELLIPSE trait | n | Within 1 point | Exact (rounded) | MAE | QWK | Spearman |",
          "|---|---|---|---|---|---|---|---|"]
    for key, trait in ELLIPSE_MAP.items():
        o, h = ours[key], human[key]
        if not o:
            continue
        rounded = [max(1, min(5, int(x + 0.5))) for x in h]
        errs = [abs(a - b) for a, b in zip(o, h)]
        m = {"n": len(o),
             "within_1": round(sum(x <= 1.0 for x in errs) / len(errs), 3),
             "exact": round(sum(a == b for a, b in zip(o, rounded)) / len(o), 3),
             "mae": round(sum(errs) / len(errs), 3),
             "qwk": round(quadratic_weighted_kappa(o, rounded, 1, 5), 3),
             "spearman": round(spearman(o, h), 3)}
        report[key] = m
        md.append(f"| {key} | {trait.capitalize()} | {m['n']} | **{m['within_1']:.0%}** | {m['exact']:.0%} | "
                  f"{m['mae']:.2f} | {m['qwk']:.2f} | {m['spearman']:.2f} |")
    _save("ellipse", {"dataset": "ELLIPSE", "metrics": report, "n": len(essays), "seed": args.seed},
          "\n".join(md) + "\n")


# ---------- PERSUADE 2.0 / ASAP 2.0 holistic agreement ----------

def _stratified(essays: list[dict], n: int, seed: int) -> list[dict]:
    """Equal-ish number of essays per human score level, so rare high/low scores are represented."""
    rng = random.Random(seed)
    by_score: dict[int, list[dict]] = {}
    for e in essays:
        by_score.setdefault(e["score"], []).append(e)
    for group in by_score.values():
        rng.shuffle(group)
    picked, levels = [], sorted(by_score)
    while len(picked) < n and any(by_score[s] for s in levels):
        for s in levels:
            if by_score[s] and len(picked) < n:
                picked.append(by_score[s].pop())
    rng.shuffle(picked)
    return picked


def _options(e: dict) -> FeedbackOptions:
    """Give the model the same context the student had: their level and the full assignment."""
    return FeedbackOptions(e["level"], "Argumentative", e["assignment"] or e["prompt"])


def run_holistic(args) -> None:
    name = DATASET_NAMES[args.dataset]
    # PERSUADE: default to essays written without a source article (the app never sees the article).
    # ASAP 2.0 is entirely source-based, so "independent" would be empty there.
    task = args.task or ("independent" if args.dataset == "persuade" else "all")
    pool = load_holistic(args.dataset, task=task)
    if not pool:
        sys.exit(f"No {name} essays match --task {task}.")
    essays = _stratified(pool, args.n, args.seed)

    ours_overall, ours_argument, human = [], [], []
    for i, e in enumerate(essays, 1):
        print(f"[{i}/{len(essays)}] {e['id']} (human {e['score']})")
        result = _run(e["text"], _options(e))
        if result is None:
            continue
        scores = _scores(result)
        ours_overall.append(scores["overall"])
        ours_argument.append(scores.get("argument", scores["overall"]))
        human.append(e["score"])
    if not human:
        sys.exit("No essays scored.")

    # Map our 1-5 scale onto the human 1-6 scale for distance-based metrics.
    to6 = [1 + (s - 1) * 5 / 4 for s in ours_overall]
    errs = [abs(a - b) for a, b in zip(to6, human)]
    m = {"n": len(human),
         "within_1": round(sum(x <= 1.0 for x in errs) / len(errs), 3),
         "mae": round(sum(errs) / len(errs), 3),
         "qwk": round(quadratic_weighted_kappa([round(x) for x in to6], human, 1, 6), 3),
         "spearman_overall": round(spearman(ours_overall, human), 3),
         "spearman_argument": round(spearman(ours_argument, human), 3)}
    task_note = {"independent": "independent-writing essays only",
                 "all": "all essays (source-based essays are judged without the source article)"}[task]
    md = [f"# Holistic score agreement: {name}\n",
          f"Sample: {m['n']} essays ({task_note}), stratified across human score levels 1-6 (seed {args.seed}). "
          "Our overall score (1-5) is mapped linearly onto 1-6 for distance metrics.\n",
          "| Metric | Value |", "|---|---|",
          f"| Within 1 point of human holistic score | **{m['within_1']:.0%}** |",
          f"| Mean absolute error (1-6 scale) | {m['mae']:.2f} |",
          f"| Quadratic weighted kappa | {m['qwk']:.2f} |",
          f"| Spearman: our overall vs human | {m['spearman_overall']:.2f} |",
          f"| Spearman: our argument score vs human | {m['spearman_argument']:.2f} |"]
    _save(args.dataset, {"dataset": name, "task": task, "metrics": m, "seed": args.seed}, "\n".join(md) + "\n")


# ---------- PERSUADE 2.0 argument structure vs expert annotations ----------

def run_argument(args) -> None:
    """Does our argument checklist agree with expert annotators about which elements each essay has?

    Sample is balanced on Counterclaim (half with, half without), so detecting a missing
    counterargument, the most actionable argument feedback, is tested fairly.
    """
    rng = random.Random(args.seed)
    pool = load_persuade_with_elements(task="independent")
    with_cc = [e for e in pool if e["elements"]["counterclaim"]]
    without_cc = [e for e in pool if not e["elements"]["counterclaim"]]
    rng.shuffle(with_cc)
    rng.shuffle(without_cc)
    essays = with_cc[: args.n // 2] + without_cc[: args.n - args.n // 2]
    rng.shuffle(essays)

    keys = list(PERSUADE_ELEMENTS.values())
    tp = {k: 0 for k in keys}; fp = {k: 0 for k in keys}; fn = {k: 0 for k in keys}; tn = {k: 0 for k in keys}
    flaw_flagged = []  # on essays WITHOUT a counterclaim: did the feedback tell the student to add one?
    n_done = 0
    for i, e in enumerate(essays, 1):
        print(f"[{i}/{len(essays)}] {e['id']} (counterclaim: {e['elements']['counterclaim']})")
        result = _run(e["text"], _options(e))
        if result is None:
            continue
        n_done += 1
        ours = {el["element"]: el["present"] for el in result["feedback"].get("argument_structure", [])}
        for k in keys:
            pred, truth = ours.get(k, False), e["elements"][k]
            if pred and truth: tp[k] += 1
            elif pred and not truth: fp[k] += 1
            elif truth: fn[k] += 1
            else: tn[k] += 1
        if not e["elements"]["counterclaim"]:
            flaw_flagged.append(int(flaw_detected("missing_counterargument", result["feedback"])))
    if not n_done:
        sys.exit("No essays scored.")

    per = {}
    md = ["# Argument structure vs expert annotations: PERSUADE 2.0\n",
          f"Sample: {n_done} independent-writing essays, balanced on whether experts annotated a Counterclaim "
          f"(seed {args.seed}). An element counts as present if experts annotated it at least once.\n",
          "| Element | Accuracy | Precision (present) | Recall (present) | Correctly marked missing |",
          "|---|---|---|---|---|"]
    for k in keys:
        total = tp[k] + fp[k] + fn[k] + tn[k]
        acc = (tp[k] + tn[k]) / total
        prec = tp[k] / (tp[k] + fp[k]) if tp[k] + fp[k] else None
        rec = tp[k] / (tp[k] + fn[k]) if tp[k] + fn[k] else None
        spec = tn[k] / (tn[k] + fp[k]) if tn[k] + fp[k] else None
        per[k] = {"accuracy": round(acc, 3), "precision": prec and round(prec, 3), "recall": rec and round(rec, 3),
                  "specificity": spec and round(spec, 3), "tp": tp[k], "fp": fp[k], "fn": fn[k], "tn": tn[k]}
        fmt = lambda x: "-" if x is None else f"{x:.0%}"
        md.append(f"| {k} | **{acc:.0%}** | {fmt(prec)} | {fmt(rec)} | {fmt(spec)} |")
    overall_acc = sum(tp[k] + tn[k] for k in keys) / sum(tp[k] + fp[k] + fn[k] + tn[k] for k in keys)
    flagged = sum(flaw_flagged) / len(flaw_flagged) if flaw_flagged else None
    md += ["", f"**Overall element accuracy: {overall_acc:.0%}**",
           f"\nOn essays with no counterclaim, the feedback told the student to address the other side in "
           f"**{'-' if flagged is None else f'{flagged:.0%}'}** of {len(flaw_flagged)} essays."]
    _save("argument", {"dataset": "PERSUADE 2.0", "n": n_done, "seed": args.seed, "overall_accuracy": round(overall_acc, 3),
                       "missing_counterclaim_flagged": flagged and round(flagged, 3), "per_element": per},
          "\n".join(md) + "\n")


# ---------- human relevance rating ----------

def relevance_export(_args) -> None:
    cache_dirs = {config.CACHE_DIR, config.DEMO_CACHE_DIR, EVAL_CACHE}
    files = sorted(p for d in cache_dirs if d.exists() for p in d.glob("*.json"))
    if not files:
        sys.exit("No cached results yet. Generate feedback for some essays first.")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    with SHEET.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["essay_id", "criterion", "kind", "quote", "feedback", "relevant"])
        for path in files:
            fb = json.loads(path.read_text(encoding="utf-8"))["feedback"]
            for c in fb["criteria"]:
                for s in c["strengths"]:
                    w.writerow([path.stem, c["criterion"], "strength", s["quote"], s["comment"], ""])
                    n += 1
                for i in c["improvements"]:
                    w.writerow([path.stem, c["criterion"], "improvement", i["quote"],
                                f"{i['issue']} | Try: {i['suggestion']}", ""])
                    n += 1
            for e in fb["grammar_errors"]:
                w.writerow([path.stem, "grammar", "error", e["quote"], f"-> {e['correction']}: {e['explanation']}", ""])
                n += 1
    print(f"Wrote {n} items from {len(files)} essays to {SHEET}. Fill 'relevant' with 1 or 0, then run relevance-score.")


def relevance_score(_args) -> None:
    with SHEET.open(encoding="utf-8") as f:
        rated = [r for r in csv.DictReader(f) if r["relevant"].strip() in {"0", "1"}]
    if not rated:
        sys.exit(f"No rated rows in {SHEET}.")
    by_kind: dict[str, list[int]] = {}
    for r in rated:
        by_kind.setdefault(r["kind"], []).append(int(r["relevant"]))
    overall = sum(int(r["relevant"]) for r in rated) / len(rated)
    md = ["# Human-rated feedback relevance\n", f"**{overall:.0%} of {len(rated)} rated items judged relevant and accurate.**\n",
          "| Item type | Rated | Relevant |", "|---|---|---|"]
    md += [f"| {k} | {len(v)} | {sum(v) / len(v):.0%} |" for k, v in sorted(by_kind.items())]
    _save("relevance", {"overall": round(overall, 3), "n": len(rated),
                        "by_kind": {k: round(sum(v) / len(v), 3) for k, v in by_kind.items()}}, "\n".join(md) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("synthetic").set_defaults(func=run_synthetic)
    p = sub.add_parser("ellipse")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(func=run_ellipse)
    p = sub.add_parser("holistic")
    p.add_argument("--dataset", choices=["persuade", "asap"], default="persuade")
    p.add_argument("--task", choices=["independent", "all"], default=None,
                   help="PERSUADE default: independent (no source article). ASAP is all source-based.")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(func=run_holistic)
    p = sub.add_parser("argument")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(func=run_argument)
    sub.add_parser("relevance-export").set_defaults(func=relevance_export)
    sub.add_parser("relevance-score").set_defaults(func=relevance_score)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
