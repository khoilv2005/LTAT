#!/usr/bin/env bash
set -u

PROJECT_ID="${PROJECT_ID:-project-d27153a4-d9d1-4bcc-93a}"
LOCATION="${LOCATION:-global}"
MODEL="${MODEL:-gemini-3-flash-preview}"
API_URL="${API_URL:-https://aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}/publishers/google/models/${MODEL}:generateContent}"
MAX_PARALLEL_JOBS="${MAX_PARALLEL_JOBS:-3}"
RESPONSE_MAX_TOKEN="${RESPONSE_MAX_TOKEN:-512}"
VERTEX_ACCESS_TOKEN_COMMAND="${VERTEX_ACCESS_TOKEN_COMMAND:-gcloud auth print-access-token}"
RESULT_NAMESPACE="${RESULT_NAMESPACE:-vertex_gemini3}"

export API_URL MODEL MAX_PARALLEL_JOBS RESPONSE_MAX_TOKEN VERTEX_ACCESS_TOKEN_COMMAND RESULT_NAMESPACE

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$ROOT/tools/run_gemini3_baseline_rag_parallel.sh"
