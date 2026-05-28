"""Regenerate the general English→Chinese translation layer (tools/ecdict_data.json).

This is a BUILD INPUT, not a shipped file: build_dict.py merges these common-word
translations into extension-browser/dict.json (skipping any key already covered by
a curated term), so the fallback rides the SAME dict.json that the app already
pulls via "检查词库更新" — no separate file, no installer change.

It is intentionally NOT the full 3.4M-entry ECDICT — that would bloat dict.json.
We keep only the most *common* words (by COCA / BNC frequency rank) and layer the
hand-curated seed (tools/ecdict_seed.json) on top so nice programming glosses win.

Usage:

  # Recommended: download full ecdict.csv and keep the top-N common words
  py tools/setup_translator.py --download --top 30000
  # then rebuild so dict.json picks them up:
  py tools/build_dict.py

  # Or convert a local ECDICT csv (the 13-column one with frq/bnc), same filter
  py tools/setup_translator.py --csv path/to/ecdict.csv --top 30000

  # Or import any plain "english,chinese" two-column csv (no freq filter)
  py tools/setup_translator.py --csv path/to/simple.csv

Output: tools/ecdict_data.json  (flat {word: 中文}, ~2 MB at top 30k)

build_dict.py tags these entries category "translation" so the card can mark them
as generic dictionary translations (vs the curated 三段式 terms).

ECDICT is from https://github.com/skywind3000/ECDICT (free to use).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tools" / "ecdict_data.json"
SEED = ROOT / "tools" / "ecdict_seed.json"
MAX_KEY_LEN = 40
MAX_VAL_LEN = 200
DEFAULT_TOP = 30000

# Full ECDICT csv (13 columns, with frq/bnc frequency ranks) lives in the repo,
# not in the GitHub releases (those are stardict/mdx/sqlite only).
ECDICT_CSV_URL = "https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv"

# csv has very long `detail` fields on some rows
csv.field_size_limit(10 * 1024 * 1024)


def is_useful(key: str) -> bool:
    if not key or len(key) > MAX_KEY_LEN:
        return False
    # mostly-ASCII English words; allow internal space / - / . / '
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9 \-./']*$", key))


def clean_value(v: str) -> str:
    if not v:
        return ""
    # ECDICT uses literal "\n" between senses; drop noisy [网络] crowd-sourced lines
    parts = re.split(r"\\n|\n|<br>", v)
    parts = [p.strip() for p in parts if p.strip() and not p.strip().startswith("[网络]")]
    v = " · ".join(parts) if parts else v.strip()
    if len(v) > MAX_VAL_LEN:
        v = v[:MAX_VAL_LEN] + "…"
    return v


def _freq_rank(row: dict) -> int:
    """Best (smallest, nonzero) of COCA(frq) / BNC(bnc) rank. 0 = unranked/rare."""
    ranks = []
    for col in ("frq", "bnc"):
        try:
            r = int(row.get(col) or 0)
        except ValueError:
            r = 0
        if r > 0:
            ranks.append(r)
    return min(ranks) if ranks else 0


def from_ecdict_csv(path: Path, top: int) -> dict:
    """Parse the 13-column ECDICT csv, keep common words within top-N frequency."""
    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "translation" not in reader.fieldnames:
            raise RuntimeError(
                "Not an ECDICT-format csv (need a 'translation' column). "
                "For a plain english,chinese file, the 2-column path is used instead."
            )
        for row in reader:
            word = (row.get("word") or "").strip()
            tr = (row.get("translation") or "").strip()
            if not word or not tr or not is_useful(word):
                continue
            rank = _freq_rank(row)
            if rank == 0 or rank > top:
                continue
            out[word.lower()] = clean_value(tr)
    return out


def from_simple_csv(path: Path) -> dict:
    """Plain two-column english,chinese csv (no frequency filtering)."""
    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if len(row) < 2:
                continue
            if i == 0 and row[0].lower() in {"word", "key", "english"}:
                continue  # header
            k, v = row[0], row[1]
            if is_useful(k) and v:
                out[k.lower()] = clean_value(v)
    return out


def looks_like_ecdict(path: Path) -> bool:
    with path.open(encoding="utf-8", newline="") as f:
        head = f.readline().strip().lower()
    return head.startswith("word,phonetic") or ("translation" in head and "frq" in head)


def load_seed() -> dict:
    if not SEED.exists():
        return {}
    try:
        return json.load(SEED.open(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, help="path to an ECDICT csv or a simple english,chinese csv")
    parser.add_argument("--download", action="store_true", help="download full ecdict.csv (~62MB) and filter")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP,
                        help=f"keep words within this COCA/BNC frequency rank (default {DEFAULT_TOP}; 0 = no cap)")
    parser.add_argument("--no-seed", action="store_true", help="do not merge the curated seed on top")
    parser.add_argument("--out", type=str, default=str(OUT))
    args = parser.parse_args()

    if not args.csv and not args.download:
        parser.print_help()
        print("\nMust pass --csv FILE or --download.")
        return 2

    top = args.top if args.top and args.top > 0 else 10**9

    if args.download:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "ecdict.csv"
            print(f"Downloading {ECDICT_CSV_URL} (~62 MB)...")
            urllib.request.urlretrieve(ECDICT_CSV_URL, csv_path)
            print("Parsing + frequency-filtering...")
            data = from_ecdict_csv(csv_path, top)
    else:
        csv_path = Path(args.csv).expanduser().resolve()
        if not csv_path.exists():
            sys.stderr.write(f"CSV not found: {csv_path}\n")
            return 1
        data = from_ecdict_csv(csv_path, top) if looks_like_ecdict(csv_path) else from_simple_csv(csv_path)

    ecdict_n = len(data)

    # Merge curated seed on top — hand-written glosses win over raw ECDICT.
    seed_n = 0
    if not args.no_seed:
        seed = load_seed()
        seed_n = len(seed)
        data.update({k.lower(): v for k, v in seed.items() if v})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    size_mb = out.stat().st_size / 1024 / 1024
    rel = out.relative_to(ROOT) if str(out).startswith(str(ROOT)) else out
    print(f"Wrote {rel}: {len(data)} entries ({size_mb:.1f} MB)  "
          f"[ecdict {ecdict_n} + seed {seed_n}, top={args.top}]  "
          f"-> now run: py tools/build_dict.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
