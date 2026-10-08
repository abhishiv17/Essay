"""Unpack the Kaggle downloads and build derived files the evals use. Run from the project root:

  python data/prepare_datasets.py

Looks in data/raw/ for the Kaggle zips (any *.zip; Kaggle names them archive.zip, archive (1).zip, ...)
or already-extracted CSVs, then:
  - extracts PERSUADE 2.0 scores        -> data/raw/persuade_2.0/persuade_2.0_human_scores_demo_id_github.csv
  - extracts PERSUADE sources           -> data/raw/persuade_2.0/sources.csv
  - extracts ASAP 2.0                   -> data/raw/asap_2.0/ASAP2_train_sourcetexts.csv
  - builds an argument-element summary  -> data/raw/persuade_2.0/discourse_summary.csv
    (one row per essay: how many Lead/Position/Claim/Counterclaim/Rebuttal/Evidence/Concluding
    Statement spans expert annotators marked), streamed from persuade_corpus_1.0.csv (804 MB)
    without extracting it to disk.
Safe to re-run: existing outputs are skipped.
"""
import csv
import io
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**31 - 1)

RAW = Path(__file__).resolve().parent / "raw"
PERSUADE_DIR = RAW / "persuade_2.0"
ASAP_DIR = RAW / "asap_2.0"

EXTRACT = {
    "persuade_2.0_human_scores_demo_id_github.csv": PERSUADE_DIR,
    "sources.csv": PERSUADE_DIR,
    "ASAP2_train_sourcetexts.csv": ASAP_DIR,
}
ANNOTATIONS = "persuade_corpus_1.0.csv"
SUMMARY = PERSUADE_DIR / "discourse_summary.csv"
ELEMENTS = ["Lead", "Position", "Claim", "Counterclaim", "Rebuttal", "Evidence", "Concluding Statement"]


def _zip_members() -> dict[str, Path]:
    """Map member name -> zip that contains it, for every zip in data/raw."""
    found = {}
    for z in sorted(RAW.glob("*.zip")):
        try:
            with zipfile.ZipFile(z) as f:
                for name in f.namelist():
                    found.setdefault(Path(name).name, z)
        except zipfile.BadZipFile:
            print(f"  ! {z.name} is not a valid zip, skipping")
    return found


def extract_files(members: dict[str, Path]) -> None:
    for name, dest_dir in EXTRACT.items():
        target = dest_dir / name
        if target.exists():
            print(f"[ok]      {target.relative_to(RAW.parent)}")
            continue
        loose = RAW / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        if loose.exists():
            loose.replace(target)
            print(f"[moved]   {name} -> {target.relative_to(RAW.parent)}")
        elif name in members:
            with zipfile.ZipFile(members[name]) as z:
                member = next(m for m in z.namelist() if Path(m).name == name)
                with z.open(member) as src, target.open("wb") as out:
                    while chunk := src.read(1 << 20):
                        out.write(chunk)
            print(f"[extract] {name} from {members[name].name} -> {target.relative_to(RAW.parent)}")
        else:
            print(f"[missing] {name}: download it (see data/DATASETS.md) and re-run")


def build_discourse_summary(members: dict[str, Path]) -> None:
    if SUMMARY.exists():
        print(f"[ok]      {SUMMARY.relative_to(RAW.parent)}")
        return
    loose = RAW / ANNOTATIONS
    if loose.exists():
        handle = loose.open(encoding="utf-8", newline="")
    elif ANNOTATIONS in members:
        z = zipfile.ZipFile(members[ANNOTATIONS])
        member = next(m for m in z.namelist() if Path(m).name == ANNOTATIONS)
        handle = io.TextIOWrapper(z.open(member), encoding="utf-8", newline="")
    else:
        print(f"[missing] {ANNOTATIONS}: needed for the argument-structure eval (PERSUADE Kaggle download)")
        return

    print(f"[build]   streaming {ANNOTATIONS} (804 MB, about a minute)...")
    counts: dict[str, Counter] = defaultdict(Counter)
    with handle:
        for row in csv.DictReader(handle):
            counts[row["essay_id_comp"]][row["discourse_type"]] += 1

    PERSUADE_DIR.mkdir(parents=True, exist_ok=True)
    with SUMMARY.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["essay_id_comp"] + ELEMENTS)
        for essay_id, c in counts.items():
            w.writerow([essay_id] + [c.get(e, 0) for e in ELEMENTS])
    print(f"[built]   {SUMMARY.relative_to(RAW.parent)}: {len(counts)} essays")
    for e in ELEMENTS:
        have = sum(1 for c in counts.values() if c.get(e, 0) > 0)
        print(f"            {e:22} present in {have / len(counts):.0%} of essays")


def main() -> None:
    members = _zip_members()
    extract_files(members)
    build_discourse_summary(members)


if __name__ == "__main__":
    main()
