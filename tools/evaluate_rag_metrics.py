import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import eval as repo_eval


def normalized_prediction(item, task, dataset):
    content = repo_eval.response_content(item.get("response", {}))
    pred = repo_eval.extract_prediction(content)
    return repo_eval.normalize_prediction(pred, task, dataset)


def normalized_truth(item, task, dataset):
    return repo_eval.normalize_ground_truth(item.get("ground_truth", ""), task, dataset)


def stable_metrics(results):
    pairs = [(normalized_truth(item, "stable", "stable_patchnet"), normalized_prediction(item, "stable", "stable_patchnet")) for item in results]
    total = len(pairs)
    labels = {"true", "false"}
    unparsed = sum(1 for _, pred in pairs if pred not in labels)
    tp = sum(1 for gt, pred in pairs if gt == "true" and pred == "true")
    fp = sum(1 for gt, pred in pairs if gt == "false" and pred == "true")
    fn = sum(1 for gt, pred in pairs if gt == "true" and pred != "true")
    tn = sum(1 for gt, pred in pairs if gt == "false" and pred == "false")
    correct = tp + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "auc": (recall + specificity) / 2,
        "unparsed": unparsed,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
    }


def sbrp_metrics(results, dataset):
    pairs = [(normalized_truth(item, "SBRP", dataset), normalized_prediction(item, "SBRP", dataset)) for item in results]
    total = len(pairs)
    labels = {"1", "0"}
    unparsed = sum(1 for _, pred in pairs if pred not in labels)
    tp = sum(1 for gt, pred in pairs if gt == "1" and pred == "1")
    fp = sum(1 for gt, pred in pairs if gt == "0" and pred == "1")
    fn = sum(1 for gt, pred in pairs if gt == "1" and pred != "1")
    tn = sum(1 for gt, pred in pairs if gt == "0" and pred == "0")
    correct = tp + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    g_measure = (recall * (1 - fpr)) ** 0.5 if recall * (1 - fpr) >= 0 else 0.0
    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "precision": precision,
        "recall": recall,
        "fpr": fpr,
        "f1": f1,
        "g_measure": g_measure,
        "unparsed": unparsed,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
    }


def apca_metrics(results, dataset):
    pairs = [(normalized_truth(item, "APCA", dataset), normalized_prediction(item, "APCA", dataset)) for item in results]
    total = len(pairs)
    labels = {"1", "0"}
    unparsed = sum(1 for _, pred in pairs if pred not in labels)
    tp = sum(1 for gt, pred in pairs if gt == "1" and pred == "1")
    fp = sum(1 for gt, pred in pairs if gt == "0" and pred == "1")
    fn = sum(1 for gt, pred in pairs if gt == "1" and pred != "1")
    tn = sum(1 for gt, pred in pairs if gt == "0" and pred == "0")
    correct = tp + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    plus_recall = tp / (tp + fn) if tp + fn else 0.0
    minus_recall = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * plus_recall / (precision + plus_recall) if precision + plus_recall else 0.0
    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "precision": precision,
        "plus_recall": plus_recall,
        "minus_recall": minus_recall,
        "f1": f1,
        "auc": (plus_recall + minus_recall) / 2,
        "unparsed": unparsed,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
    }


def cvss_metrics(results, dataset):
    pairs = [(normalized_truth(item, "cvss", dataset), normalized_prediction(item, "cvss", dataset)) for item in results]
    labels = ["0", "1", "2", "3"] if dataset == "AV" else ["0", "1"]
    total = len(pairs)
    unparsed = sum(1 for _, pred in pairs if pred not in labels)
    correct = sum(1 for gt, pred in pairs if gt == pred)
    precisions = []
    recalls = []
    f1s = []
    per_label = {}
    for label in labels:
        tp = sum(1 for gt, pred in pairs if gt == label and pred == label)
        fp = sum(1 for gt, pred in pairs if gt != label and pred == label)
        fn = sum(1 for gt, pred in pairs if gt == label and pred != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1}
        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)
    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "precision": sum(precisions) / len(precisions) if precisions else 0.0,
        "recall": sum(recalls) / len(recalls) if recalls else 0.0,
        "f1": sum(f1s) / len(f1s) if f1s else 0.0,
        "unparsed": unparsed,
        "per_label": per_label,
    }

