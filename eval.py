"""
Evaluation script for vulnerability management tasks.
Computes accuracy, F1, precision, recall for classification tasks.

Implements metrics from the paper:
- ROUGE for title generation
- FPR, G-measure for SBRP
- AUC, +Recall/-Recall for APCA
- Compiler + PoC + regression tests for VulFix (manual evaluation)
"""

import os
import sys
import json
import argparse
from collections import defaultdict

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))


def parse_args():
    parser = argparse.ArgumentParser(description='Evaluate vulnerability management results')
    parser.add_argument('--result_file', type=str, required=True,
                        help='Path to result JSON file')
    parser.add_argument('--task', type=str, required=True,
                        choices=['title', 'SBRP', 'cvss', 'vulfix', 'APCA', 'stable'],
                        help='Task name')
    parser.add_argument('--dataset', type=str, required=True,
                        help='Dataset name')
    parser.add_argument('--output', type=str, default=None,
                        help='Output file for results (optional)')
    return parser.parse_args()


def extract_prediction(response_content):
    """Extract prediction from model response content."""
    if response_content is None:
        return None

    content = str(response_content).strip()

    import re
    # Find ALL matches and take the LAST one (for thinking models that reconsider)
    all_matches = re.findall(r'\*\*Answer:\s*\(([A-D])\)\s*(\w+)\*\*', content, re.IGNORECASE)
    if all_matches:
        last_match = all_matches[-1]
        return f"({last_match[0]}) {last_match[1]}"

    # Try to find "Answer:" pattern without bold
    all_matches = re.findall(r'Answer:\s*\(([A-D])\)\s*(\w+)', content, re.IGNORECASE)
    if all_matches:
        last_match = all_matches[-1]
        return f"({last_match[0]}) {last_match[1]}"

    # Try to find category after "Category:" or "category:"
    if "Category:" in content:
        pred = content.split("Category:")[-1].strip()
        pred = pred.split("\n")[0].strip()
        return pred
    elif "category:" in content.lower():
        pred = content.lower().split("category:")[-1].strip()
        pred = pred.split("\n")[0].strip()
        return pred

    # For title task - return as is
    return content


