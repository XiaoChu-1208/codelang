"""Extract candidate terms from upstream seed files.

Sources in tools/seeds/:
- jargon_mcsrainbow.md     : Chinese jargon, comma-separated inside ``` code blocks
- jargon_mcsrainbow_abbr.md: "ABBR - Expansion 中文" lines, inside ``` code blocks
- cs_earseyesmouth.md      : Markdown tables `| Word | Meaning |`

Output: tools/seeds/terms.json with shape:
  [{term, source, category_hint, hint_meaning}]

We DO NOT copy upstream explanations into our dict. We only carry a small
hint_meaning for the LLM generation step to anchor it.

Run: py tools/extract_terms.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "tools" / "seeds"
OUT = SEEDS / "terms.json"

# Skip very short / non-meaningful terms.
SKIP_TERMS = {"OK", "PR", "OT", "PT", "FT", "FW", "CC", "FAM", "M8", "B4"}


def parse_jargon_mcsrainbow(text: str) -> list[dict]:
    """Find code blocks, split by comma/whitespace, treat each token as a term."""
    out: list[dict] = []
    seen: set[str] = set()
    blocks = re.findall(r"```(?:markdown)?\n(.*?)\n```", text, re.DOTALL)
    for block in blocks:
        # Skip blocks that look like "term - explanation" lines (we'll handle those separately if any)
        if re.search(r"^\S+ - ", block, re.MULTILINE):
            continue
        # Split on Chinese/ASCII comma, whitespace, newlines
        tokens = re.split(r"[,，\s]+", block)
        for t in tokens:
            t = t.strip().rstrip("。.")
            if not t or t in seen:
                continue
            # Want pure Chinese tokens of 2-6 chars
            if not re.match(r"^[一-鿿]{2,6}$", t):
                continue
            seen.add(t)
            out.append(
                {
                    "term": t,
                    "source": "mcsrainbow/chinese-internet-jargon",
                    "category_hint": "jargon",
                    "hint_meaning": "",
                }
            )
    return out


ABBR_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9/&\.\:\-]{0,15})\s*-\s*(.+)$")


def parse_abbr(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    blocks = re.findall(r"```(?:markdown)?\n(.*?)\n```", text, re.DOTALL)
    for block in blocks:
        for line in block.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = ABBR_LINE.match(line)
            if not m:
                continue
            term = m.group(1).strip().rstrip(":.")
            hint = m.group(2).strip()
            if not term or term in seen or term in SKIP_TERMS:
                continue
            if len(term) < 2:
                continue
            seen.add(term)
            cat = "abbr"
            out.append(
                {
                    "term": term,
                    "source": "mcsrainbow/chinese-internet-jargon",
                    "category_hint": cat,
                    "hint_meaning": hint[:120],
                }
            )
    return out


TABLE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$")


def parse_cs_terms(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for raw in text.split("\n"):
        line = raw.strip()
        if not line.startswith("|"):
            continue
        m = TABLE_ROW.match(line)
        if not m:
            continue
        term = m.group(1).strip()
        hint = m.group(2).strip()
        if term.lower() in {"word", "------", "term"}:
            continue
        if set(term) <= {"-", " "}:
            continue
        if not term or term in seen:
            continue
        # Strip simple footnote markers like "<sup>1</sup>"
        hint_clean = re.sub(r"<sup>.*?</sup>", "", hint).strip()
        # Filter out trivially short or obviously broken rows
        if len(term) > 60 or len(term) < 2:
            continue
        seen.add(term)
        # Category guess
        cat = "devterm"
        if re.match(r"^[A-Z]{2,6}$", term):
            cat = "abbr"
        out.append(
            {
                "term": term,
                "source": "EarsEyesMouth/computerese-cross-references",
                "category_hint": cat,
                "hint_meaning": hint_clean[:160],
            }
        )
    return out


def main() -> int:
    files = {
        "jargon_mcsrainbow.md": parse_jargon_mcsrainbow,
        "jargon_mcsrainbow_abbr.md": parse_abbr,
        "cs_earseyesmouth.md": parse_cs_terms,
    }
    all_terms: list[dict] = []
    for fname, parser in files.items():
        p = SEEDS / fname
        if not p.exists():
            print(f"SKIP missing {fname}")
            continue
        text = p.read_text(encoding="utf-8")
        items = parser(text)
        print(f"{fname}: {len(items)} terms")
        all_terms.extend(items)

    # Global dedupe by lowercased term
    by_key: dict[str, dict] = {}
    for item in all_terms:
        k = item["term"].lower().strip()
        if k in by_key:
            # Keep entry with a hint if we have one
            if not by_key[k]["hint_meaning"] and item["hint_meaning"]:
                by_key[k] = item
            continue
        by_key[k] = item

    # Drop terms we already have in our existing YAML dict (avoid re-generating)
    existing: set[str] = set()
    for yf in (ROOT / "dict").glob("*.yaml"):
        for line in yf.read_text(encoding="utf-8").split("\n"):
            m = re.match(r"^- term:\s*(.+)$", line.strip())
            if m:
                existing.add(m.group(1).strip().lower())
            m2 = re.match(r"^\s*aliases:\s*\[(.+)\]", line)
            if m2:
                for a in m2.group(1).split(","):
                    existing.add(a.strip().strip("\"'").lower())

    kept = [v for k, v in by_key.items() if k not in existing]
    skipped = len(by_key) - len(kept)

    OUT.write_text(
        json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nTotal unique: {len(by_key)}")
    print(f"Already in our dict: {skipped}")
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(kept)} candidate terms")
    by_cat: dict[str, int] = {}
    for it in kept:
        by_cat[it["category_hint"]] = by_cat.get(it["category_hint"], 0) + 1
    print(f"By category: {by_cat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
