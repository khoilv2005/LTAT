import contextlib
import importlib.util
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METRICS_DIR = ROOT / "results" / "metrics"
METRICS_DIR.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("repo_eval", ROOT / "eval.py")
repo_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repo_eval)

ITEMS = [
    ("task1_title_itape_partial", "title", "title_itape", 33438, "results/title_title_itape_few-shot_test.json"),
    ("task2_SBRP_Ambari", "SBRP", "Ambari", 500, "results/SBRP_Ambari_expertise_test.json"),
    ("task2_SBRP_Camel", "SBRP", "Camel", 500, "results/SBRP_Camel_expertise_test.json"),
    ("task2_SBRP_Chromium", "SBRP", "Chromium", 20970, "results/SBRP_Chromium_expertise_test.json"),
    ("task2_SBRP_Derby", "SBRP", "Derby", 500, "results/SBRP_Derby_expertise_test.json"),
    ("task2_SBRP_Wicket", "SBRP", "Wicket", 500, "results/SBRP_Wicket_expertise_test.json"),
    ("task3_cvss_AV", "cvss", "AV", 487, "results/cvss/cvss_AV_self-heuristic_test.json"),
    ("task3_cvss_AC", "cvss", "AC", 373, "results/cvss/cvss_AC_self-heuristic_test.json"),
    ("task3_cvss_PR", "cvss", "PR", 414, "results/cvss/cvss_PR_self-heuristic_test.json"),
    ("task3_cvss_UI", "cvss", "UI", 359, "results/cvss/cvss_UI_self-heuristic_test.json"),
    ("task4_vulfix", "vulfix", "vulfix_extractfix", 12, "results/vulfix_vulfix_extractfix_expertise_test.json"),
    ("task5_APCA_quatrain", "APCA", "APCA_quatrain", 995, "results/APCA_APCA_quatrain_code-only_test.json"),
    ("task5_APCA_invalidator", "APCA", "APCA_invalidator", 139, "results/APCA/APCA_APCA_invalidator_self-heuristic_test.json"),
    ("task5_APCA_panther", "APCA", "APCA_panther", 208, "results/APCA/APCA_APCA_panther_self-heuristic_test.json"),
    ("task6_stable", "stable", "stable_patchnet", 10895, "results/stable_stable_patchnet_expertise_test.json"),
]


def evaluate(task, dataset, data):
    for item in data:
        if isinstance(item, dict):
            item["task"] = task
            item["dataset"] = dataset
    with contextlib.redirect_stdout(io.StringIO()):
        if task == "title":
            return repo_eval.evaluate_title(data)
        if task == "vulfix":
            return repo_eval.evaluate_vulfix(data)
        return repo_eval.evaluate_classification(data, task, dataset)


def main():
    rows = []
    for name, task, dataset, expected, rel_path in ITEMS:
        path = ROOT / rel_path
        row = {
            "name": name,
            "task": task,
            "dataset": dataset,
            "expected": expected,
            "path": rel_path,
        }
        if not path.exists():
            row.update({"status": "missing", "count": 0})
            rows.append(row)
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        ids = [str(item.get("id")) for item in data if isinstance(item, dict)]
        errors = sum(
            1
            for item in data
            if isinstance(item, dict)
            and isinstance(item.get("response"), dict)
            and "error" in item.get("response")
        )
        row.update(
            {
                "status": "full" if len(data) == expected else "partial",
                "count": len(data),
                "unique": len(set(ids)),
                "duplicates": len(ids) - len(set(ids)),
                "errors": errors,
                "metrics": evaluate(task, dataset, data),
            }
        )
        rows.append(row)

    output = METRICS_DIR / "deepseek_v4_flash_metrics_current.json"
    output.write_text(json.dumps({"items": rows}, indent=2), encoding="utf-8")

    for row in rows:
        metrics = row.get("metrics", {})
        parts = [
            row["name"],
            f"{row.get('count', 0)}/{row['expected']}",
            row.get("status", ""),
            f"errs={row.get('errors', '')}",
        ]
        if "accuracy" in metrics:
            parts.append(f"acc={metrics['accuracy']:.4f}")
        if "macro_f1" in metrics:
            parts.append(f"macro_f1={metrics['macro_f1']:.4f}")
        if "unparsed" in metrics:
            parts.append(f"unparsed={metrics['unparsed']}")
        if metrics.get("auc") is not None:
            parts.append(f"auc={metrics['auc']:.4f}")
        if "rouge1_f1" in metrics:
            parts.append(f"r1={metrics['rouge1_f1']:.4f}")
            parts.append(f"r2={metrics['rouge2_f1']:.4f}")
            parts.append(f"rl={metrics['rougeL_f1']:.4f}")
        if "has_response" in metrics:
            parts.append(f"responses={metrics['has_response']}")
        print(" | ".join(parts))
    print(f"saved={output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
