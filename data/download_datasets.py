"""Download the evaluation datasets into data/raw/ (git-ignored), then unpack them. From the project root:

  python data/download_datasets.py            # all
  python data/download_datasets.py ellipse    # just one: ellipse | persuade | asap

ELLIPSE downloads directly from its public GitHub repo (no login needed).
PERSUADE 2.0 and ASAP 2.0 are on Kaggle: this uses the Kaggle CLI if it is installed and
authenticated (pip install kaggle + ~/.kaggle/kaggle.json), otherwise it prints the manual steps.
Downloading by hand works too: drop the Kaggle zips into data/raw/ and run
`python data/prepare_datasets.py`. See data/DATASETS.md for sources, licenses and citations.
"""
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_datasets  # noqa: E402

RAW = Path(__file__).resolve().parent / "raw"

DATASETS = {
    "ellipse": {
        "url": "https://raw.githubusercontent.com/scrosseye/ELLIPSE-Corpus/main/ELLIPSE_Final_github_train.csv",
        "target": RAW / "ellipse_train.csv",
    },
    "persuade": {
        "kaggle": "nbroad/persaude-corpus-2",
        "target": RAW / "persuade_2.0" / "persuade_2.0_human_scores_demo_id_github.csv",
        "files": "persuade_2.0_human_scores_demo_id_github.csv, persuade_corpus_1.0.csv (for the argument eval)",
    },
    "asap": {
        "kaggle": "lburleigh/asap-2-0",
        "target": RAW / "asap_2.0" / "ASAP2_train_sourcetexts.csv",
        "files": "ASAP2_train_sourcetexts.csv",
    },
}


def download_url(name: str, spec: dict) -> None:
    print(f"[{name}] downloading {spec['url']}")
    try:
        with urllib.request.urlopen(spec["url"], timeout=120) as resp, spec["target"].open("wb") as out:
            shutil.copyfileobj(resp, out)
    except OSError as e:
        print(f"[{name}] download failed: {e}")
        return
    print(f"[{name}] saved {spec['target']} ({spec['target'].stat().st_size / 1e6:.1f} MB)")


def download_kaggle(name: str, spec: dict) -> None:
    if shutil.which("kaggle") is None:
        print(f"[{name}] Kaggle CLI not found. Manual download:\n"
              f"    1. Open https://www.kaggle.com/datasets/{spec['kaggle']} (log in) and click Download\n"
              f"    2. Put the zip in {RAW} (any name is fine). It contains: {spec['files']}\n"
              f"    3. Run: python data/prepare_datasets.py")
        return
    # Download the whole dataset as a zip; prepare_datasets extracts what we need and streams the rest.
    cmd = ["kaggle", "datasets", "download", "-d", spec["kaggle"], "-p", str(RAW)]
    print(f"[{name}] {' '.join(cmd)}")
    if subprocess.run(cmd).returncode != 0:
        print(f"[{name}] Kaggle download failed. Is ~/.kaggle/kaggle.json set up?")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    names = sys.argv[1:] or list(DATASETS)
    unknown = [n for n in names if n not in DATASETS]
    if unknown:
        sys.exit(f"Unknown dataset(s): {unknown}. Choose from {list(DATASETS)}.")
    for name in names:
        spec = DATASETS[name]
        if spec["target"].exists():
            print(f"[{name}] already present: {spec['target']}")
        elif "url" in spec:
            download_url(name, spec)
        else:
            download_kaggle(name, spec)
    print("\nUnpacking / preparing:")
    prepare_datasets.main()


if __name__ == "__main__":
    main()