def normalize_prediction(pred, task, dataset):
    """Normalize prediction to match ground truth format."""

    if pred is None:
        return None

    pred = str(pred).strip()
    task_normalized = 'SBRP' if str(task).lower() == 'sbrp' else task

    # Handle MiniMax format: **Answer: (X) Label**
    # Extract (A), (B), (C), (D) patterns
    import re
    answer_match = re.search(r'\(([A-D])\)\s*(\w+)', pred, re.IGNORECASE)
    if answer_match:
        letter = answer_match.group(1).upper()
        label = answer_match.group(2).lower()

        if task_normalized == 'SBRP':
            # Prefer label text because paper expertise prompt uses
            # (A) SBR, (B) NBR while self-heuristic uses the reverse order.
            if 'non' in label or label == 'nbr':
                return '0'
            elif 'security' in label or label == 'sbr':
                return '1'
            # Paper's SBRP expertise prompt: (A) SBR, (B) NBR.
            if letter == 'A':
                return '1'
            elif letter == 'B':
                return '0'

        elif task_normalized == 'cvss':
            # AV: (A) Network(1), (B) Adjacent(2), (C) Physical(3), (D) Not Related(0)
            if dataset == 'AV':
                if letter == 'A' or 'network' in label:
                    return '1'
                elif letter == 'B' or 'adjacent' in label:
                    return '2'
                elif letter == 'C' or 'physical' in label:
                    return '3'
                elif letter == 'D' or ('not' in label and 'related' in label):
                    return '0'
            # AC, PR, UI: (A) Not High(0), (B) High(1)
            elif dataset in ['AC', 'PR', 'UI']:
                if letter == 'A' or ('not' in label and 'high' in label):
                    return '0'
                elif letter == 'B' or 'high' in label:
                    return '1'

        elif task_normalized == 'APCA':
            # CoF = Correct (1), NCF = Incorrect (0)
            if 'incorrect' in label or 'ncf' in label:
                return '0'
            elif 'correct' in label or 'cof' in label:
                return '1'
            elif letter == 'A':
                return '1'
            elif letter == 'B':
                return '0'

        elif task_normalized == 'stable':
            if letter == 'A' or 'ack' in label or 'true' in label:
                return 'true'
            elif letter == 'B' or 'nak' in label or 'false' in label:
                return 'false'

    # Fallback to old keyword-based matching
    pred_lower = pred.lower()

    if task_normalized == 'SBRP':
        if pred_lower in ['sbr', 'security bug report']:
            return '1'
        elif pred_lower in ['nbr', 'non-security bug report']:
            return '0'
        elif 'security' in pred_lower and 'non' not in pred_lower:
            return '1'
        elif 'non' in pred_lower or 'non-security' in pred_lower:
            return '0'

    elif task_normalized == 'cvss':
        if dataset == 'AV':
            if 'not' in pred_lower and 'related' in pred_lower:
                return '0'
            elif 'network' in pred_lower and 'adjacent' not in pred_lower:
                return '1'
            elif 'adjacent' in pred_lower:
                return '2'
            elif 'physical' in pred_lower:
                return '3'
        elif dataset in ['AC', 'PR', 'UI']:
            if 'not' in pred_lower and 'high' in pred_lower:
                return '0'
            elif 'high' in pred_lower:
                return '1'

    elif task_normalized == 'APCA':
        if 'ncf' in pred_lower or 'incorrect' in pred_lower:
            return '0'
        elif 'cof' in pred_lower or 'correct' in pred_lower:
            return '1'

    elif task_normalized == 'stable':
        if 'ack' in pred_lower or 'true' in pred_lower:
            return 'true'
        elif 'nak' in pred_lower or 'false' in pred_lower:
            return 'false'

    return pred

def normalize_ground_truth(label, task, dataset):
    """Normalize dataset labels into the same space as predictions."""
    if label is None:
        return None

    value = str(label).strip()
    lower = value.lower()
    task_normalized = 'SBRP' if str(task).lower() == 'sbrp' else task

    if task_normalized == 'SBRP':
        if lower in ['1', 'sbr', 'security bug report', 'security bug']:
            return '1'
        if lower in ['0', 'nbr', 'non-security bug report', 'non-security bug']:
            return '0'

    elif task_normalized == 'APCA':
        if lower in ['1', 'true', 'correct', 'cof', 'correct patch']:
            return '1'
        if lower in ['0', 'false', 'incorrect', 'ncf', 'incorrect patch']:
            return '0'

    elif task_normalized == 'stable':
        if lower in ['true', '1', 'stable', 'ack']:
            return 'true'
        if lower in ['false', '0', 'non-stable', 'nak']:
            return 'false'

    return value

def response_content(response):
    """Return assistant text across OpenAI/Ollama response shapes."""
    if isinstance(response, dict):
        choices = response.get('choices', [])
        if choices:
            return choices[0].get('message', {}).get('content', '')
        if 'message' in response and isinstance(response['message'], dict):
            return response['message'].get('content', '')
        if 'response' in response:
            return response.get('response', '')
        return ''
    return str(response)


