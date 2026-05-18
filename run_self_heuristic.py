"""
Self-Heuristic Pipeline

Fully automated 2-round self-heuristic approach from the paper:
- Round 1: Extract classification rules from training/probe examples
- Round 2: Use extracted rules for classification on test set

Usage:
    # CVSS tasks
    python run_self_heuristic.py --task cvss --dataset AV --testNum 0

    # SBRP tasks
    python run_self_heuristic.py --task sbrp --dataset Chromium --testNum 0

    # Evaluate
    python eval.py --result_file results/cvss/cvss_AV_xxx_self-heuristic_test.json --task cvss --dataset AV
"""

import os
import sys
import json
import asyncio
import argparse
import aiohttp
from dotenv import load_dotenv

# Load .env file if it exists
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

# Add project root and src to path
project_root = os.path.dirname(__file__)
src_dir = os.path.join(project_root, 'src')
sys.path.insert(0, project_root)
sys.path.insert(0, src_dir)

from src import prompt, request


def parse_args():
    parser = argparse.ArgumentParser(description='Self-Heuristic pipeline')
    parser.add_argument('--task', type=str, default='cvss',
                       choices=['cvss', 'sbrp', 'SBRP', 'APCA', 'apca'],
                       help='Task name')
    parser.add_argument('--dataset', type=str, required=True,
                       help='Dataset name (AV/AC/PR/UI for cvss, Ambari/Camel/Chromium/Derby/Wicket for sbrp)')
    parser.add_argument('--data_root', type=str,
                       default=os.path.join(os.path.dirname(__file__), 'data'),
                       help='Root directory for data files')
    parser.add_argument('--result_root', type=str,
                       default=os.path.join(os.path.dirname(__file__), 'results'),
                       help='Root directory for results')
    parser.add_argument('--testNum', type=int, default=0,
                       help='Number of test samples (0 = all)')
    parser.add_argument('--model', type=str, default='gpt-4-0314',
                       help='Model name')
    parser.add_argument('--max_token', type=int, default=8000,
                       help='Max tokens in response')
    parser.add_argument('--api_url', type=str,
                       default='https://api.openai.com/v1/chat/completions',
                       help='Chat completions API endpoint URL')
    parser.add_argument('--api_key', type=str, default=None,
                       help='API key (or set OPENAI_API_KEY/MINIMAX_API_KEY/OLLAMA_API_KEY env var)')
    parser.add_argument('--n_samples_per_class', type=int, default=30,
                       help='Number of training samples per class for heuristics extraction')
    parser.add_argument('--max_requests_per_minute', type=float, default=10,
                       help='Max API requests per minute during classification')
    parser.add_argument('--max_tokens_per_minute', type=float, default=1000000,
                       help='Max API tokens per minute during classification')
    parser.add_argument('--max_attempts', type=int, default=10,
                       help='Max retry attempts per request')
    parser.add_argument('--max_concurrent_requests', type=int, default=2,
                       help='Maximum in-flight API requests during classification')
    parser.add_argument('--result_file_name', type=str, default=None,
                       help='Optional result file name without .json')
    parser.add_argument('--dry_run', action='store_true',
                       help='Build prompts and exit without API calls')
    return parser.parse_args()


