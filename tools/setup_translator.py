"""Optional: install ECDICT (or any English→Chinese CSV) as codelang's translation fallback.

Two modes:

1) Convert a local CSV/TSV file:
     py tools/setup_translator.py --csv path/to/words.csv

   Expected format: first column English word, second column Chinese meaning.
   Headers like "word,translation" are tolerated.

2) Download ECDICT stardict zip and extract (heaviest, ~67MB):
     py tools/setup_translator.py --download

   Network must be available. Output saved to
     extension-browser/ecdict.json   (~3-30 MB depending on pruning)

Behavior:
   - Keeps only entries with English (ASCII) lookup keys.
   - Drops entries longer than 40 chars (avoid junk).
   - Lowercases keys.
   - Caps meaning text at 200 chars.

After this runs, the desktop app will automatically use it as a translation
fallback for words missing from dict/*.yaml. Card will show category
"通用翻译·非术语词典" to distinguish from curated entries.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "extension-browser" / "ecdict.json"
MAX_KEY_LEN = 40
MAX_VAL_LEN = 200


def is_useful(key: str) -> bool:
    if not key:
        return False
    if len(key) > MAX_KEY_LEN:
        return False
    # Want mostly-ASCII English words; allow internal -/'/. only
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9 \-./']*$", key))


def clean_value(v: str) -> str:
    if not v:
        return ""
    v = v.replace("\\n", " · ").replace("<br>", " · ").replace("\n", " · ").strip()
    if len(v) > MAX_VAL_LEN:
        v = v[:MAX_VAL_LEN] + "…"
    return v


def from_csv(path: Path) -> dict:
    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        first = next(reader, None)
        if first and first[0].lower() in {"word", "key", "english"}:
            pass  # skip header
        else:
            # treat as data
            if first and len(first) >= 2:
                k, v = first[0], first[1]
                if is_useful(k) and v:
                    out[k.lower()] = clean_value(v)
        for row in reader:
            if len(row) < 2:
                continue
            k, v = row[0], row[1]
            if is_useful(k) and v:
                out[k.lower()] = clean_value(v)
    return out


ECDICT_STARDICT_URL = "https://github.com/skywind3000/ECDICT/releases/download/1.0.28/ecdict-stardict-28.zip"


def from_ecdict_stardict_download(tmpdir: Path) -> dict:
    zip_path = tmpdir / "ecdict-stardict.zip"
    print(f"Downloading {ECDICT_STARDICT_URL} (~67 MB)...")
    urllib.request.urlretrieve(ECDICT_STARDICT_URL, zip_path)
    print("Extracting...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmpdir)
    # Look for the .idx + .dict.dz inside; we instead try CSV/txt fallbacks
    txt_files = list(tmpdir.rglob("*.txt")) + list(tmpdir.rglob("*.csv"))
    if not txt_files:
        raise RuntimeError(
            "ECDICT stardict zip extracted but no CSV/TXT found inside. "
            "Try --csv path manually with the ecdict CSV file from the repo."
        )
    # Just take the first TXT/CSV
    return from_csv(txt_files[0])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, help="path to a CSV (English,Chinese) to import")
    parser.add_argument("--download", action="store_true", help="download ECDICT and convert (large)")
    parser.add_argument("--out", type=str, default=str(OUT))
    args = parser.parse_args()

    if not args.csv and not args.download:
        parser.print_help()
        print("\nMust pass --csv FILE or --download.")
        return 2

    if args.csv:
        csv_path = Path(args.csv).expanduser().resolve()
        if not csv_path.exists():
            sys.stderr.write(f"CSV not found: {csv_path}\n")
            return 1
        data = from_csv(csv_path)
    else:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            data = from_ecdict_stardict_download(Path(td))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT) if str(out).startswith(str(ROOT)) else out}: {len(data)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
