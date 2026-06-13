#!/usr/bin/env bash
set -u

API_URL="${API_URL:-https://ollama.com/api/chat}"
MODEL="${MODEL:-gemini-3-flash-preview:cloud}"
MAX_PARALLEL_JOBS="${MAX_PARALLEL_JOBS:-3}"
RESPONSE_MAX_TOKEN="${RESPONSE_MAX_TOKEN:-512}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

RESULT_ROOT="$ROOT/results/gemini3"
BASELINE_ROOT="$RESULT_ROOT/baseline"
RAG_ROOT="$RESULT_ROOT/rag"
METRIC_ROOT="$ROOT/results/metrics/gemini3"
LOG_DIR="$RESULT_ROOT/parallel_logs"
mkdir -p "$BASELINE_ROOT" "$RAG_ROOT" "$METRIC_ROOT" "$LOG_DIR"

JOBS=(
  "gemini3_baseline_sbrp_ambari|baseline|SBRP|Ambari|expertise|0|500|"
  "gemini3_baseline_sbrp_camel|baseline|SBRP|Camel|expertise|0|500|"
  "gemini3_baseline_sbrp_derby|baseline|SBRP|Derby|expertise|0|500|"
  "gemini3_baseline_sbrp_wicket|baseline|SBRP|Wicket|expertise|0|500|"
  "gemini3_baseline_cvss_av|baseline|cvss|AV|self-heuristic|0|487|--heuristics_file results/heuristics/cvss_AV_heuristics.json --task_type CVSS"
  "gemini3_baseline_cvss_ac|baseline|cvss|AC|self-heuristic|0|373|--heuristics_file results/heuristics/cvss_AC_heuristics.json --task_type CVSS"
  "gemini3_baseline_cvss_pr|baseline|cvss|PR|self-heuristic|0|414|--heuristics_file results/heuristics/cvss_PR_heuristics.json --task_type CVSS"
  "gemini3_baseline_cvss_ui|baseline|cvss|UI|self-heuristic|0|359|--heuristics_file results/heuristics/cvss_UI_heuristics.json --task_type CVSS"
  "gemini3_baseline_stable|baseline|stable|stable_patchnet|expertise|0|10895|"
  "gemini3_baseline_sbrp_chromium|baseline|SBRP|Chromium|expertise|0|20970|"
  "gemini3_baseline_title_title_itape|baseline|title|title_itape|few-shot|0|33438|"
  "gemini3_rag_sbrp_ambari|rag|SBRP|Ambari||0|500|"
  "gemini3_rag_sbrp_camel|rag|SBRP|Camel||0|500|"
  "gemini3_rag_sbrp_derby|rag|SBRP|Derby||0|500|"
  "gemini3_rag_sbrp_wicket|rag|SBRP|Wicket||0|500|"
  "gemini3_rag_cvss_av|rag|cvss|AV||0|487|"
  "gemini3_rag_cvss_ac|rag|cvss|AC||0|373|"
  "gemini3_rag_cvss_pr|rag|cvss|PR||0|414|"
  "gemini3_rag_cvss_ui|rag|cvss|UI||0|359|"
  "gemini3_rag_apca_invalidator|rag|APCA|APCA_invalidator||0|139|"
  "gemini3_rag_apca_panther|rag|APCA|APCA_panther||0|208|"
  "gemini3_rag_apca_quatrain|rag|APCA|APCA_quatrain||0|995|"
  "gemini3_rag_stable|rag|stable|stable_patchnet||0|10895|"
  "gemini3_rag_sbrp_chromium|rag|SBRP|Chromium||0|20970|"
  "gemini3_rag_title_title_itape|rag|title|title_itape||0|33438|"
)

json_count() {
  local path="$1"
  [[ -f "$path" ]] || { echo 0; return; }
  "$PYTHON" - "$path" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    print(len(data) if isinstance(data, list) else 0)
except Exception:
    print(0)
PY
}

baseline_result_name() {
  local task="$1" dataset="$2" method="$3"
  echo "${task}_${dataset}_${method}_test"
}

result_path() {
  local name="$1" kind="$2" task="$3" dataset="$4" method="$5"
  if [[ "$kind" == "baseline" ]]; then
    echo "$BASELINE_ROOT/$(baseline_result_name "$task" "$dataset" "$method").json"
  else
    echo "$RAG_ROOT/${name}.json"
  fi
}

eval_job() {
  local name="$1" task="$2" dataset="$3" result="$4"
  [[ -f "$result" ]] || { echo "SKIP eval missing result $name"; return; }
  "$PYTHON" "$ROOT/tools/evaluate_rag_metrics.py" "$result" \
    --task "$task" \
    --dataset "$dataset" \
    --name "$name" \
    --output "$METRIC_ROOT/${name}.json" \
    > "$LOG_DIR/${name}.metrics.out.log" \
    2> "$LOG_DIR/${name}.metrics.err.log"
  echo "EVAL done $name"
}

run_job() {
  local spec="$1"
  IFS='|' read -r name kind task dataset method n expected extra <<< "$spec"
  local result metric out err
  result="$(result_path "$name" "$kind" "$task" "$dataset" "$method")"
  metric="$METRIC_ROOT/${name}.json"
  out="$LOG_DIR/${name}.out.log"
  err="$LOG_DIR/${name}.err.log"

  local count
  count="$(json_count "$result")"
  if [[ "$count" -ge "$expected" && -f "$metric" ]]; then
    echo "SKIP completed $name $count/$expected"
    return 0
  fi

  echo "START $name"
  if [[ "$kind" == "baseline" ]]; then
    # shellcheck disable=SC2086
    "$PYTHON" -u "$ROOT/run.py" \
      --task "$task" \
      --dataset "$dataset" \
      --method "$method" \
      --TEST test \
      --testNum "$n" \
      --api_url "$API_URL" \
      --model "$MODEL" \
      --result_root "$BASELINE_ROOT" \
      --max_requests_per_minute 30 \
      --max_tokens_per_minute 1000000 \
      --max_concurrent_requests 1 \
      --save_every 25 \
      --response_max_token "$RESPONSE_MAX_TOKEN" \
      $extra > "$out" 2> "$err"
  else
    # shellcheck disable=SC2086
    "$PYTHON" -u "$ROOT/run_rag.py" \
      --task "$task" \
      --dataset "$dataset" \
      --TEST test \
      --testNum "$n" \
      --api_url "$API_URL" \
      --model "$MODEL" \
      --result_root "$RAG_ROOT" \
      --result_file_name "$name" \
      --max_requests_per_minute 30 \
      --max_tokens_per_minute 1000000 \
      --max_concurrent_requests 1 \
      --save_every 25 \
      --response_max_token "$RESPONSE_MAX_TOKEN" \
      $extra > "$out" 2> "$err"
  fi

  local code=$?
  echo "DONE $name exit=$code"
  if [[ "$code" -eq 0 ]]; then
    eval_job "$name" "$task" "$dataset" "$result"
  else
    echo "FAILED run $name stderr=$err"
  fi
  return "$code"
}

active=0
for spec in "${JOBS[@]}"; do
  run_job "$spec" &
  active=$((active + 1))
  if [[ "$active" -ge "$MAX_PARALLEL_JOBS" ]]; then
    wait -n
    active=$((active - 1))
  fi
done

while [[ "$active" -gt 0 ]]; do
  wait -n
  active=$((active - 1))
done

echo "Gemini parallel baseline/RAG queue finished."
