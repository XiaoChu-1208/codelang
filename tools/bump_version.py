"""Bump the codelang version across the 7 places it appears.

Single source of truth: <repo>/VERSION (one line, e.g. "0.1.3").

Usage:
    py tools/bump_version.py                  # patch bump (0.1.0 -> 0.1.1)
    py tools/bump_version.py --patch          # explicit patch bump
    py tools/bump_version.py --minor          # 0.1.5 -> 0.2.0
    py tools/bump_version.py --major          # 0.2.7 -> 1.0.0
    py tools/bump_version.py 1.2.3            # set explicitly
    py tools/bump_version.py --show           # just print current

Updates:
    VERSION
    installer/codelang.iss          (#define MyAppVersion)
    README.md                       (JSON-LD softwareVersion + download link)
    docs/index.html                 (JSON-LD softwareVersion)
    CITATION.cff                    (version: "...")
    extension-browser/manifest.json (browser-extension version)

Does NOT touch requirements.txt's `resvg-py>=0.1.0` — that's a dependency
version, not ours. The script greps for our exact current string and replaces
that, so unrelated 0.1.0 occurrences are safe.

installer/build.bat reads the version dynamically from VERSION, so it
doesn't need string-replacement here.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"


def read_current() -> str:
    if not VERSION_FILE.exists():
        sys.exit(f"VERSION file missing: {VERSION_FILE}")
    v = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        sys.exit(f"VERSION content not semver x.y.z: {v!r}")
    return v


def bump(current: str, kind: str) -> str:
    major, minor, patch = (int(x) for x in current.split("."))
    if kind == "patch":
        patch += 1
    elif kind == "minor":
        minor += 1
        patch = 0
    elif kind == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise ValueError(kind)
    return f"{major}.{minor}.{patch}"


# (relative path, list of (find, replace_template)) — replace_template uses
# {OLD} and {NEW} as placeholders.  We deliberately keep each pattern narrow so
# we only touch the version strings we own, not unrelated 0.1.0 occurrences.
def edits_for(old: str, new: str) -> list[tuple[str, str, str]]:
    """Return [(path, find_pattern, replacement)] for each known reference."""
    return [
        # installer/codelang.iss:  #define MyAppVersion       "0.1.0"
        (
            "installer/codelang.iss",
            f'#define MyAppVersion       "{old}"',
            f'#define MyAppVersion       "{new}"',
        ),
        # README.md:  "softwareVersion": "0.1.0",   (JSON-LD)
        (
            "README.md",
            f'"softwareVersion": "{old}"',
            f'"softwareVersion": "{new}"',
        ),
        # README.md:  下载 codelang-0.1.0-setup.exe
        (
            "README.md",
            f"codelang-{old}-setup.exe",
            f"codelang-{new}-setup.exe",
        ),
        # docs/index.html:  "softwareVersion": "0.1.0",
        (
            "docs/index.html",
            f'"softwareVersion": "{old}"',
            f'"softwareVersion": "{new}"',
        ),
        # CITATION.cff:  version: "0.1.0"
        (
            "CITATION.cff",
            f'version: "{old}"',
            f'version: "{new}"',
        ),
        # extension-browser/manifest.json:  "version": "0.1.0",
        (
            "extension-browser/manifest.json",
            f'"version": "{old}"',
            f'"version": "{new}"',
        ),
    ]


def apply_edits(old: str, new: str) -> list[str]:
    """Apply all edits. Returns list of files actually changed."""
    changed: list[str] = []
    misses: list[str] = []
    for rel, find, repl in edits_for(old, new):
        p = ROOT / rel
        if not p.exists():
            misses.append(f"{rel} (file missing)")
            continue
        text = p.read_text(encoding="utf-8")
        if find not in text:
            misses.append(f"{rel} (pattern not found: {find!r})")
            continue
        new_text = text.replace(find, repl)
        if new_text == text:
            continue
        p.write_text(new_text, encoding="utf-8")
        changed.append(rel)
    if misses:
        print("[warn] some references were not updated:")
        for m in misses:
            print(f"  - {m}")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bump codelang version.")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--patch", action="store_true", help="bump patch (default)")
    g.add_argument("--minor", action="store_true", help="bump minor, reset patch")
    g.add_argument("--major", action="store_true", help="bump major, reset minor+patch")
    g.add_argument("--show", action="store_true", help="just print current version")
    parser.add_argument("explicit", nargs="?", help="set explicit version like 1.2.3")
    args = parser.parse_args(argv)

    current = read_current()

    if args.show:
        print(current)
        return 0

    if args.explicit:
        if not re.fullmatch(r"\d+\.\d+\.\d+", args.explicit):
            sys.exit(f"explicit version must be x.y.z, got {args.explicit!r}")
        new = args.explicit
    elif args.minor:
        new = bump(current, "minor")
    elif args.major:
        new = bump(current, "major")
    else:
        new = bump(current, "patch")

    if new == current:
        print(f"version unchanged: {current}")
        return 0

    changed = apply_edits(current, new)
    VERSION_FILE.write_text(new + "\n", encoding="utf-8")
    print(f"version: {current} -> {new}")
    print(f"updated {len(changed)} files:")
    for c in changed:
        print(f"  + {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
