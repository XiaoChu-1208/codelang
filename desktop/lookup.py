"""Dict lookup with smart selection cleanup + multi-result + ECDICT translation fallback.

Lookup chain (in order):
  1. Local dict (curated, including user.yaml)
  2. Selection cleanup: strip punct → try again
  3. Selection split: split on separators, look up each part
  4. ECDICT translation fallback (if available, marked as 通用翻译)
  5. Miss → caller handles

Threading: callers should treat .lookup_translation() as potentially slow (file IO),
fine to call from main thread for now since ECDICT loads once and is in-memory.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from . import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DICT_JSON = PROJECT_ROOT / "extension-browser" / "dict.json"
USER_YAML = PROJECT_ROOT / "dict" / "user.yaml"
ECDICT_JSON = PROJECT_ROOT / "extension-browser" / "ecdict.json"

# Stripped from start/end of selection before lookup
PUNCT_STRIP = " \t\n\r.,;:!?，。、；：！？\"'`()[]{}<>《》【】「」『』-—_"

# Separators used to split selection into multiple candidate terms
SPLIT_SEPS = re.compile(r"[,，、;；/\\\s]+")


def normalize(s) -> str:
    return str(s or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")


def strip_punct(s: str) -> str:
    return str(s or "").strip(PUNCT_STRIP)


def _edit_dist_le_1(a: str, b: str) -> bool:
    """True if Damerau-Levenshtein(a, b) <= 1.
    Handles: 1 substitution / 1 insertion / 1 deletion / 1 adjacent transposition.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diffs = [i for i in range(la) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        # adjacent transposition (e.g. claude vs cluade)
        if (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and a[diffs[0]] == b[diffs[1]]
            and a[diffs[1]] == b[diffs[0]]
        ):
            return True
        return False
    # length differs by 1: insertion or deletion
    short, long = (a, b) if la < lb else (b, a)
    i = j = 0
    skipped = False
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
        else:
            if skipped:
                return False
            skipped = True
            j += 1
    return True


@dataclass
class Entry:
    term: str
    category: str
    literal: str
    meaning: str
    example: str
    source: str = "local"  # local | user | translation | llm | llm-cache


@dataclass
class LookupResult:
    entries: list[Entry] = field(default_factory=list)
    cleanup: str = ""  # "" | "stripped" | "split"
    raw_query: str = ""

    @property
    def is_hit(self) -> bool:
        return bool(self.entries)


class DictIndex:
    def __init__(self, path: Path = DICT_JSON):
        self.path = path
        self.entries: list[dict] = []
        self.index: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            data = json.load(f)
        self.entries = data.get("entries", [])
        self.index = data.get("index", {})

    def reload(self) -> None:
        self._load()

    def lookup_one(self, query: str) -> Optional[Entry]:
        """Single best match for query (after normalize)."""
        nk = normalize(query)
        if not nk:
            return None
        idx = self.index.get(nk)
        if idx is None:
            return None
        e = self.entries[idx]
        return Entry(
            term=e.get("term", query),
            category=e.get("category", "misc"),
            literal=e.get("literal", ""),
            meaning=e.get("meaning", ""),
            example=e.get("example", ""),
            source="local",
        )

    # Generic basics-level words that show up in nearly every meaning text — they're
    # legitimate dict entries (user can still look them up directly) but suggesting
    # them as drill-down chips just produces noise. Curated by hand.
    _CHIP_BLOCKLIST = frozenset(
        normalize(s) for s in [
            "item", "entry", "element", "value", "type", "name", "label", "tag",
            "index", "format", "data", "list", "array", "object", "string",
            "number", "boolean", "null", "true", "false", "undefined",
            "function", "method", "variable", "constant", "parameter", "argument",
            "module", "package", "library", "framework", "runtime", "ref",
            "input", "output", "request", "response", "query", "command",
            "system", "platform", "application", "server", "client",
            "state", "category",
            # CJK 太常见
            "美", "码", "码农", "中", "技术", "公司", "用户", "代码",
        ]
    )

    def find_referenced_terms(
        self, text: str, exclude_terms: set[str] | None = None, max_n: int = 5
    ) -> list[str]:
        """Scan `text` and return up to `max_n` dict terms that appear in it.

        Used to build the "相关概念" chip row at the bottom of a card so the user
        can drill into terms used in the explanation. Sorted by first appearance.

        Filters:
          - exclude_terms: already-shown terms (avoids loops)
          - _CHIP_BLOCKLIST: too-generic basics that fire in every meaning
          - terms <2 chars are skipped (too noisy)
          - ASCII terms matched case-insensitively with word boundary
          - CJK terms matched as exact substring
        """
        if not text:
            return []
        exclude_norm = {normalize(t) for t in (exclude_terms or set())}
        exclude_norm |= self._CHIP_BLOCKLIST

        text_lower = text.lower()
        found: list[tuple[int, str]] = []  # (position, term)
        seen_norm: set[str] = set(exclude_norm)

        for e in self.entries:
            term = e.get("term", "")
            if len(term) < 2:
                continue
            term_norm = normalize(term)
            if term_norm in seen_norm:
                continue

            # search for the entry's term or any alias in text
            candidates = [term] + list(e.get("aliases") or [])
            best_pos = -1
            best_len = 0
            for cand in candidates:
                is_ascii = cand.isascii() and cand.replace(" ", "").replace("-", "").replace(".", "").isalnum()
                # min length: 3 for ASCII (avoid "VS"/"IT"/"AI" matching too liberally),
                # 2 for CJK (单字汉字有意义但太常见, 双字起步)
                if is_ascii:
                    if len(cand) < 3:
                        continue
                    pos = self._find_ascii_ci(text_lower, cand.lower())
                else:
                    if len(cand) < 2:
                        continue
                    pos = text.find(cand)
                if pos >= 0 and (best_pos < 0 or pos < best_pos):
                    best_pos = pos
                    best_len = len(cand)
            if best_pos >= 0:
                found.append((best_pos, best_len, term))
                seen_norm.add(term_norm)

        # Sort by position. For same/overlapping position, prefer longer matches
        # (so "VS Code" wins over "VS" alias of Visual Studio).
        found.sort(key=lambda t: (t[0], -t[1]))
        # Drop terms whose match position is inside a longer earlier match's range
        kept: list[tuple[int, int, str]] = []
        for pos, length, term in found:
            overlapped = any(
                pos < kp + klen and pos + length > kp
                for kp, klen, _ in kept
            )
            if not overlapped:
                kept.append((pos, length, term))
        return [t for _, _, t in kept[:max_n]]

    @staticmethod
    def _find_ascii_ci(haystack_lower: str, needle_lower: str) -> int:
        """Case-insensitive find requiring word boundary on both ends.
        haystack must already be lowered.
        """
        n = len(needle_lower)
        pos = 0
        while True:
            i = haystack_lower.find(needle_lower, pos)
            if i < 0:
                return -1
            before_ok = i == 0 or not haystack_lower[i - 1].isalnum()
            after = i + n
            after_ok = after >= len(haystack_lower) or not haystack_lower[after].isalnum()
            if before_ok and after_ok:
                return i
            pos = i + 1

    def fuzzy_lookup(self, query: str, max_results: int = 2) -> list[Entry]:
        """Find entries whose normalized key is within edit-distance 1 of query.

        Conservative defaults to avoid false positives:
          - Input must be ASCII and length >= 4 (skip Chinese, skip short inputs like 'pip')
          - Only matches against ASCII keys of length >= 4
          - Single edit distance (sub/ins/del/transposition)
        Returns up to max_results distinct entries, each tagged source='fuzzy'
        with meaning prefixed by 'you mean X?' hint so user sees it's a guess.
        """
        nq = normalize(query)
        if len(nq) < 4 or not nq.isascii() or not nq.isalpha():
            return []

        first = nq[0]
        seen_terms = set()
        out: list[Entry] = []
        for key, idx in self.index.items():
            if abs(len(key) - len(nq)) > 1 or len(key) < 4:
                continue
            if not key.isascii() or not key.isalpha():
                continue
            # Cheap pre-filter: same first char, OR transposition case (first 2 chars swapped)
            if key[0] != first and not (len(key) == len(nq) and key[0] == nq[1] and key[1] == nq[0]):
                continue
            if not _edit_dist_le_1(nq, key):
                continue
            e = self.entries[idx]
            term = e.get("term", "")
            if term in seen_terms or normalize(term) == nq:
                continue
            seen_terms.add(term)
            out.append(
                Entry(
                    term=term,
                    category=e.get("category", "misc"),
                    literal=e.get("literal", ""),
                    meaning=f"（你是不是想查「{term}」？）{e.get('meaning', '')}",
                    example=e.get("example", ""),
                    source="fuzzy",
                )
            )
            if len(out) >= max_results:
                break
        return out

    def smart_lookup(self, query: str, max_entries: int = 3) -> LookupResult:
        """Smart lookup with selection cleanup + multi-result.

        Strategy:
        1. Exact normalized lookup.
        2. Strip surrounding punctuation, retry.
        3. Split on separators (whitespace/comma/etc), look up each token,
           return all distinct hits (up to max_entries).
        """
        result = LookupResult(raw_query=query)
        if not query or not query.strip():
            return result

        # Step 1: exact lookup
        e = self.lookup_one(query)
        if e:
            result.entries.append(e)
            return result

        # Step 2: strip surrounding punctuation
        stripped = strip_punct(query)
        if stripped and stripped != query:
            e = self.lookup_one(stripped)
            if e:
                result.entries.append(e)
                result.cleanup = "stripped"
                return result

        # Step 3: split into tokens
        tokens = [strip_punct(t) for t in SPLIT_SEPS.split(query) if strip_punct(t)]
        if len(tokens) >= 2:
            seen = set()
            for t in tokens:
                e = self.lookup_one(t)
                if e and e.term not in seen:
                    seen.add(e.term)
                    result.entries.append(e)
                    if len(result.entries) >= max_entries:
                        break
            if result.entries:
                result.cleanup = "split"
                return result

        # Step 4: extract ASCII word-like tokens embedded in mixed text
        # (e.g. "和YAML这种" → ["YAML"]; "用React写" → ["React"])
        ascii_tokens = re.findall(r"[A-Za-z][A-Za-z0-9./+_-]{0,30}", query)
        if ascii_tokens:
            seen = set()
            for t in ascii_tokens:
                t_clean = strip_punct(t)
                if not t_clean or t_clean.lower() == normalize(query):
                    continue  # avoid loops on already-tried full query
                e = self.lookup_one(t_clean)
                if e and e.term not in seen:
                    seen.add(e.term)
                    result.entries.append(e)
                    if len(result.entries) >= max_entries:
                        break
            if result.entries:
                result.cleanup = "extracted"
                return result

        # Step 5: fuzzy match (last resort, English only, edit distance 1).
        # Catches typos like "claud"→"claude", "kuberntes"→"kubernetes",
        # also handles "用 figmaa 画图" by fuzzy-matching extracted ASCII tokens.
        # Conservative: only fires when everything else missed.
        fuzzy_candidates = [stripped or query]
        if ascii_tokens:
            for t in ascii_tokens:
                t_clean = strip_punct(t)
                if t_clean and t_clean not in fuzzy_candidates:
                    fuzzy_candidates.append(t_clean)
        seen_terms = set()
        for cand in fuzzy_candidates:
            hits = self.fuzzy_lookup(cand, max_results=2)
            for h in hits:
                if h.term in seen_terms:
                    continue
                seen_terms.add(h.term)
                result.entries.append(h)
                if len(result.entries) >= max_entries:
                    break
            if len(result.entries) >= max_entries:
                break
        if result.entries:
            result.cleanup = "fuzzy"
            return result

        return result

    @property
    def count(self) -> int:
        return len(self.entries)


# ---------- Translation fallback (ECDICT) ----------

class Translator:
    """Lazy loader for ECDICT-derived English→Chinese fallback dictionary.

    Loads only when first lookup_translation() is called, to keep app startup fast.
    Falls back gracefully if ecdict.json is absent.
    """

    def __init__(self, path: Path = ECDICT_JSON):
        self.path = path
        self._dict: Optional[dict[str, str]] = None
        self._lock = threading.Lock()

    def _load_if_needed(self) -> Optional[dict[str, str]]:
        if self._dict is not None:
            return self._dict
        with self._lock:
            if self._dict is not None:
                return self._dict
            if not self.path.exists():
                self._dict = {}
                return self._dict
            try:
                with self.path.open(encoding="utf-8") as f:
                    raw = json.load(f)
                # Normalize keys (lowercase) for O(1) lookup
                normalized = {}
                for k, v in raw.items():
                    nk = normalize(k)
                    if nk and v:
                        normalized[nk] = v
                self._dict = normalized
            except Exception:
                self._dict = {}
            return self._dict

    @property
    def available(self) -> bool:
        return self.path.exists()

    @property
    def count(self) -> int:
        d = self._load_if_needed()
        return len(d) if d else 0

    def lookup(self, query: str) -> Optional[Entry]:
        d = self._load_if_needed()
        if not d:
            return None
        nk = normalize(query)
        if not nk:
            return None
        meaning = d.get(nk)
        if not meaning:
            return None
        # Clean up ECDICT's multi-meaning format (often "n. xxx vt. yyy" or "<br>" separated)
        cleaned = meaning.replace("\\n", " · ").replace("<br>", " · ").strip()
        if len(cleaned) > 200:
            cleaned = cleaned[:200] + "…"
        return Entry(
            term=query,
            category="translation",
            literal="",
            meaning=cleaned,
            example="",
            source="translation",
        )


# ---------- LLM fallback (unchanged from before) ----------

_LLM_LOCK = threading.Lock()

LLM_SYSTEM = """你是中文程序员/职场术语解释器。给一个词，输出 JSON：
{"literal":"字面意思（一句或空）","meaning":"实际含义（1-2 句大白话，讲清在中文互联网/编程/职场语境的实际意思）","example":"具体场景例句"}
规则：
- 只输出 JSON，没有 markdown 围栏、没有解释文字
- 风格要大白话、举具体场景，禁用「在某种意义上」「可以理解为」这类抽象表述
- 如果词没有特别的技术/职场含义，meaning 字段填「通用词，无特殊语境含义」"""


def _parse_llm_json(text: str) -> dict:
    s = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
    if m:
        s = m.group(1).strip()
    i = s.find("{")
    j = s.rfind("}")
    if i == -1 or j == -1:
        raise ValueError("no JSON object in LLM response")
    return json.loads(s[i : j + 1])


def call_anthropic(api_key: str, model: str, term: str, timeout: int = 8) -> dict:
    body = {
        "model": model or "claude-haiku-4-5-20251001",
        "max_tokens": 400,
        "system": LLM_SYSTEM,
        "messages": [{"role": "user", "content": f"解释这个词：{term}"}],
    }
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=timeout,
    )
    if not r.ok:
        raise RuntimeError(f"Anthropic {r.status_code}: {r.text[:200]}")
    data = r.json()
    text = data["content"][0]["text"]
    return _parse_llm_json(text)


