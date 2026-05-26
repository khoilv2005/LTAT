import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import eval as repo_eval


def normalized_prediction(item):
    content = repo_eval.response_content(item.get("response", {}))
    pred = repo_eval.extract_prediction(content)
    return repo_eval.normalize_prediction(pred, "stable", "stable_patchnet")


def normalized_truth(item):
    return repo_eval.normalize_ground_truth(
        item.get("ground_truth", ""), "stable", "stable_patchnet"
    )


def compute_metrics(results):
    pairs = [(normalized_truth(item), normalized_prediction(item)) for item in results]
    total = len(pairs)
    correct = sum(1 for gt, pred in pairs if gt == pred)
    unparsed = sum(1 for _, pred in pairs if pred not in {"true", "false"})

    tp = sum(1 for gt, pred in pairs if gt == "true" and pred == "true")
    fp = sum(1 for gt, pred in pairs if gt == "false" and pred == "true")
    fn = sum(1 for gt, pred in pairs if gt == "true" and pred != "true")
    tn = sum(1 for gt, pred in pairs if gt == "false" and pred != "true")

    accuracy = correct / total if total else 0
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    specificity = tn / (tn + fp) if tn + fp else 0
    auc = (recall + specificity) / 2

    return {
        "total": total,
        "correct": correct,
        "unparsed": unparsed,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "auc": auc,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
    }


def write_false_cases(results, output_path):
    rows = []
    for item in results:
        gt = normalized_truth(item)
        pred = normalized_prediction(item)
        if gt == pred:
            continue
        patch = str(item.get("prompt", {}).get("messages", [{}])[-1].get("content", ""))
        if not patch:
            patch = str(item.get("prompt", ""))
        rows.append(
            {
                "id": item.get("id"),
                "ground_truth": gt,
                "prediction": pred,
                "kind": "FN" if gt == "true" else "FP",
                "preview": patch[:1200],
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Evaluate stable patch classification results")
    parser.add_argument("result_file", type=Path)
    parser.add_argument("name", nargs="?", default=None)
    parser.add_argument("--metrics-output", type=Path, default=None)
    parser.add_argument("--false-output", type=Path, default=None)
    args = parser.parse_args()

    results = json.loads(args.result_file.read_text(encoding="utf-8"))
    metrics = compute_metrics(results)

    payload = {
        "name": args.name or args.result_file.stem,
        "result_file": str(args.result_file),
        "metrics": metrics,
        "baselines": {
            "paper_gpt4_expertise": {
                "accuracy": 0.733,
                "precision": 0.679,
                "recall": 0.950,
                "f1": 0.792,
                "auc": 0.716,
            },
            "local_deepseek_expertise": {
                "accuracy": 0.7734,
                "precision": 0.7552,
                "recall": 0.8553,
                "f1": 0.8021,
                "auc": 0.7680,
                "unparsed": 24,
            },
            "paper_patchnet": {
                "accuracy": 0.862,
                "precision": 0.839,
                "recall": 0.907,
                "f1": 0.871,
                "auc": 0.860,
            },
        },
    }

    if args.metrics_output:
        args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    false_count = None
    if args.false_output:
        false_count = write_false_cases(results, args.false_output)

    print(f"name={payload['name']}")
    for key in ["total", "accuracy", "precision", "recall", "f1", "auc", "unparsed"]:
        value = metrics[key]
        print(f"{key}={value:.4f}" if isinstance(value, float) else f"{key}={value}")
    print(
        "confusion="
        f"TP:{metrics['true_positive']} FP:{metrics['false_positive']} "
        f"FN:{metrics['false_negative']} TN:{metrics['true_negative']}"
    )
    if false_count is not None:
        print(f"false_cases={false_count}")


if __name__ == "__main__":
    main()