async def call_chat_api(api_url, api_key, model, messages, max_tokens=8000, temperature=0):
    """Make a single chat completion API call."""
    api_key = request.resolve_api_key(api_key, api_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = request.build_chat_request_payload(
        model=model,
        messages=messages,
        temperature=temperature,
        max_token=max_tokens,
        request_url=api_url,
    )

    timeout = aiohttp.ClientTimeout(total=300, connect=30, sock_connect=30, sock_read=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(api_url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"API call failed with status {resp.status}: {error_text}")

            text = await resp.text()
            # Ollama API returns NDJSON (newline-delimited JSON) when streaming
            # For non-streaming, it's a single JSON object
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                # Handle NDJSON format - take first line
                lines = text.strip().split('\n')
                result = json.loads(lines[0])

            if 'choices' in result and result['choices']:
                return result['choices'][0].get('message', {}).get('content')
            elif 'message' in result:
                return result['message'].get('content')
            elif 'response' in result:
                return result['response']
            return None


async def run_self_heuristic_pipeline(args):
    """
    Fully automated 2-round self-heuristic pipeline:
    1. Extract heuristics from probe/training data via chat completion API
    2. Use extracted heuristics to classify test samples
    """
    print(f"\n{'='*60}")
    args.task = prompt.normalize_task_name(args.task)
    print(f"SELF-HEURISTIC PIPELINE ({args.model})")
    print(f"{'='*60}")
    print(f"Task: {args.task}, Dataset: {args.dataset}")

    api_key = args.api_key

    # ============================================================
    # ROUND 1: Extract Heuristics
    # ============================================================
    print(f"\n{'='*60}")
    print(f"ROUND 1: Extracting Heuristics...")
    print(f"{'='*60}")

    # Get heuristics extraction prompt
    heuristics_result = prompt.extract_heuristics(
        root=args.data_root,
        task=args.task,
        dataset=args.dataset,
        method='self-heuristic',
        n_samples_per_class=args.n_samples_per_class
    )

    # Get task_type from heuristics_result
    task_type = heuristics_result.get('task_type', 'CVSS')

    # Check if cached heuristics exist
    heuristics_file = os.path.join(args.result_root, 'heuristics', f'{args.task}_{args.dataset}_heuristics.json')
    extracted_text = None

    if os.path.exists(heuristics_file):
        print(f"\n[CACHE] Found existing heuristics file: {heuristics_file}")
        with open(heuristics_file, 'r', encoding='utf-8') as f:
            cached = json.load(f)
            extracted_text = cached.get('extracted_heuristics')
            task_type = cached.get('task_type', task_type)
            # Validate cached heuristics matches current model
            if cached.get('model') != args.model:
                print(f"[CACHE] Model mismatch ({cached.get('model')} != {args.model}), re-extracting...")
                extracted_text = None
            elif cached.get('n_samples_per_class') != args.n_samples_per_class:
                print(f"[CACHE] Sample count mismatch, re-extracting...")
                extracted_text = None

    # Extract heuristics if not cached
    if not extracted_text:
        extraction_prompt = heuristics_result['heuristics']
        print(f"\nExtraction prompt created ({len(extraction_prompt)} chars)")
        print(f"Preview:\n{extraction_prompt[:300]}...")

        if args.dry_run:
            print("\nDry run complete after extraction prompt build. No API calls made.")
            return

        # Call chat API to extract heuristics
        messages = [{"role": "user", "content": extraction_prompt}]
        print(f"\nCalling API for heuristics extraction...")

        extracted_text = await call_chat_api(
            api_url=args.api_url,
            api_key=api_key,
            model=args.model,
            messages=messages,
            max_tokens=args.max_token,
            temperature=0
        )

        if not extracted_text:
            raise Exception("Failed to extract heuristics from API")

        print(f"\nExtracted heuristics ({len(extracted_text)} chars):")
        print(f"{extracted_text[:500]}...")

        # Save extracted heuristics
        os.makedirs(os.path.join(args.result_root, 'heuristics'), exist_ok=True)
        with open(heuristics_file, 'w', encoding='utf-8') as f:
            json.dump({
                'task': args.task,
                'dataset': args.dataset,
                'model': args.model,
                'task_type': task_type,
                'n_samples_per_class': args.n_samples_per_class,
                'extraction_prompt': extraction_prompt,
                'extracted_heuristics': extracted_text,
                'class_samples': heuristics_result['class_samples'],
                'class_names': heuristics_result['class_names']
            }, f, indent=2, ensure_ascii=False)
        print(f"Saved heuristics to: {heuristics_file}")
    else:
        print(f"[CACHE] Using cached heuristics ({len(extracted_text)} chars)")
        print(f"{extracted_text[:500]}...")

    # ============================================================
    # ROUND 2: Classify Test Samples
    # ============================================================
    print(f"\n{'='*60}")
    print(f"ROUND 2: Classifying Test Samples with Heuristics")
    print(f"{'='*60}")

    # Build system prompt with extracted heuristics
    system_prompt = prompt.generate_self_heuristic_system_prompt(
        dataset=args.dataset,
        heuristics_text=extracted_text,
        cot_instruction=True,
        task_type=task_type
    )
    print(f"\nBuilt system prompt ({len(system_prompt)} chars)")

    # Generate prompts for test set
    test_count = args.testNum if args.testNum > 0 else 999999999
    prompts = prompt.generate_prompt(
        root=args.data_root,
        task=args.task,
        dataset=args.dataset,
        method='self-heuristic',
        max_tokens=args.max_token,
        TEST='test',
        testNum=test_count,
        extracted_heuristics={'system_prompt': system_prompt}
    )

    print(f"Generated {len(prompts)} prompts for classification")

    if args.dry_run:
        preview = prompts[0] if prompts else None
        if preview:
            print(f"Dry run preview id={preview['id']} ground_truth={preview['ground_truth']}")
            print(f"Messages: {len(preview['prompt'])}")
        print("Dry run complete. No API calls made.")
        return

    result_file_name = args.result_file_name or f"{args.task}_{args.dataset}_self-heuristic_test"
    result_file_path = os.path.join(args.result_root, args.task)

    # Run API requests
    await request.async_api_requests(
        max_requests_per_minute=args.max_requests_per_minute,
        max_tokens_per_minute=args.max_tokens_per_minute,
        request_url=args.api_url,
        api_key=api_key,
        root_path=args.data_root,
        result_file_path=result_file_path,
        result_file_name=result_file_name,
        task=args.task,
        dataset=args.dataset,
        model=args.model,
        testNum=len(prompts),
        method='self-heuristic',
        max_token=args.max_token,
        max_attempts=args.max_attempts,
        max_concurrent_requests=args.max_concurrent_requests,
        temperature=0,
        choices=1,
        data=prompts,
    )

    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE!")
    print(f"{'='*60}")
    result_json_path = os.path.join(result_file_path, result_file_name + ".json")
    print(f"Results saved to: {result_json_path}")
    print(f"Heuristics saved to: {heuristics_file}")
    print(f"\nTo evaluate:")
    print(f"  python eval.py --result_file {result_json_path} --task {args.task} --dataset {args.dataset}")


async def main():
    args = parse_args()
    await run_self_heuristic_pipeline(args)


if __name__ == '__main__':
    asyncio.run(main())