def call_openai(api_key: str, model: str, term: str, timeout: int = 8) -> dict:
    body = {
        "model": model or "gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": LLM_SYSTEM},
            {"role": "user", "content": f"解释这个词：{term}"},
        ],
    }
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        json=body,
        timeout=timeout,
    )
    if not r.ok:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:200]}")
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    return _parse_llm_json(text)


def llm_lookup(term: str, cfg: dict) -> Entry:
    """Call LLM; results are cached on disk so we never pay twice for the same word."""
    nk = normalize(term)
    cache = config.load_cache()
    if nk in cache:
        c = cache[nk]
        return Entry(
            term=c.get("term", term),
            category=c.get("category", "llm"),
            literal=c.get("literal", ""),
            meaning=c.get("meaning", ""),
            example=c.get("example", ""),
            source="llm-cache",
        )

    if not cfg.get("api_key"):
        raise RuntimeError("未配置 API key")

    provider = cfg.get("provider", "anthropic")
    model = cfg.get("model", "")
    if provider == "openai":
        parsed = call_openai(cfg["api_key"], model, term)
    else:
        parsed = call_anthropic(cfg["api_key"], model, term)

    entry_dict = {
        "term": term,
        "category": "llm",
        "literal": (parsed.get("literal") or "").strip(),
        "meaning": (parsed.get("meaning") or "").strip(),
        "example": (parsed.get("example") or "").strip(),
    }
    with _LLM_LOCK:
        cache = config.load_cache()
        cache[nk] = entry_dict
        config.save_cache(cache)

    return Entry(source="llm", **entry_dict)


