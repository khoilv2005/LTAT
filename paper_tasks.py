"""
Paper-aligned task presets for ChatGPT-Vulnerability-Management.

This module captures the best prompt choices reported in the paper and can
validate prompt generation without making API calls.
"""

import argparse
import os
import sys

project_root = os.path.dirname(__file__)
src_dir = os.path.join(project_root, 'src')
sys.path.insert(0, project_root)
sys.path.insert(0, src_dir)

PAPER_TASKS = [
    {
        'paper_task': 1,
        'name': 'Bug report summarization',
        'task': 'title',
        'datasets': ['title_itape'],
        'method': 'few-shot',
        'task_type': None,
        'output': 'title/summary',
    },
    {
        'paper_task': 2,
        'name': 'Security bug report identification',
        'task': 'SBRP',
        'datasets': ['Ambari', 'Camel', 'Chromium', 'Derby', 'Wicket'],
        'method': 'expertise',
        'task_type': None,
        'output': 'SBR/NBR',
    },
    {
        'paper_task': 3,
        'name': 'Vulnerability severity evaluation',
        'task': 'cvss',
        'datasets': ['AV', 'AC', 'PR', 'UI'],
        'method': 'self-heuristic',
        'task_type': 'CVSS',
        'output': 'CVSS metric label',
    },
    {
        'paper_task': 4,
        'name': 'Vulnerability repair',
        'task': 'vulfix',
        'datasets': ['vulfix_extractfix'],
        'method': 'expertise',
        'task_type': None,
        'output': 'repaired code',
    },
    {
        'paper_task': 5,
        'name': 'Patch correctness assessment',
        'task': 'APCA',
        'datasets': ['APCA_quatrain'],
        'method': 'code-only',
        'task_type': None,
        'output': 'correct/incorrect patch',
    },
    {
        'paper_task': 5,
        'name': 'Patch correctness assessment',
        'task': 'APCA',
        'datasets': ['APCA_invalidator', 'APCA_panther'],
        'method': 'self-heuristic',
        'task_type': 'APCA',
        'output': 'correct/incorrect patch',
    },
    {
        'paper_task': 6,
        'name': 'Stable patch classification',
        'task': 'stable',
        'datasets': ['stable_patchnet'],
        'method': 'expertise',
        'task_type': None,
        'output': 'stable/non-stable',
    },
]

SELF_HEURISTIC_PLACEHOLDER = (
    "**Class 0**: Placeholder heuristic for dry-run prompt construction.\n"
    "**Class 1**: Placeholder heuristic for dry-run prompt construction."
)

def iter_presets(task_filter=None):
    for preset in PAPER_TASKS:
        if task_filter and preset['paper_task'] != task_filter:
            continue
        for dataset in preset['datasets']:
            yield {
                **preset,
                'dataset': dataset,
            }

def build_extracted_heuristics(dataset, task_type):
    if not task_type:
        return None
    from src import prompt
    system_prompt = prompt.generate_self_heuristic_system_prompt(
        dataset=dataset,
        heuristics_text=SELF_HEURISTIC_PLACEHOLDER,
        cot_instruction=True,
        task_type=task_type,
    )
    return {'system_prompt': system_prompt}

def dry_run_preset(preset, data_root, max_tokens):
    from src import prompt
    extracted = build_extracted_heuristics(preset['dataset'], preset['task_type'])
    prompts = prompt.generate_prompt(
        root=data_root,
        task=preset['task'],
        dataset=preset['dataset'],
        method=preset['method'],
        max_tokens=max_tokens,
        TEST='test',
        testNum=1,
        extracted_heuristics=extracted,
    )
    first = prompts[0] if prompts else None
    return {
        'paper_task': preset['paper_task'],
        'task': preset['task'],
        'dataset': preset['dataset'],
        'method': preset['method'],
        'prompt_count': len(prompts),
        'message_count': len(first['prompt']) if first else 0,
        'sample_id': first['id'] if first else None,
    }

def command_for_preset(preset):
    if preset['method'] == 'self-heuristic':
        return (
            f"python run_self_heuristic.py --task {preset['task']} --dataset {preset['dataset']} "
            f"--testNum 0 "
            f"--api_url https://api.openai.com/v1/chat/completions --model gpt-4-0314"
        )
    return (
        f"python run.py --task {preset['task']} --dataset {preset['dataset']} "
        f"--method {preset['method']} --TEST test --testNum 0 "
        f"--api_url https://api.openai.com/v1/chat/completions --model gpt-4-0314"
    )

def parse_args():
    parser = argparse.ArgumentParser(description='Paper-aligned task presets')
    parser.add_argument('--data_root', default=os.path.join(project_root, 'data'))
    parser.add_argument('--max_token', type=int, default=8000)
    parser.add_argument('--task', type=int, choices=[1, 2, 3, 4, 5, 6])
    parser.add_argument('--dry_run', action='store_true',
                        help='Generate one prompt per preset without API calls')
    parser.add_argument('--print_commands', action='store_true',
                        help='Print paper-aligned run.py commands')
    return parser.parse_args()

def main():
    args = parse_args()
    presets = list(iter_presets(args.task))

    if args.print_commands:
        for preset in presets:
            print(command_for_preset(preset))

    if args.dry_run:
        for preset in presets:
            result = dry_run_preset(preset, args.data_root, args.max_token)
            print(
                f"Task {result['paper_task']} | {result['task']}/{result['dataset']} "
                f"| method={result['method']} | prompts={result['prompt_count']} "
                f"| messages={result['message_count']} | sample={result['sample_id']}"
            )

    if not args.print_commands and not args.dry_run:
        for preset in presets:
            print(
                f"Task {preset['paper_task']}: {preset['name']} | "
                f"{preset['task']}/{preset['dataset']} | method={preset['method']} | "
                f"output={preset['output']}"
            )

if __name__ == '__main__':
    main()
