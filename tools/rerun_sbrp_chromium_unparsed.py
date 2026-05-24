import argparse
import asyncio
import contextlib
import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src import prompt, request

EVAL_SPEC = importlib.util.spec_from_file_location("repo_eval", ROOT / "eval.py")
repo_eval = importlib.util.module_from_spec(EVAL_SPEC)
EVAL_SPEC.loader.exec_module(repo_eval)

BASE_RESULT = ROOT / "results" / "SBRP_Chromium_expertise_test.json"
RERUN_NAME = "SBRP_Chromium_expertise_test_unparsed_rerun"
MERGED_NAME = "SBRP_Chromium_expertise_test_merged"

STRICT_SUFFIX = """

STRICT OUTPUT REQUIREMENT:
- Do not explain.
- Output exactly one line, and it MUST be one of:
Final answer: SBR
Final answer: NBR
"""


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def is_unparsed(item):
    content = repo_eval.response_content(item.get("response", {}))
    pred = repo_eval.extract_prediction(content)
    normalized = repo_eval.normalize_prediction(pred, "SBRP", "Chromium")
    return str(normalized) not in {"0", "1"}


def strict_prompt_item(item):
    stored_prompt = item.get("prompt", [])
    if isinstance(stored_prompt, dict) and "messages" in stored_prompt:
        messages = stored_prompt["messages"]
    else:
        messages = stored_prompt
    patched = {
        "id": item["id"],
        "ground_truth": item["ground_truth"],
        "prompt": [dict(message) for message in messages],
    }
    content = patched["prompt"][-1]["content"].rstrip()
    marker = "Answer: Let's think step-by-step to reach the right conclusion,"
    if marker in content:
        content = content.split(marker, 1)[0].rstrip()
    patched["prompt"][-1]["content"] = content + STRICT_SUFFIX
    return patched


def build_unparsed_prompts(limit=None):
    base = load_json(BASE_RESULT)
    unparsed = [strict_prompt_item(item) for item in base if is_unparsed(item)]
    if limit is not None:
        unparsed = unparsed[:limit]
    return unparsed


async def run(args):
    data = build_unparsed_prompts(args.limit)
    print(f"unparsed_to_rerun={len(data)}")
    if args.dry_run:
        if data:
            print(f"first_id={data[0]['id']} ground_truth={data[0]['ground_truth']}")
            print(data[0]["prompt"][-1]["content"][-600:])
        return

    await run_direct(args, data)


async def run_direct(args, data):
    rerun_path = ROOT / "results" / f"{RERUN_NAME}.json"
    existing = load_json(rerun_path) if rerun_path.exists() else []
    existing = [item for item in existing if isinstance(item, dict) and not is_unparsed(item)]
    existing_ids = {str(item.get("id")) for item in existing}
    pending = [item for item in data if str(item.get("id")) not in existing_ids]
    print(f"Skipping {len(existing_ids)} existing results; {len(pending)} requests remaining")
    if not pending:
        return

    api_key = request.resolve_api_key(args.api_key, args.api_url)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=args.timeout, connect=20, sock_connect=20, sock_read=args.timeout)
    semaphore = asyncio.Semaphore(args.max_concurrent_requests)
    lock = asyncio.Lock()
    results = list(existing)
    completed = 0
    last_save = time.time()

    async def save(force=False):
        nonlocal last_save
        if not force and completed % args.save_every != 0 and time.time() - last_save < 60:
            return
        write_json(rerun_path, results)
        last_save = time.time()

    async def call_one(session, item):
        payload = request.build_chat_request_payload(
            model=args.model,
            messages=item["prompt"],
            temperature=0,
            choices=1,
            max_token=args.response_max_token or args.max_token,
            request_url=args.api_url,
        )
        last_response = {}
        for attempt in range(1, args.max_attempts + 1):
            try:
                async with semaphore:
                    async with session.post(args.api_url, headers=headers, json=payload) as resp:
                        text = await resp.text()
                try:
                    last_response = json.loads(text)
                except json.JSONDecodeError:
                    lines = text.strip().splitlines()
                    last_response = json.loads(lines[0]) if lines else {}
                if isinstance(last_response, dict) and "error" in last_response:
                    await asyncio.sleep(min(30, attempt * 2))
                    continue
                return {
                    "id": item["id"],
                    "ground_truth": item["ground_truth"],
                    "prompt": payload,
                    "response": request._json_safe(last_response),
                }
            except Exception as exc:
                last_response = {"error": str(exc)}
                await asyncio.sleep(min(30, attempt * 2))
        return {
            "id": item["id"],
            "ground_truth": item["ground_truth"],
            "prompt": payload,
            "response": request._json_safe(last_response),
        }

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [asyncio.create_task(call_one(session, item)) for item in pending]
        for future in asyncio.as_completed(tasks):
            result = await future
            async with lock:
                results.append(result)
                completed += 1
                if completed % 25 == 0 or completed == len(pending):
                    parsed = 0 if is_unparsed(result) else 1
                    print(f"completed={completed}/{len(pending)} last_id={result['id']} last_parseable={parsed}")
                await save()
    write_json(rerun_path, results)


