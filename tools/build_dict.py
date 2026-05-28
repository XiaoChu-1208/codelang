"""Merge dict/*.yaml into extension-browser/dict.json.

Output format optimized for O(1) lookup:
{
  "version": "...",
  "entries": [ {term, aliases, category, literal, meaning, example}, ... ],
  "index": { normalized_key: entry_idx, ... }
}

Run: py tools/build_dict.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("Need PyYAML. Install:  py -m pip install pyyaml\n")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
DICT_DIR = ROOT / "dict"
OUT_BROWSER = ROOT / "extension-browser" / "dict.json"
# General English→Chinese translation layer (common words from ECDICT), merged
# into dict.json as a second tier so it rides the same file the app already
# pulls. Regenerate with tools/setup_translator.py. Optional — build still works
# without it. Curated terms always win; only non-colliding keys are added.
ECDICT_DATA = ROOT / "tools" / "ecdict_data.json"
MAX_TR_LEN = 60  # keep generic glosses short so dict.json stays lean


def normalize(s) -> str:
    return str(s).strip().lower().replace(" ", "").replace("-", "").replace("_", "")


def main() -> int:
    entries: list[dict] = []
    seen_terms: set[str] = set()

    # user.yaml is a per-user overlay (now at ~/.codelang/user_dict.yaml) and
    # must never be baked into the shipping bundle — DictIndex merges it at
    # runtime instead. Filter out any stray `dict/user.yaml` defensively in
    # case a contributor's local copy lingers.
    yaml_files = [
        f for f in sorted(DICT_DIR.glob("*.yaml")) if f.name != "user.yaml"
    ]
    if not yaml_files:
        sys.stderr.write(f"No YAML files in {DICT_DIR}\n")
        return 1

    for yf in yaml_files:
        with yf.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        if not isinstance(data, list):
            sys.stderr.write(f"{yf.name}: top-level should be a list, got {type(data).__name__}\n")
            return 1
        for item in data:
            term = item.get("term")
            if not term:
                sys.stderr.write(f"{yf.name}: entry missing 'term': {item}\n")
                return 1
            if term in seen_terms:
                sys.stderr.write(f"Duplicate term: {term}\n")
                return 1
            seen_terms.add(term)
            entries.append(
                {
                    "term": str(term),
                    "aliases": [str(a) for a in (item.get("aliases", []) or [])],
                    "category": str(item.get("category", "misc")),
                    "literal": str(item.get("literal", "") or ""),
                    "meaning": str(item.get("meaning", "") or ""),
                    "example": str(item.get("example", "") or ""),
                }
            )

    # Build O(1) lookup index on normalized term + aliases.
    index: dict[str, int] = {}
    collisions: list[tuple[str, str, str]] = []
    for idx, e in enumerate(entries):
        keys = [e["term"], *e["aliases"]]
        for k in keys:
            nk = normalize(k)
            if not nk:
                continue
            if nk in index and index[nk] != idx:
                collisions.append((nk, entries[index[nk]]["term"], e["term"]))
            index[nk] = idx

    if collisions:
        for nk, a, b in collisions:
            sys.stderr.write(f"Key collision '{nk}': {a} vs {b}\n")
        return 1

    curated_count = len(entries)

    # Second tier: merge the general translation layer. These are common English
    # words (ECDICT, frequency-capped) for when a selection misses every curated
    # term — e.g. plain "government" / "apple". Tagged category "translation" so
    # the UI can mark them as generic dictionary glosses. Curated terms win: any
    # key already in the index is skipped.
    tr_added = 0
    if ECDICT_DATA.exists():
        try:
            tr = json.loads(ECDICT_DATA.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            sys.stderr.write(f"Warning: ecdict_data.json ignored ({e})\n")
            tr = {}
        for word, meaning in (tr.items() if isinstance(tr, dict) else []):
            nk = normalize(word)
            if not nk or nk in index:
                continue
            m = str(meaning or "").strip()
            if not m:
                continue
            # Keep just the first sense — generic glosses are a fallback, not the
            # curated 三段式 experience; this keeps dict.json from ballooning.
            m = m.split(" · ")[0].strip()
            if len(m) > MAX_TR_LEN:
                m = m[:MAX_TR_LEN] + "…"
            index[nk] = len(entries)
            entries.append(
                {
                    "term": str(word),
                    "aliases": [],
                    "category": "translation",
                    "literal": "",
                    "meaning": m,
                    "example": "",
                }
            )
            tr_added += 1

    payload = {
        "version": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(entries),
        "curated_count": curated_count,
        "entries": entries,
        "index": index,
    }

    OUT_BROWSER.parent.mkdir(parents=True, exist_ok=True)
    with OUT_BROWSER.open("w", encoding="utf-8") as f:
        # Compact (no indent): with the merged translation tier dict.json holds
        # ~37k entries and is pulled over the network — pretty-printing would
        # nearly double its size for zero runtime benefit (DictIndex json.loads
        # it either way).
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    print(
        f"Wrote {OUT_BROWSER.relative_to(ROOT)}: {len(entries)} entries "
        f"({curated_count} curated + {tr_added} translation), {len(index)} keys"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
