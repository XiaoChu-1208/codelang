"""Batch-generate 大白话 explanations for seed terms using Anthropic Claude.

Reads:  tools/seeds/terms.json
Writes: tools/seeds/generated.jsonl  (resumable, one JSON object per line)

After full run, use tools/jsonl_to_yaml.py to merge into dict/*.yaml.

Cost estimate: ~4600 terms / 10 per request = 460 requests, ~200 input + 1500 output tokens each
  Haiku 4.5: $1/MTok in, $5/MTok out → ~$3.5 total

Usage:
  set ANTHROPIC_API_KEY=sk-ant-...
  py tools/gen_explanations.py            # full run
  py tools/gen_explanations.py --sample 10  # only first 10 terms (test prompt)
  py tools/gen_explanations.py --resume   # default; skips terms already in jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "tools" / "seeds"
TERMS_FILE = SEEDS / "terms.json"
OUT_FILE = SEEDS / "generated.jsonl"

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 10
CONCURRENCY = 6
MAX_RETRIES = 4
TIMEOUT = 60

SYSTEM = """你是中文程序员/职场术语翻译大白话专家。给一批词，每个用 1-2 句大白话解释 + 一个具体例句。

输出格式：严格的 JSON 数组，每元素：
{"term":"原词","category":"devterm|jargon|abbr|slang|common","literal":"字面意思（与实际同则空字符串）","meaning":"实际含义。1-2 句，讲清在中文互联网/职场/编程里到底什么意思","example":"具体例句，10-30 字"}

风格规则：
1. 大白话、生动、举具体场景。例如「抓手」→「能下手干活的点。找抓手=找一个能开始推进的具体切入口」，不要说「解决问题的切入点」这种废话
2. 禁用「可以理解为」「在某种意义上」「具有...属性」「指代...」这类抽象表述
3. 例句要具体、有场景，类似「老板说先和产品对齐一下需求」「这个接口必须做幂等，重复点击不能多扣钱」
4. category 判断：
   - devterm: 技术/工程/编程概念（幂等、CAS、熔断、依赖注入、状态机）
   - jargon: 互联网公司高频黑话（对齐、抓手、闭环、复盘、赋能、颗粒度）
   - abbr: 字母缩写（OKR、QPS、SSR、CRUD）
   - slang: 职场/网络俚语（卷、八股、润、摸鱼）
   - common: 在普通中文里就是常用词、没有特殊语境含义。这种情况下 literal/meaning/example 全部留空字符串

5. 只输出 JSON 数组，不要 markdown 围栏 ```、不要任何解释文字、不要前缀后缀"""


def build_user_prompt(items: list[dict]) -> str:
    lines = ["请给以下词逐个输出 JSON 元素，按输入顺序，确保 term 字段与输入一致：\n"]
    for it in items:
        hint = it.get("hint_meaning", "").strip()
        hint_tag = f"  (上游参考: {hint[:80]})" if hint else ""
        lines.append(f"- {it['term']}{hint_tag}")
    lines.append("\n请输出 JSON 数组：")
    return "\n".join(lines)


def call_anthropic(api_key: str, items: list[dict]) -> list[dict]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": MODEL,
        "max_tokens": 4096,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": build_user_prompt(items)}],
    }
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(API_URL, headers=headers, json=body, timeout=TIMEOUT)
            if r.status_code == 429 or r.status_code >= 500:
                backoff = (2 ** attempt) + random.random()
                time.sleep(backoff)
                continue
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            text = data["content"][0]["text"].strip()
            # strip code fences if present
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if m:
                text = m.group(1).strip()
            # find the first '[' and last ']'
            i = text.find("[")
            j = text.rfind("]")
            if i == -1 or j == -1:
                raise RuntimeError(f"no JSON array in response: {text[:300]}")
            arr = json.loads(text[i : j + 1])
            if not isinstance(arr, list):
                raise RuntimeError("response is not a list")
            return arr
        except Exception as e:
            last_err = e
            time.sleep(1.5 ** attempt)
    raise RuntimeError(f"failed after {MAX_RETRIES} retries: {last_err}")


def load_existing() -> set[str]:
    if not OUT_FILE.exists():
        return set()
    done: set[str] = set()
    for line in OUT_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            t = obj.get("term")
            if t:
                done.add(t)
        except Exception:
            continue
    return done


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0, help="only run first N terms (for prompt testing)")
    parser.add_argument("--limit", type=int, default=0, help="cap total terms (0=all)")
    parser.add_argument("--no-resume", action="store_true", help="ignore existing generated.jsonl")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.stderr.write("ANTHROPIC_API_KEY env var not set. Aborting.\n")
        return 2

    terms = json.loads(TERMS_FILE.read_text(encoding="utf-8"))
    done = set() if args.no_resume else load_existing()
    if done:
        print(f"Resuming: {len(done)} terms already generated")

    pending = [t for t in terms if t["term"] not in done]
    if args.sample:
        pending = pending[: args.sample]
    elif args.limit:
        pending = pending[: args.limit]

    if not pending:
        print("Nothing to do.")
        return 0

    batches = [pending[i : i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
    print(f"Will process {len(pending)} terms in {len(batches)} batches (concurrency {CONCURRENCY})")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out_fp = OUT_FILE.open("a", encoding="utf-8")

    ok = 0
    fail = 0
    started = time.perf_counter()

    def worker(batch):
        try:
            results = call_anthropic(api_key, batch)
            return batch, results, None
        except Exception as e:
            return batch, None, e

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futures = [ex.submit(worker, b) for b in batches]
        for n, fut in enumerate(as_completed(futures), 1):
            batch, results, err = fut.result()
            if err:
                fail += len(batch)
                sys.stderr.write(f"[batch {n}/{len(batches)}] FAIL: {err}\n")
                continue
            # Match results by term (LLM might reorder)
            input_terms = {it["term"]: it for it in batch}
            got_terms = set()
            for r in results:
                t = r.get("term")
                if not t:
                    continue
                got_terms.add(t)
                if t not in input_terms:
                    # LLM hallucinated term name; keep it anyway under that name
                    pass
                out_fp.write(json.dumps(r, ensure_ascii=False) + "\n")
                ok += 1
            out_fp.flush()
            missing = [t for t in input_terms if t not in got_terms]
            if missing:
                sys.stderr.write(
                    f"[batch {n}/{len(batches)}] partial; missing {len(missing)}: {missing[:3]}\n"
                )
                fail += len(missing)
            elapsed = time.perf_counter() - started
            rate = (ok + fail) / max(elapsed, 1)
            eta = (len(pending) - ok - fail) / max(rate, 0.001)
            print(
                f"[{n}/{len(batches)}] ok={ok} fail={fail} rate={rate:.1f}/s eta={eta/60:.1f}min"
            )

    out_fp.close()
    print(f"\nDone. ok={ok} fail={fail} in {(time.perf_counter()-started)/60:.1f}min")
    print(f"Output: {OUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
