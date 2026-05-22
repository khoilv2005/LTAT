"""Compare CVSS UI variants against local baseline and paper reference."""
import json
import os
import re
import subprocess
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASELINE_NT521 = {
    'name': 'DeepSeek baseline (NT521)',
    'accuracy': 0.7716,
    'macro_f1': 0.7158,
    'precision_required': 0.4538,
    'recall_required': 0.8429,
    'unparsed': 0,
    'total': 359,
}

BASELINE_OLD = {
    'name': 'Local old UI run',
    'accuracy': 0.8635,
    'macro_f1': 0.8022,
    'precision_required': 0.6806,
    'recall_required': 0.7000,
    'unparsed': 5,
    'total': 359,
}

PAPER = {
    'name': 'Paper GPT-4',
    'precision_required': 0.8852,
    'recall_required': 0.7714,
}


def parse_eval_output(text):
    metrics = {}
    m = re.search(r'Accuracy:\s*([0-9.]+)', text)
    if m:
        metrics['accuracy'] = float(m.group(1))
    m = re.search(r'Total samples:\s*(\d+)', text)
    if m:
        metrics['total'] = int(m.group(1))
    m = re.search(r'Unparsed predictions:\s*(\d+)', text)
    if m:
        metrics['unparsed'] = int(m.group(1))
    m = re.search(r'Macro-Average F1:\s*([0-9.]+)', text)
    if m:
        metrics['macro_f1'] = float(m.group(1))

    class_blocks = re.split(r'\nClass:\s*', text)
    for block in class_blocks[1:]:
        first_line = block.splitlines()[0].strip()
        label = first_line.split()[0]
        body = '\n'.join(block.splitlines()[:8])
        precision = re.search(r'Precision:\s*([0-9.]+)', body)
        recall = re.search(r'Recall:\s*([0-9.]+)', body)
        f1 = re.search(r'F1:\s*([0-9.]+)', body)
        suffix = 'required' if label == '1' else 'not_required'
        if precision:
            metrics[f'precision_{suffix}'] = float(precision.group(1))
        if recall:
            metrics[f'recall_{suffix}'] = float(recall.group(1))
        if f1:
            metrics[f'f1_{suffix}'] = float(f1.group(1))
    return metrics


def fmt(value):
    if value is None:
        return 'n/a'
    if isinstance(value, float):
        return f'{value:.4f}'
    return str(value)


def run_eval(result_file):
    cmd = [
        sys.executable,
        os.path.join(PROJECT_ROOT, 'eval.py'),
        '--result_file', result_file,
        '--task', 'cvss',
        '--dataset', 'UI',
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    return proc.stdout + '\n' + proc.stderr


def main():
    if len(sys.argv) < 2:
        result_file = os.path.join(
            PROJECT_ROOT,
            'results/cvss/cvss_UI_cvss-ui-v1_self-heuristic_test.json',
        )
        variant_name = 'cvss-ui-v1'
    else:
        result_file = sys.argv[1]
        variant_name = sys.argv[2] if len(sys.argv) > 2 else 'Variant'

    print(f'Evaluating: {result_file}')
    eval_text = run_eval(result_file)
    print(eval_text)
    variant = parse_eval_output(eval_text)
    variant['name'] = variant_name

    out_dir = os.path.join(PROJECT_ROOT, 'results/metrics')
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f'cvss_UI_{variant_name}_metrics.json'), 'w', encoding='utf-8') as f:
        json.dump(variant, f, indent=2)

    rows = [BASELINE_NT521, BASELINE_OLD, variant, PAPER]
    print('\n' + '=' * 96)
    print('CVSS UI COMPARISON')
    print('=' * 96)
    print(f"{'Variant':<28} {'ACC':>7} {'MacroF1':>8} {'P(Req)':>8} {'R(Req)':>8} {'F1(Req)':>8} {'Unp':>5} {'N':>5}")
    print('-' * 96)
    for row in rows:
        print(
            f"{row['name'][:28]:<28} "
            f"{fmt(row.get('accuracy')):>7} "
            f"{fmt(row.get('macro_f1')):>8} "
            f"{fmt(row.get('precision_required')):>8} "
            f"{fmt(row.get('recall_required')):>8} "
            f"{fmt(row.get('f1_required')):>8} "
            f"{fmt(row.get('unparsed')):>5} "
            f"{fmt(row.get('total')):>5}"
        )

    if 'precision_required' in variant:
        print(f"\nDeltas of {variant_name} vs NT521 baseline:")
        for key in ['accuracy', 'macro_f1', 'precision_required', 'recall_required']:
            if key in variant and BASELINE_NT521.get(key) is not None:
                delta = variant[key] - BASELINE_NT521[key]
                sign = '+' if delta >= 0 else ''
                print(f'  {key}: {sign}{delta:.4f}')


if __name__ == '__main__':
    main()
