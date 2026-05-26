# New Results

## APCA Invalidator - V5 hybrid (V7 + manual expertise)

Source metrics file: `results/metrics/APCA_invalidator_v5_metrics.json`

| Metric | Value |
|---|---:|
| Total samples | 139 |
| Accuracy | 0.8489 |
| +Recall (Correct / CoF) | 0.8000 |
| -Recall (Incorrect / NCF) | 0.8624 |
| Precision (Correct / CoF) | 0.6154 |
| F1 (Correct / CoF) | 0.6957 |
| AUC | 0.8312 |
| Unparsed | 0 |

## CVSS UI - cvss-ui-v2

Source metrics file: `results/metrics/cvss_UI_cvss-ui-v2_metrics.json`

| Metric | Value |
|---|---:|
| Total samples | 359 |
| Accuracy | 0.8357 |
| Macro-F1 | 0.7659 |
| Precision (Not Required) | 0.9323 |
| Recall (Not Required) | 0.8581 |
| F1 (Not Required) | 0.8937 |
| Precision (Required) | 0.5591 |
| Recall (Required) | 0.7429 |
| F1 (Required) | 0.6380 |
| Unparsed | 0 |

## Task 6 Stable Patch Classification - stable-v3

Source metrics file: `results/metrics/stable_v3_full_metrics.json`

| Metric | Value |
|---|---:|
| Total samples | 10,895 |
| Correct | 8,978 |
| Accuracy | 0.8240 |
| Precision | 0.8197 |
| Recall | 0.8692 |
| F1 | 0.8437 |
| AUC | 0.8245 |
| Unparsed | 59 |
| True Positive | 5,069 |
| False Positive | 1,115 |
| False Negative | 763 |
| True Negative | 3,948 |

### Compared with local DeepSeek baseline

| Metric | Baseline | stable-v3 | Delta |
|---|---:|---:|---:|
| Accuracy | 0.7734 | 0.8240 | +0.0506 |
| Precision | 0.7552 | 0.8197 | +0.0645 |
| Recall | 0.8553 | 0.8692 | +0.0139 |
| F1 | 0.8021 | 0.8437 | +0.0416 |
| AUC | 0.7680 | 0.8245 | +0.0565 |
| Unparsed | 24 | 59 | +35 |