def vulfix_sanity_metrics(results):
    total = len(results)
    non_empty = 0
    code_like = 0
    for item in results:
        content = repo_eval.response_content(item.get("response", {})).strip()
        if content:
            non_empty += 1
        lowered = content.lower()
        if any(token in content for token in [";", "{", "}", "#include", "return", "if (", "if("]) and not lowered.startswith(("i cannot", "sorry")):
            code_like += 1
    return {
        "total": total,
        "non_empty": non_empty,
        "code_like": code_like,
        "non_empty_rate": non_empty / total if total else 0.0,
        "code_like_rate": code_like / total if total else 0.0,
    }

def title_metrics(results):
    return repo_eval.evaluate_title(results)

def _baselines(task):
    if task == "stable":
        return {
            "local_deepseek_expertise": {
                "accuracy": 0.7734,
                "precision": 0.7552,
                "recall": 0.8553,
                "f1": 0.8021,
                "auc": 0.7680,
            },
            "stable_v3_from_update_md": {
                "accuracy": 0.8240,
                "precision": 0.8197,
                "recall": 0.8692,
                "f1": 0.8437,
                "auc": 0.8245,
            },
        }
    if task == "SBRP":
        return {
            "paper_gpt4_expertise": {
                "recall": 0.68,
                "fpr": 0.04,
                "precision": 0.53,
                "f1": 0.57,
                "g_measure": 0.79,
            }
        }
    return {}


def main():
    parser = argparse.ArgumentParser(description="Evaluate RAG result files")
    parser.add_argument("result_file", type=Path)
    parser.add_argument("--task", default="stable", choices=["stable", "SBRP", "APCA", "cvss", "vulfix", "title"])
    parser.add_argument("--dataset", default="stable_patchnet")
    parser.add_argument("--name", default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    results = json.loads(args.result_file.read_text(encoding="utf-8"))
    if args.task == "stable":
        if args.dataset != "stable_patchnet":
            raise ValueError("Stable evaluator supports stable_patchnet only")
        metrics = stable_metrics(results)
    elif args.task == "SBRP":
        metrics = sbrp_metrics(results, args.dataset)
    elif args.task == "APCA":
        metrics = apca_metrics(results, args.dataset)
    elif args.task == "cvss":
        metrics = cvss_metrics(results, args.dataset)
    elif args.task == "vulfix":
        metrics = vulfix_sanity_metrics(results)
    elif args.task == "title":
        metrics = title_metrics(results)
    else:
        raise ValueError(f"Unsupported task: {args.task}")
    payload = {
        "name": args.name or args.result_file.stem,
        "task": args.task,
        "dataset": args.dataset,
        "result_file": str(args.result_file),
        "metrics": metrics,
        "baselines": _baselines(args.task),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"name={payload['name']}")
    if args.task == "title":
        for key, value in metrics.items():
            print(f"{key}={value:.4f}" if isinstance(value, float) else f"{key}={value}")
        return
    if args.task == "vulfix":
        print(f"total={metrics['total']}")
        print(f"non_empty={metrics['non_empty']}")
        print(f"code_like={metrics['code_like']}")
        print(f"non_empty_rate={metrics['non_empty_rate']:.4f}")
        print(f"code_like_rate={metrics['code_like_rate']:.4f}")
        return
    keys = ["total", "accuracy", "precision", "recall", "f1"]
    if "plus_recall" in metrics:
        keys = ["total", "accuracy", "precision", "plus_recall", "minus_recall", "f1"]
    if "fpr" in metrics:
        keys.append("fpr")
    if "g_measure" in metrics:
        keys.append("g_measure")
    if "auc" in metrics:
        keys.append("auc")
    keys.append("unparsed")
    for key in keys:
        value = metrics[key]
        print(f"{key}={value:.4f}" if isinstance(value, float) else f"{key}={value}")
    if "true_positive" in metrics:
        print(
            "confusion="
            f"TP:{metrics['true_positive']} FP:{metrics['false_positive']} "
            f"FN:{metrics['false_negative']} TN:{metrics['true_negative']}"
        )
    if "per_label" in metrics:
        print("per_label=" + json.dumps(metrics["per_label"], sort_keys=True))


if __name__ == "__main__":
    main()
