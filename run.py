"""
Run script for ChatGPT-Vulnerability-Management evaluation.
Supports both OpenAI and MiniMax APIs.
"""

import os
import sys
import asyncio
import argparse
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
                        help='Prompt method (base, summary, few-shot, info-manual, etc.)')

    # API Config
    parser.add_argument('--api_url', type=str,
                        default='https://api.minimax.io/v1/text/chatcompletion_v2',
                        help='API endpoint URL')
    parser.add_argument('--api_key', type=str, default=None,
                        help='API key (or set MINIMAX_API_KEY env var)')
    parser.add_argument('--model', type=str, default='MiniMax-M2.7-highspeed',
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
                        choices=['test', 'vali', 'remain'],
                        help='Test split to use')
    parser.add_argument('--testNum', type=int, default=1,
                        help='Number of test samples (0 = all)')

    # Generation Config
    parser.add_argument('--temperature', type=float, default=0,
                        help='Sampling temperature')
    parser.add_argument('--choices', type=int, default=1,
                        help='Number of choices per request')
    parser.add_argument('--max_token', type=int, default=8000,
                        help='Max tokens in response')
    parser.add_argument('--max_attempts', type=int, default=10,
                        help='Max retry attempts')

    return parser.parse_args()


async def main():
    args = parse_args()

    # Generate prompts
    print(f"Generating prompts for task={args.task}, dataset={args.dataset}, method={args.method}")
    prompts = prompt.generate_prompt(
        root=args.data_root,
        task=args.task,
        dataset=args.dataset,
        method=args.method,
        max_tokens=args.max_token,
        TEST=args.TEST,
        testNum=args.testNum if args.testNum > 0 else 999999999
    )
    print(f"Generated {len(prompts)} prompts")

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
        max_attempts=args.max_attempts,
        temperature=args.temperature,
        choices=args.choices,
        data=prompts,
    )

    print("Done!")


if __name__ == '__main__':
    asyncio.run(main())
