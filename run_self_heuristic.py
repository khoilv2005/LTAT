"""
Self-Heuristic Pipeline for CVSS Tasks

Fully automated 2-round self-heuristic approach from the paper:
- Round 1: Extract classification rules from training/probe examples (via MiniMax API)
- Round 2: Use extracted rules for classification on test set

Usage:
    python run_self_heuristic.py --task cvss --dataset AV
    python eval.py --result_file results/cvss_AV_self-heuristic_test.json --task cvss --dataset AV
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
    parser = argparse.ArgumentParser(description='Self-Heuristic pipeline for CVSS tasks (fully automated)')
    parser.add_argument('--task', type=str, default='cvss',
                       choices=['cvss'],
                       help='Task name')
    parser.add_argument('--dataset', type=str, required=True,
                       choices=['AV', 'AC', 'PR', 'UI'],
                       help='Dataset name')
    parser.add_argument('--data_root', type=str,
                       default=os.path.join(os.path.dirname(__file__), 'data'),
                       help='Root directory for data files')
    parser.add_argument('--result_root', type=str,
                       default=os.path.join(os.path.dirname(__file__), 'results'),
                       help='Root directory for results')
    parser.add_argument('--testNum', type=int, default=0,
                       help='Number of test samples (0 = all)')
    parser.add_argument('--model', type=str, default='MiniMax-M2.7-highspeed',
                       help='Model name')
    parser.add_argument('--max_token', type=int, default=8000,
                       help='Max tokens in response')
    parser.add_argument('--api_url', type=str,
                       default='https://api.minimax.io/v1/text/chatcompletion_v2',
                       help='API endpoint URL')
    parser.add_argument('--api_key', type=str, default=None,
                       help='API key (or set MINIMAX_API_KEY env var)')
    parser.add_argument('--n_samples_per_class', type=int, default=25,
                       help='Number of training samples per class for heuristics extraction')
    return parser.parse_args()


async def call_minimax_api(api_url, api_key, model, messages, max_tokens=8000, temperature=0):
    """Make a single API call to MiniMax."""
    if api_key is None:
        api_key = os.environ.get('MINIMAX_API_KEY')
        if api_key is None:
            raise ValueError("API key not provided and MINIMAX_API_KEY not set")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 1,
        "stream": False,
        "max_tokens": max_tokens
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"API call failed with status {resp.status}: {error_text}")

            result = await resp.json()
            choices = result.get('choices', [])
            if choices:
                return choices[0]['message']['content']
            return None


async def run_self_heuristic_pipeline(args):
    """
    Fully automated 2-round self-heuristic pipeline:
    1. Extract heuristics from probe data via MiniMax API
    2. Use extracted heuristics to classify test samples
    """
    print(f"\n{'='*60}")
    print(f"SELF-HEURISTIC PIPELINE (Fully Automated)")
    print(f"{'='*60}")
    print(f"Task: {args.task}, Dataset: {args.dataset}")

    api_key = args.api_key or os.environ.get('MINIMAX_API_KEY')
    if not api_key:
        raise ValueError("API key not provided. Set MINIMAX_API_KEY env var or use --api_key")

    # ============================================================
    # ROUND 1: Extract Heuristics
    # ============================================================
    print(f"\n{'='*60}")
    print(f"ROUND 1: Extracting Heuristics from MiniMax...")
    print(f"{'='*60}")

    # Get heuristics extraction prompt
    heuristics_result = prompt.extract_heuristics(
        root=args.data_root,
        task=args.task,
        dataset=args.dataset,
        method='self-heuristic',
        n_samples_per_class=args.n_samples_per_class
    )

    extraction_prompt = heuristics_result['heuristics']
    print(f"\nExtraction prompt created ({len(extraction_prompt)} chars)")
    print(f"Preview:\n{extraction_prompt[:300]}...")

    # Call MiniMax to extract heuristics
    messages = [{"role": "user", "content": extraction_prompt}]
    print(f"\nCalling MiniMax API for heuristics extraction...")

    extracted_text = await call_minimax_api(
        api_url=args.api_url,
        api_key=api_key,
        model=args.model,
        messages=messages,
        max_tokens=args.max_token,
        temperature=0
    )

    if not extracted_text:
        raise Exception("Failed to extract heuristics from MiniMax API")

    print(f"\nExtracted heuristics ({len(extracted_text)} chars):")
    print(f"{extracted_text[:500]}...")

    # Save extracted heuristics
    os.makedirs(os.path.join(args.result_root, 'heuristics'), exist_ok=True)
    heuristics_file = os.path.join(args.result_root, 'heuristics', f'{args.task}_{args.dataset}_heuristics.json')
    with open(heuristics_file, 'w', encoding='utf-8') as f:
        json.dump({
            'task': args.task,
            'dataset': args.dataset,
            'extraction_prompt': extraction_prompt,
            'extracted_heuristics': extracted_text,
            'class_samples': heuristics_result['class_samples'],
            'class_names': heuristics_result['class_names']
        }, f, indent=2, ensure_ascii=False)
    print(f"Saved heuristics to: {heuristics_file}")

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
        cot_instruction=True
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

    # Run API requests
    await request.async_api_requests(
        max_requests_per_minute=20,
        max_tokens_per_minute=100000,
        request_url=args.api_url,
        api_key=api_key,
        root_path=args.data_root,
        result_file_path=args.result_root,
        result_file_name=f"{args.task}_{args.dataset}_self-heuristic_test",
        task=args.task,
        dataset=args.dataset,
        model=args.model,
        testNum=len(prompts),
        method='self-heuristic',
        max_token=args.max_token,
        max_attempts=10,
        temperature=0,
        choices=1,
        data=prompts,
    )

    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE!")
    print(f"{'='*60}")
    print(f"Results saved to: results/{args.task}_{args.dataset}_self-heuristic_test.json")
    print(f"Heuristics saved to: {heuristics_file}")
    print(f"\nTo evaluate:")
    print(f"  python eval.py --result_file results/{args.task}_{args.dataset}_self-heuristic_test.json --task {args.task} --dataset {args.dataset}")


async def main():
    args = parse_args()
    await run_self_heuristic_pipeline(args)


if __name__ == '__main__':
    asyncio.run(main())
