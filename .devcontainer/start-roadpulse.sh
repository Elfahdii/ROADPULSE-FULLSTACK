#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${repo_root}/.codespaces"
mkdir -p "${runtime_dir}/matplotlib"

if ! curl --silent --fail http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  (
    cd "${repo_root}/backend"
    nohup env \
      MPLCONFIGDIR="${runtime_dir}/matplotlib" \
      PYTHONDONTWRITEBYTECODE=1 \
      python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
      >"${runtime_dir}/backend.log" 2>&1 &
  )
fi

for _ in $(seq 1 120); do
  if curl --silent --fail http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl --silent --fail http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  echo "RoadPulse backend did not become ready. See ${runtime_dir}/backend.log" >&2
  exit 1
fi

if ! curl --silent --fail http://127.0.0.1:5173 >/dev/null 2>&1; then
  (
    cd "${repo_root}"
    nohup env VITE_API_URL=same-origin npm --prefix frontend run dev -- --host 0.0.0.0 --port 5173 \
      >"${runtime_dir}/frontend.log" 2>&1 &
  )
fi

echo "RoadPulse is starting on forwarded port 5173. Set that port's visibility to Public."