def evaluate_title(results):
    """
    Evaluate title generation results using ROUGE scores.

    Paper methodology: ROUGE-1, ROUGE-2, ROUGE-L (F1 measure)
    Reference: Section 4.1 / Table 3 in the paper
    """
    try:
        from rouge_score import rouge_scorer
    except ImportError:
        print("ERROR: rouge-score library not installed.")
        print("Install with: pip install rouge-score")
        print("Falling back to exact match (incorrect methodology).")
        return _evaluate_title_exact(results)

    print(f"\n{'='*60}")
    print(f"Title Generation Results (ROUGE)")
    print(f"{'='*60}")

    scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)
    # Track precision, recall, f1 for each metric
    total_scores = {
        'rouge1': {'precision': 0, 'recall': 0, 'f1': 0},
        'rouge2': {'precision': 0, 'recall': 0, 'f1': 0},
        'rougeL': {'precision': 0, 'recall': 0, 'f1': 0},
    }
    total = 0

    for item in results:
        ground_truth = str(item.get('ground_truth', '')).strip()
        response = item.get('response', {})

        if isinstance(response, dict):
            choices = response.get('choices', [])
            if choices:
                content = choices[0].get('message', {}).get('content', '').strip()
            elif 'message' in response and isinstance(response['message'], dict):
                content = response['message'].get('content', '').strip()
            elif 'response' in response:
                content = response.get('response', '').strip()
            else:
                content = ''
        else:
            content = str(response).strip()

        if not content or not ground_truth:
            continue

        scores = scorer.score(ground_truth, content)
        for metric in ['rouge1', 'rouge2', 'rougeL']:
            total_scores[metric]['precision'] += scores[metric].precision
            total_scores[metric]['recall'] += scores[metric].recall
            total_scores[metric]['f1'] += scores[metric].fmeasure
        total += 1

        if total <= 5:
            print(f"\nSample {total}:")
            print(f"  Ground Truth: {ground_truth[:80]}")
            print(f"  Prediction: {content[:80]}")
            print(f"  R-1 P/R/F1: {scores['rouge1'].precision:.4f}/{scores['rouge1'].recall:.4f}/{scores['rouge1'].fmeasure:.4f}, "
                  f"R-2: {scores['rouge2'].fmeasure:.4f}, R-L: {scores['rougeL'].fmeasure:.4f}")

    if total > 0:
        print(f"\n{'='*60}")
        print(f"Total samples: {total}")
        print(f"{'Metric':<12} {'Precision':>10} {'Recall':>10} {'F1':>10}")
        print(f"{'-'*44}")
        for metric in ['rouge1', 'rouge2', 'rougeL']:
            avg_p = total_scores[metric]['precision'] / total
            avg_r = total_scores[metric]['recall'] / total
            avg_f = total_scores[metric]['f1'] / total
            print(f"{metric.upper():<12} {avg_p:>10.4f} {avg_r:>10.4f} {avg_f:>10.4f}")
        print(f"{'='*60}")
        return {
            'rouge1_precision': total_scores['rouge1']['precision'] / total,
            'rouge1_recall': total_scores['rouge1']['recall'] / total,
            'rouge1_f1': total_scores['rouge1']['f1'] / total,
            'rouge2_f1': total_scores['rouge2']['f1'] / total,
            'rougeL_f1': total_scores['rougeL']['f1'] / total,
            'total': total
        }
    else:
        print(f"\nNo valid samples to evaluate.")
        print(f"{'='*60}")
        return {'rouge1': 0, 'rouge2': 0, 'rougeL': 0, 'total': 0}


def _evaluate_title_exact(results):
    """Fallback exact match evaluation (incorrect methodology per paper)."""
    correct = 0
    total = 0

    print(f"\n{'='*60}")
    print(f"Title Generation Results (EXACT MATCH - INCORRECT METHODOLOGY)")
    print(f"{'='*60}")
    print(f"WARNING: Using exact match instead of ROUGE. Install rouge-score for correct evaluation.")

    for item in results:
        ground_truth = str(item.get('ground_truth', '')).strip().lower()
        response = item.get('response', {})

        if isinstance(response, dict):
            choices = response.get('choices', [])
            if choices:
                content = choices[0].get('message', {}).get('content', '').strip().lower()
            elif 'message' in response and isinstance(response['message'], dict):
                content = response['message'].get('content', '').strip().lower()
            elif 'response' in response:
                content = response.get('response', '').strip().lower()
            else:
                content = ''
        else:
            content = str(response).strip().lower()

        if content == ground_truth:
            correct += 1
        total += 1

    accuracy = correct / total if total > 0 else 0
    print(f"\n{'='*60}")
    print(f"Total samples: {total}")
    print(f"Exact Match Accuracy: {accuracy:.4f} ({accuracy*100:.2f}%)")
    print(f"{'='*60}")

    return {'accuracy': accuracy, 'total': total, 'correct': correct}