# ---------- User dict additions ----------

_USER_LOCK = threading.Lock()


def append_user_entry(term: str, meaning: str, example: str = "", category: str = "user") -> None:
    """Append a user-curated entry to dict/user.yaml. Caller should reload dict afterwards."""
    USER_YAML.parent.mkdir(parents=True, exist_ok=True)

    def yaml_escape(s: str) -> str:
        if not s:
            return '""'
        if any(c in s for c in ':#&*!|>%@`"\'[]{},') or s.startswith(" ") or s.endswith(" "):
            return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return s

    block_lines = [
        f"- term: {yaml_escape(term)}",
        f"  category: {category}",
        f"  meaning: {yaml_escape(meaning)}",
    ]
    if example:
        block_lines.append(f"  example: {yaml_escape(example)}")
    block = "\n".join(block_lines) + "\n\n"

    with _USER_LOCK:
        if not USER_YAML.exists():
            USER_YAML.write_text("# 用户自建词条（codelang 内自动追加）\n\n", encoding="utf-8")
        with USER_YAML.open("a", encoding="utf-8") as f:
            f.write(block)


def rebuild_dict_json() -> tuple[bool, str]:
    """Run build_dict.py in-process to regenerate dict.json. Returns (ok, message)."""
    import subprocess
    import sys

    script = PROJECT_ROOT / "tools" / "build_dict.py"
    if not script.exists():
        return False, f"build_dict.py not found at {script}"
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        if proc.returncode != 0:
            return False, f"build failed: {proc.stderr[:200] or proc.stdout[:200]}"
        return True, (proc.stdout or "").strip().split("\n")[-1]
    except Exception as e:
        return False, f"build error: {e}"
