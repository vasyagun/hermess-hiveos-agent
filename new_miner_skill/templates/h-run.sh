#!/usr/bin/env bash
set -u

cd "$(dirname "$0")" || exit 1

# shellcheck source=h-manifest.conf disable=SC1091
. ./h-manifest.conf

# shellcheck source=h-config.sh disable=SC1091
. ./h-config.sh

MINER_DIR="$(pwd)"
BINARY="$MINER_DIR/miner/example-miner"
LOG_DIR="/var/log/miner/${CUSTOM_NAME:-example-miner}"
mkdir -p "$LOG_DIR" /run/hive

if [[ -d "$MINER_DIR/miner/lib" ]]; then
    export LD_LIBRARY_PATH="$MINER_DIR/miner/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

if [[ ! -x "$BINARY" ]]; then
    echo "[h-run] ERROR: binary is not executable: $BINARY" >&2
    exit 126
fi

echo "[$(date -u +%FT%TZ)] launching $BINARY" >> "$LOG_DIR/h-run.log"
echo "[$(date -u +%FT%TZ)] pool=${MINER_POOL_HOST}:${MINER_POOL_PORT} wallet=${MINER_WALLET} worker=${MINER_WORKER}" >> "$LOG_DIR/h-run.log"

# Replace this argument list with the real miner CLI.
exec "$BINARY" \
    --pool "${MINER_POOL_HOST}:${MINER_POOL_PORT}" \
    --wallet "$MINER_WALLET" \
    --worker "$MINER_WORKER" \
    2>&1