def evaluate_classification(results, task, dataset):
    """
    Evaluate classification results with paper-compliant metrics.

    Paper methodology:
    - SBRP: Accuracy, Precision, Recall, F1, FPR, G-measure (Table 4)
    - APCA: Accuracy, Precision, +Recall, -Recall, F1, AUC (Table 5)
    - Stable: Accuracy, Precision, Recall, F1, AUC (Table 6)
    - CVSS: Accuracy, Precision, Recall, F1 per metric

    Reference: Tables 4, 5, 6 in the paper
    """
    try:
        from sklearn.metrics import roc_auc_score
    except ImportError:
        roc_auc_score = None
        print("WARNING: scikit-learn not installed. AUC will not be computed.")

    correct = 0
    total = 0

    true_positive = defaultdict(int)
    false_positive = defaultdict(int)
    false_negative = defaultdict(int)
    true_negative = defaultdict(int)

    all_labels = set()
    predictions = []
    y_true_binary = []
    y_pred_binary = []
    auc = None
    unparsed = 0

    for item in results:
        ground_truth = normalize_ground_truth(item.get('ground_truth', ''), task, dataset)
        content = response_content(item.get('response', {}))

        pred = extract_prediction(content)
        pred_normalized = normalize_prediction(pred, task, dataset)
        if str(pred_normalized) not in {'0', '1', '2', '3', 'true', 'false'}:
            unparsed += 1

        all_labels.add(ground_truth)
        predictions.append((ground_truth, pred_normalized))

        if ground_truth == pred_normalized:
            correct += 1
        total += 1

    accuracy = correct / total if total > 0 else 0

    # Calculate per-class metrics
    print(f"\n{'='*60}")
    print(f"Results Summary")
    print(f"{'='*60}")
    print(f"Total samples: {total}")
    print(f"Correct: {correct}")
    print(f"Accuracy: {accuracy:.4f} ({accuracy*100:.2f}%)")
    print(f"Unparsed predictions: {unparsed}")

    # Per-class breakdown
    print(f"\n{'='*60}")
    print(f"Per-Class Metrics")
    print(f"{'='*60}")

    is_apca = (task == 'APCA')

    # Build binary arrays for AUC BEFORE the per-class loop (fixes duplication bug)
    if is_apca or task == 'stable':
        for gt, p in predictions:
            y_true_binary.append(1 if gt in ['1', 'true'] else 0)
            y_pred_binary.append(1 if p in ['1', 'true'] else 0)

    for label in sorted(all_labels):
        tp = sum(1 for gt, p in predictions if gt == label and p == label)
        fp = sum(1 for gt, p in predictions if gt != label and p == label)
        fn = sum(1 for gt, p in predictions if gt == label and p != label)
        tn = sum(1 for gt, p in predictions if gt != label and p != label)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

        # G-measure for SBRP (Table 4 in paper) - only for positive class
        g_measure = 0
        if task == 'SBRP' and label == '1' and recall > 0 and (1 - fpr) > 0:
            g_measure = (2 * recall * (1 - fpr)) / (recall + (1 - fpr))

        # For APCA: +Recall = recall of class 1 (Correct/CoF), -Recall = recall of class 0 (Incorrect/NCF)
        recall_label = '+Recall' if (label == '1' and is_apca) else ('-Recall' if (label == '0' and is_apca) else 'Recall')

        print(f"\nClass: {label}")
        print(f"  Support: {tp + fn}")
        print(f"  Precision: {precision:.4f}")
        print(f"  {recall_label}: {recall:.4f}")
        print(f"  F1: {f1:.4f}")

        # FPR and G-measure only for SBRP Positive Class (Table 4)
        if task == 'SBRP' and label == '1':
            print(f"  FPR: {fpr:.4f}")
            print(f"  G-measure: {g_measure:.4f}")

    # Calculate AUC for APCA and stable
    if (is_apca or task == 'stable') and roc_auc_score is not None and len(y_true_binary) > 0:
        try:
            auc = roc_auc_score(y_true_binary, y_pred_binary)
            print(f"\n  AUC: {auc:.4f}")
        except ValueError as e:
            print(f"\n  AUC: N/A ({e})")

    # Macro-average F1
    macro_f1 = 0
    for label in sorted(all_labels):
        tp = sum(1 for gt, p in predictions if gt == label and p == label)
        fp = sum(1 for gt, p in predictions if gt != label and p == label)
        fn = sum(1 for gt, p in predictions if gt == label and p != label)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        macro_f1 += 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    macro_f1 /= len(all_labels) if all_labels else 1
    print(f"\n{'='*60}")
    print(f"Macro-Average F1: {macro_f1:.4f}")
    print(f"{'='*60}")

    ret = {
        'accuracy': accuracy,
        'macro_f1': macro_f1,
        'total': total,
        'correct': correct,
        'unparsed': unparsed
    }

    if is_apca or task == 'stable':
        ret['auc'] = auc

    return ret


