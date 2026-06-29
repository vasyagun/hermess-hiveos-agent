#!/usr/bin/env bash
set -u

required_cuda_major="${REQUIRED_CUDA_MAJOR:-}"
required_cuda_minor="${REQUIRED_CUDA_MINOR:-}"
required_min_sm="${REQUIRED_MIN_SM:-}"

if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "[check-driver] ERROR: nvidia-smi not found" >&2
    exit 1
fi

driver="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)"
sm="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)"

echo "[check-driver] driver=${driver:-unknown} sm=${sm:-unknown}"

if [[ -n "$required_min_sm" && -n "$sm" ]]; then
    sm_int="$(printf '%s' "$sm" | awk -F. '{print ($1 * 10) + $2}')"
    if [[ "$sm_int" -lt "$required_min_sm" ]]; then
        echo "[check-driver] ERROR: GPU SM $sm is below required SM $required_min_sm" >&2
        exit 2
    fi
fi

exit 0

