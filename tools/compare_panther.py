"""Compare V7 Panther vs baseline DeepSeek + paper GPT-4."""
import json
import os
import re
import subprocess
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Baseline metrics on Panther từ NT521.md (run đầy đủ 208 sample)
BASELINE = {
    'name': 'Baseline DeepSeek self-heuristic',
    'accuracy': 0.8077,
    'plus_recall': 0.8108,
    'minus_recall': 0.8041,
    'precision': 0.8257,
    'f1': 0.8182,
    'auc': 0.8075,
    'unparsed': 0,
    'total': 208,
}

# Paper GPT-4 self-heuristic test trên Panther
PAPER = {
    'name': 'Paper GPT-4 self-heuristic',
    'accuracy': 0.813,
    'plus_recall': 0.829,
    'minus_recall': 0.794,
    'precision': 0.821,
    'f1': 0.825,
    'auc': 0.811,
    'unparsed': None,
    'total': 208,
}


def parse_eval_output(text):
    metrics = {}
    m = re.search(r'Accuracy:\s*([0-9.]+)', text)
    if m: metrics['accuracy'] = float(m.group(1))
    m = re.search(r'Total samples:\s*(\d+)', text)
    if m: metrics['total'] = int(m.group(1))
    m = re.search(r'Unparsed predictions:\s*(\d+)', text)
    if m: metrics['unparsed'] = int(m.group(1))
    m = re.search(r'AUC:\s*([0-9.]+)', text)
    if m: metrics['auc'] = float(m.group(1))

    class_blocks = re.split(r'\nClass:\s*', text)
    for block in class_blocks[1:]:
        first_line = block.splitlines()[0].strip()
        label = first_line.split()[0]
        body = '\n'.join(block.splitlines()[:8])
        prec = re.search(r'Precision:\s*([0-9.]+)', body)
        plus_r = re.search(r'\+Recall[^:]*:\s*([0-9.]+)', body)
        minus_r = re.search(r'-Recall[^:]*:\s*([0-9.]+)', body)
        f1 = re.search(r'F1:\s*([0-9.]+)', body)
        if label == '1':
            if prec: metrics['precision'] = float(prec.group(1))
            if plus_r: metrics['plus_recall'] = float(plus_r.group(1))
            if f1: metrics['f1'] = float(f1.group(1))
        elif label == '0':
            if minus_r: metrics['minus_recall'] = float(minus_r.group(1))
    return metrics


def fmt(v):
    if v is None: return 'n/a'
    if isinstance(v, float): return f'{v:.4f}'
    return str(v)


def run_eval(result_file):
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, 'eval.py'),
           '--result_file', result_file, '--task', 'APCA', '--dataset', 'APCA_panther']
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    return proc.stdout + '\n' + proc.stderr


def main():
    if len(sys.argv) < 2:
        result_file = os.path.join(
            PROJECT_ROOT, 'results/APCA/APCA_APCA_panther_v7_self-heuristic_test.json',
        )
        variant_name = 'V7 combined (V1+V3+V4)'
        variant_id = 'v7'
    else:
        result_file = sys.argv[1]
        variant_name = sys.argv[2] if len(sys.argv) > 2 else 'Variant'
        variant_id = sys.argv[3] if len(sys.argv) > 3 else 'unknown'

    eval_text = run_eval(result_file)
    print(eval_text)
    new_variant = parse_eval_output(eval_text)
    new_variant['name'] = variant_name

    out_dir = os.path.join(PROJECT_ROOT, 'results/metrics')
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f'APCA_panther_{variant_id}_metrics.json'), 'w', encoding='utf-8') as f:
        json.dump(new_variant, f, indent=2)

    rows = [BASELINE, new_variant, PAPER]
    print('\n' + '=' * 90)
    print('COMPARISON (Panther)')
    print('=' * 90)
    print(f"{'Variant':<35} {'ACC':>7} {'+R':>7} {'-R':>7} {'P':>7} {'F1':>7} {'AUC':>7} {'Unp':>5} {'N':>5}")
    print('-' * 90)
    for r in rows:
        print(
            f"{r['name'][:35]:<35} "
            f"{fmt(r.get('accuracy')):>7} {fmt(r.get('plus_recall')):>7} "
            f"{fmt(r.get('minus_recall')):>7} {fmt(r.get('precision')):>7} "
            f"{fmt(r.get('f1')):>7} {fmt(r.get('auc')):>7} "
            f"{fmt(r.get('unparsed')):>5} {fmt(r.get('total')):>5}"
        )

    print(f'\nDeltas of {variant_name} vs baseline (Panther):')
    for k in ['accuracy', 'plus_recall', 'minus_recall', 'precision', 'f1', 'auc']:
        if k in new_variant:
            d = new_variant[k] - BASELINE[k]
            sign = '+' if d >= 0 else ''
            print(f'  {k}: {sign}{d:.4f}')

    print(f'\nDeltas of {variant_name} vs paper:')
    for k in ['accuracy', 'plus_recall', 'minus_recall', 'precision', 'f1', 'auc']:
        if k in new_variant and PAPER.get(k) is not None:
            d = new_variant[k] - PAPER[k]
            sign = '+' if d >= 0 else ''
            print(f'  {k}: {sign}{d:.4f}')


if __name__ == '__main__':
    main()
