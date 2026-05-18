"""
Run script for ChatGPT-Vulnerability-Management evaluation.
Defaults follow the paper's large-scale setting: OpenAI Chat Completions,
gpt-4-0314, temperature=0, top_p=1.
"""

import os
import sys
import asyncio
import argparse
import json
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
    parser = argparse.ArgumentParser(description='Run vulnerability management evaluation')

    # Task & Dataset
    parser.add_argument('--task', type=str, required=True,
                        choices=['title', 'SBRP', 'cvss', 'vulfix', 'APCA', 'stable'],
                        help='Task name')
    parser.add_argument('--dataset', type=str, required=True,
                        help='Dataset name (e.g., title_itape, Chromium, AV, APCA_quatrain)')
    parser.add_argument('--method', type=str, default='base',
                        help='Prompt method (base, expertise, summary, few-shot, info-manual, etc.)')

    # API Config
    parser.add_argument('--api_url', type=str,
                        default='https://api.openai.com/v1/chat/completions',
                        help='API endpoint URL')
    parser.add_argument('--api_key', type=str, default=None,
                        help='API key (or set OPENAI_API_KEY env var)')
    parser.add_argument('--model', type=str, default='gpt-4-0314',
                        help='Model name')

    # Request Limits
    parser.add_argument('--max_requests_per_minute', type=float, default=20,
                        help='Max requests per minute')
    parser.add_argument('--max_tokens_per_minute', type=float, default=100000,
                        help='Max tokens per minute')

    # Data Config
    parser.add_argument('--data_root', type=str,
                        default=os.path.join(os.path.dirname(__file__), 'data'),
                        help='Root directory for data files')
    parser.add_argument('--result_root', type=str,
                        default=os.path.join(os.path.dirname(__file__), 'results'),
                        help='Root directory for results')
    parser.add_argument('--TEST', type=str, default='test',
                        choices=['test', 'probe', 'vali', 'remain'],
                        help='Test split to use')
    parser.add_argument('--testNum', type=int, default=1,
                        help='Number of test samples (0 = all)')
    parser.add_argument('--dry_run', action='store_true',
                        help='Generate prompts and exit without calling the API')
    parser.add_argument('--heuristics_file', type=str, default=None,
                        help='JSON file containing extracted_heuristics for self-heuristic prompts')
    parser.add_argument('--task_type', type=str, default=None,
                        choices=['CVSS', 'SBRP', 'APCA'],
                        help='Task type for self-heuristic system prompt construction')

    # Generation Config
    parser.add_argument('--temperature', type=float, default=0,
                        help='Sampling temperature')
    parser.add_argument('--choices', type=int, default=1,
                        help='Number of choices per request')
    parser.add_argument('--max_token', type=int, default=8000,
                        help='Max tokens in response')
    parser.add_argument('--response_max_token', type=int, default=None,
                        help='Max response tokens; leaves prompt truncation max_token unchanged')
    parser.add_argument('--max_attempts', type=int, default=10,
                        help='Max retry attempts')
    parser.add_argument('--max_concurrent_requests', type=int, default=2,
                        help='Maximum in-flight API requests')
    parser.add_argument('--save_every', type=int, default=50,
                        help='Flush results after this many completed requests')

    return parser.parse_args()


async def main():
    args = parse_args()
    extracted_heuristics = None

    if args.method == 'self-heuristic':
        if args.heuristics_file:
            with open(args.heuristics_file, encoding='utf-8') as f:
                heuristics_data = json.load(f)
            if 'system_prompt' in heuristics_data:
                extracted_heuristics = {'system_prompt': heuristics_data['system_prompt']}
            else:
                task_type = args.task_type or heuristics_data.get('task_type')
                heuristics_text = heuristics_data.get('extracted_heuristics')
                if not task_type or not heuristics_text:
                    raise ValueError("heuristics_file must contain system_prompt or task_type + extracted_heuristics")
                extracted_heuristics = {
                    'system_prompt': prompt.generate_self_heuristic_system_prompt(
                        dataset=args.dataset,
                        heuristics_text=heuristics_text,
                        cot_instruction=True,
                        task_type=task_type,
                    )
                }
        elif args.dry_run:
            if args.task_type:
                task_type = args.task_type
            elif args.task == 'APCA':
                task_type = 'APCA'
            elif args.task == 'SBRP':
                task_type = 'SBRP'
            else:
                task_type = 'CVSS'
            extracted_heuristics = {
                'system_prompt': prompt.generate_self_heuristic_system_prompt(
                    dataset=args.dataset,
                    heuristics_text='**Class 0**: Dry-run placeholder.\n**Class 1**: Dry-run placeholder.',
                    cot_instruction=True,
                    task_type=task_type,
                )
            }
        else:
            raise ValueError("--method self-heuristic requires --heuristics_file unless --dry_run is used")

    # Generate prompts
    print(f"Generating prompts for task={args.task}, dataset={args.dataset}, method={args.method}")
    prompts = prompt.generate_prompt(
        root=args.data_root,
        task=args.task,
        dataset=args.dataset,
        method=args.method,
        max_tokens=args.max_token,
        TEST=args.TEST,
        testNum=args.testNum if args.testNum > 0 else 999999999,
        extracted_heuristics=extracted_heuristics,
    )
    print(f"Generated {len(prompts)} prompts")

    if args.dry_run:
        preview = prompts[0] if prompts else None
        if preview:
            print(f"Dry run preview id={preview['id']} ground_truth={preview['ground_truth']}")
            print(f"Messages: {len(preview['prompt'])}")
        print("Dry run complete. No API calls made.")
        return

    # Run API requests
    print(f"Starting API calls to {args.api_url}")
    print(f"Model: {args.model}, Temperature: {args.temperature}")

    await request.async_api_requests(
        max_requests_per_minute=args.max_requests_per_minute,
        max_tokens_per_minute=args.max_tokens_per_minute,
        request_url=args.api_url,
        api_key=args.api_key,
        root_path=args.data_root,
        result_file_path=args.result_root,
        result_file_name=f"{args.task}_{args.dataset}_{args.method}_{args.TEST}",
        task=args.task,
        dataset=args.dataset,
        model=args.model,
        testNum=len(prompts),
        method=args.method,
        max_token=args.max_token,
        response_max_token=args.response_max_token,
        max_attempts=args.max_attempts,
        max_concurrent_requests=args.max_concurrent_requests,
        save_every=args.save_every,
        temperature=args.temperature,
        choices=args.choices,
        data=prompts,
    )

    print("Done!")


if __name__ == '__main__':
    asyncio.run(main())