def merge(args):
    base = load_json(BASE_RESULT)
    rerun_path = ROOT / "results" / f"{RERUN_NAME}.json"
    rerun = load_json(rerun_path) if rerun_path.exists() else []
    replacement_by_id = {}
    parseable = 0
    for item in rerun:
        if not isinstance(item, dict):
            continue
        if not is_unparsed(item):
            parseable += 1
            replacement_by_id[str(item.get("id"))] = item

    merged = []
    replaced = 0
    for item in base:
        key = str(item.get("id"))
        if key in replacement_by_id:
            merged.append(replacement_by_id[key])
            replaced += 1
        else:
            merged.append(item)

    out = ROOT / "results" / f"{MERGED_NAME}.json"
    write_json(out, merged)
    print(f"rerun_rows={len(rerun)} parseable={parseable} replaced={replaced} saved={out.relative_to(ROOT)}")
    evaluate_file(out)


def evaluate_file(path):
    data = load_json(path)
    for item in data:
        item["task"] = "SBRP"
        item["dataset"] = "Chromium"
    with contextlib.redirect_stdout(io.StringIO()):
        metrics = repo_eval.evaluate_classification(data, "SBRP", "Chromium")
    print(json.dumps(metrics, indent=2))


def status():
    base = load_json(BASE_RESULT)
    rerun_path = ROOT / "results" / f"{RERUN_NAME}.json"
    rerun = load_json(rerun_path) if rerun_path.exists() else []
    base_unparsed = sum(1 for item in base if is_unparsed(item))
    rerun_parseable = sum(1 for item in rerun if not is_unparsed(item))
    print(f"base_total={len(base)} base_unparsed={base_unparsed}")
    print(f"rerun_total={len(rerun)} rerun_parseable={rerun_parseable} rerun_unparsed={len(rerun)-rerun_parseable}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "run", "merge"])
    parser.add_argument("--api_url", default="https://ollama.com/api/chat")
    parser.add_argument("--api_key", default=None)
    parser.add_argument("--model", default="deepseek-v4-flash:cloud")
    parser.add_argument("--max_requests_per_minute", type=float, default=10)
    parser.add_argument("--max_tokens_per_minute", type=float, default=1000000)
    parser.add_argument("--max_concurrent_requests", type=int, default=2)
    parser.add_argument("--max_attempts", type=int, default=10)
    parser.add_argument("--max_token", type=int, default=8000)
    parser.add_argument("--response_max_token", type=int, default=512)
    parser.add_argument("--save_every", type=int, default=200)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry_run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.action == "status":
        status()
    elif args.action == "merge":
        merge(args)
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