def evaluate_vulfix(results):
    """
    Evaluate vulnerability fix results.

    Paper methodology: Combine generated code with original, compile, and test with PoC + regression tests.
    Reference: Section 4.4 / Table 6 in the paper

    NOTE: Full evaluation requires compiler + PoC + regression test execution.
    This function provides basic response stats only. Manual verification needed.
    """
    total = len(results)
    has_response = 0
    samples_with_code = 0

    print(f"\n{'='*60}")
    print(f"Vulnerability Fix Results")
    print(f"{'='*60}")
    print(f"Total samples: {total}")
    print(f"\nWARNING: VulFix requires manual evaluation with compiler + PoC + regression tests.")
    print(f"See paper Section 4.4 for methodology.")

    for item in results:
        content = response_content(item.get('response', {}))
        if content and len(content.strip()) > 0:
            has_response += 1
            # Check if content looks like code
            if '```' in content or 'def ' in content or 'patch' in content.lower():
                samples_with_code += 1

    print(f"Samples with response: {has_response}")
    print(f"Samples with code blocks: {samples_with_code}")
    print(f"\n{'='*60}")
    print(f"Manual Evaluation Required:")
    print(f"  1. Combine generated fix with original source")
    print(f"  2. Compile the combined code")
    print(f"  3. Run PoC (Proof of Concept) to verify fix")
    print(f"  4. Run regression tests to ensure no breakage")
    print(f"{'='*60}")

    return {
        'total': total,
        'has_response': has_response,
        'samples_with_code': samples_with_code,
        'manual_evaluation_required': True
    }


def main():
    args = parse_args()

    # Load results
    with open(args.result_file) as f:
        results = json.load(f)

    # Add task and dataset info to each result
    for item in results:
        item['task'] = args.task
        item['dataset'] = args.dataset

    print(f"Loaded {len(results)} results from {args.result_file}")
    print(f"Task: {args.task}, Dataset: {args.dataset}")

    # Evaluate based on task type
    if args.task == 'title':
        metrics = evaluate_title(results)
    elif args.task == 'vulfix':
        metrics = evaluate_vulfix(results)
    else:
        metrics = evaluate_classification(results, args.task, args.dataset)

    # Save metrics if output specified
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f"\nMetrics saved to {args.output}")

    return metrics


if __name__ == '__main__':
    main()
