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


def normalize(s) -> str:
    return str(s).strip().lower().replace(" ", "").replace("-", "").replace("_", "")


def main() -> int:
    entries: list[dict] = []
    seen_terms: set[str] = set()

    yaml_files = sorted(DICT_DIR.glob("*.yaml"))
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

    payload = {
        "version": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(entries),
        "entries": entries,
        "index": index,
    }

    OUT_BROWSER.parent.mkdir(parents=True, exist_ok=True)
    with OUT_BROWSER.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_BROWSER.relative_to(ROOT)}: {len(entries)} entries, {len(index)} keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
