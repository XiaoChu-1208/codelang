"""Merge tools/seeds/generated.jsonl into dict/*.yaml.

- Skips entries with category=='common' (they're just普通词, no jargon meaning).
- Skips entries with empty meaning.
- Splits by category into dict/devterm.yaml / jargon.yaml / abbr.yaml / slang.yaml.
- Existing user-curated YAML entries are kept; only new terms are appended.

Usage:
  py tools/jsonl_to_yaml.py            # dry run, prints stats
  py tools/jsonl_to_yaml.py --write    # actually write YAMLs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("Need PyYAML. Install:  py -m pip install pyyaml\n")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "tools" / "seeds"
JSONL = SEEDS / "generated.jsonl"
DICT_DIR = ROOT / "dict"


def yaml_escape(s: str) -> str:
    # Use double-quoted strings if there's any special char; escape backslashes/quotes.
    if not s:
        return '""'
    if re.search(r'[:\[\]{},#&*!|>\'"%@`]', s) or s.startswith(" ") or s.endswith(" "):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def render_entry(e: dict) -> str:
    lines = []
    lines.append(f"- term: {yaml_escape(e['term'])}")
    aliases = e.get("aliases") or []
    if aliases:
        lines.append(
            "  aliases: [" + ", ".join(yaml_escape(a) for a in aliases) + "]"
        )
    lines.append(f"  category: {e['category']}")
    if e.get("literal"):
        lines.append(f"  literal: {yaml_escape(e['literal'])}")
    lines.append(f"  meaning: {yaml_escape(e['meaning'])}")
    if e.get("example"):
        lines.append(f"  example: {yaml_escape(e['example'])}")
    return "\n".join(lines)


def existing_terms_for(cat_file: Path) -> set[str]:
    if not cat_file.exists():
        return set()
    out: set[str] = set()
    for line in cat_file.read_text(encoding="utf-8").split("\n"):
        m = re.match(r"^- term:\s*(.+)$", line.strip())
        if m:
            t = m.group(1).strip().strip('"').strip("'")
            out.add(t.lower())
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="actually append to YAML files")
    args = parser.parse_args()

    if not JSONL.exists():
        sys.stderr.write(f"Missing {JSONL}\n")
        return 1

    entries: list[dict] = []
    seen = set()
    stats = {"total": 0, "common": 0, "empty": 0, "dup_in_jsonl": 0, "kept": 0}
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        stats["total"] += 1
        t = obj.get("term", "").strip()
        if not t:
            continue
        if t.lower() in seen:
            stats["dup_in_jsonl"] += 1
            continue
        seen.add(t.lower())
        cat = (obj.get("category") or "").strip()
        if cat == "common":
            stats["common"] += 1
            continue
        meaning = (obj.get("meaning") or "").strip()
        if not meaning:
            stats["empty"] += 1
            continue
        entries.append(
            {
                "term": t,
                "category": cat if cat in {"devterm", "jargon", "abbr", "slang"} else "jargon",
                "literal": (obj.get("literal") or "").strip(),
                "meaning": meaning,
                "example": (obj.get("example") or "").strip(),
            }
        )

    # Bucket by category file
    by_cat: dict[str, list[dict]] = {"devterm": [], "jargon": [], "abbr": [], "slang": []}
    skipped_existing = 0
    cat_existing = {
        c: existing_terms_for(DICT_DIR / f"{c}.yaml") for c in by_cat
    }
    # also union all existing terms so a new term doesn't clash across files
    all_existing = set().union(*cat_existing.values())

    for e in entries:
        if e["term"].lower() in all_existing:
            skipped_existing += 1
            continue
        by_cat[e["category"]].append(e)
        stats["kept"] += 1

    print(f"Total JSONL rows: {stats['total']}")
    print(f"  common (skipped): {stats['common']}")
    print(f"  empty meaning  : {stats['empty']}")
    print(f"  duplicate rows : {stats['dup_in_jsonl']}")
    print(f"  already in YAML: {skipped_existing}")
    print(f"  new to add     : {stats['kept']}")
    print(f"  By category    : { {k: len(v) for k, v in by_cat.items()} }")

    if not args.write:
        print("\n(dry run; use --write to append)")
        # show 5 samples
        for cat, lst in by_cat.items():
            if not lst:
                continue
            print(f"\n--- sample for {cat} ---")
            for e in lst[:3]:
                print(render_entry(e))
                print()
        return 0

    DICT_DIR.mkdir(exist_ok=True)
    for cat, lst in by_cat.items():
        if not lst:
            continue
        path = DICT_DIR / f"{cat}.yaml"
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n# --- auto-generated batch ({len(lst)} entries) ---\n")
            for e in lst:
                f.write(render_entry(e))
                f.write("\n\n")
        print(f"Appended {len(lst)} entries to {path.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
