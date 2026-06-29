#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for hive_conf in /hive-config/wallet.conf /hive-config/rig.conf; do
    if [[ -r "$hive_conf" ]]; then
        # shellcheck source=/dev/null disable=SC1090
        . "$hive_conf"
    fi
done

HIVE_CUSTOM_TEMPLATE="${CUSTOM_TEMPLATE:-}"
HIVE_CUSTOM_URL="${CUSTOM_URL:-}"
HIVE_CUSTOM_USER_CONFIG="${CUSTOM_USER_CONFIG:-}"

# shellcheck source=h-manifest.conf disable=SC1091
. "$SCRIPT_DIR/h-manifest.conf"

[[ -n "$HIVE_CUSTOM_TEMPLATE" ]] && CUSTOM_TEMPLATE="$HIVE_CUSTOM_TEMPLATE"
[[ -n "$HIVE_CUSTOM_URL" ]] && CUSTOM_URL="$HIVE_CUSTOM_URL"
[[ -n "$HIVE_CUSTOM_USER_CONFIG" ]] && CUSTOM_USER_CONFIG="$HIVE_CUSTOM_USER_CONFIG"

template="${CUSTOM_TEMPLATE:-%WAL%.%WORKER_NAME%}"
template="${template//%WORKER_NAME%/${WORKER_NAME:-default}}"
template="${template//%WORKER%/${WORKER_NAME:-default}}"
if [[ "$template" == *"%WAL%"* ]]; then
    hive_wallet="${WAL:-${WALLET:-${CUSTOM_WALLET:-}}}"
    if [[ -n "$hive_wallet" ]]; then
        template="${template//%WAL%/$hive_wallet}"
    fi
fi

wallet="${template%%.*}"
worker="${template#*.}"
[[ "$worker" == "$template" ]] && worker="${WORKER_NAME:-default}"

export MINER_WALLET="$wallet"
export MINER_WORKER="$worker"

pool_url="${CUSTOM_URL%%,*}"
pool_url="${pool_url#stratum+tcp://}"
pool_url="${pool_url#tcp://}"
pool_url="${pool_url#ssl://}"
pool_url="${pool_url#stratum+ssl://}"

pool_host="${pool_url%%:*}"
pool_port="${pool_url##*:}"
[[ "$pool_port" == "$pool_url" ]] && pool_port=3333

export MINER_POOL_HOST="$pool_host"
export MINER_POOL_PORT="$pool_port"

# Whitelist extra flight sheet variables. Never eval arbitrary user config.
if [[ -n "${CUSTOM_USER_CONFIG:-}" ]]; then
    while IFS= read -r line; do
        line="${line%%#*}"
        line="$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        [[ -z "$line" ]] && continue
        [[ "$line" =~ ^(MINER_[A-Z0-9_]+|POOL_HOST|POOL_PORT|POOL_TLS|WALLET|WORKER)= ]] || continue
        # shellcheck disable=SC2163
        export "$line"
    done < <(printf '%s\n' "$CUSTOM_USER_CONFIG" | tr ';' '\n')
fi

export MINER_LOG_LEVEL="${MINER_LOG_LEVEL:-info}"
export MINER_API_PORT="${MINER_API_PORT:-0}"

mkdir -p "/var/log/miner/${CUSTOM_NAME:-example-miner}" /run/hive

