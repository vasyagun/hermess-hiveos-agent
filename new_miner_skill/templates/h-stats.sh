#!/usr/bin/env bash

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=h-manifest.conf disable=SC1091
. "$script_dir/h-manifest.conf" 2>/dev/null || true

miner_name="${CUSTOM_NAME:-example-miner}"
miner_version="${CUSTOM_VERSION:-unknown}"
log_file="/var/log/miner/$miner_name/$miner_name.log"
screen_copy="/tmp/${miner_name}-hstats-screen.txt"

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    hstats_sourced=1
else
    hstats_sourced=0
fi

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g;s/"/\\"/g'
}

json_array_numbers() {
    local first=1 value
    printf '['
    for value in "$@"; do
        [[ "$first" -eq 0 ]] && printf ','
        first=0
        [[ -n "$value" ]] || value=0
        printf '%s' "$value"
    done
    printf ']'
}

read_gpu_telemetry() {
    temps=()
    fans=()
    bus_numbers=()

    local idx bus temp fan bus_hex bus_num
    while IFS=, read -r idx bus temp fan; do
        temp="$(printf '%s' "$temp" | tr -dc '0-9')"
        fan="$(printf '%s' "$fan" | tr -dc '0-9')"
        bus="$(printf '%s' "$bus" | tr -d '[:space:]')"
        bus_hex="$(printf '%s' "$bus" | awk -F: '{print $2}' 2>/dev/null | tr -dc '0-9A-Fa-f')"
        if [[ -n "$bus_hex" ]]; then
            bus_num="$((16#$bus_hex))"
        else
            bus_num=0
        fi
        temps+=("${temp:-0}")
        fans+=("${fan:-0}")
        bus_numbers+=("$bus_num")
    done < <(nvidia-smi --query-gpu=index,pci.bus_id,temperature.gpu,fan.speed --format=csv,noheader,nounits 2>/dev/null)

    if [[ "${#temps[@]}" -eq 0 ]]; then
        temps=(0)
        fans=(0)
        bus_numbers=(0)
    fi
}

miner_uptime() {
    local pid etime
    pid="$(pgrep -f "$script_dir/miner/" | head -n1 || true)"
    if [[ -n "$pid" ]]; then
        etime="$(ps -o etimes= -p "$pid" 2>/dev/null | tr -dc '0-9')"
        printf '%s' "${etime:-0}"
    else
        printf '0'
    fi
}

to_khs_from_unit() {
    local value="$1" unit="$2"
    awk -v v="$value" -v u="$unit" 'BEGIN {
        if (u == "kh/s" || u == "khs") printf "%.0f", v;
        else if (u == "mh/s" || u == "mhs") printf "%.0f", v * 1000;
        else if (u == "gh/s" || u == "ghs") printf "%.0f", v * 1000000;
        else if (u == "th/s" || u == "ths") printf "%.0f", v * 1000000000;
        else if (u == "h/s" || u == "hs") printf "%.0f", v / 1000;
        else printf "%.0f", v;
    }'
}

extract_total_khs_from_log() {
    local line value unit
    line="$(grep -Eai 'hashrate|hashes/s|speed|[0-9.]+[[:space:]]*[KMGT]?H/s' "$log_file" 2>/dev/null | tail -n1 || true)"

    if [[ "$line" =~ ([0-9]+([.][0-9]+)?)[[:space:]]*(TH/s|GH/s|MH/s|KH/s|H/s|ths|ghs|mhs|khs|hs) ]]; then
        value="${BASH_REMATCH[1]}"
        unit="$(printf '%s' "${BASH_REMATCH[3]}" | tr '[:upper:]' '[:lower:]')"
        to_khs_from_unit "$value" "$unit"
    else
        printf '0'
    fi
}

extract_shares_from_log() {
    local accepted rejected
    accepted="$(grep -Eaci 'accepted|accepted=True|share accepted' "$log_file" 2>/dev/null || true)"
    rejected="$(grep -Eaci 'rejected|accepted=False|invalid share|submit_share failed' "$log_file" 2>/dev/null || true)"
    printf '%s %s' "${accepted:-0}" "${rejected:-0}"
}

emit_stats() {
    local total_khs="$1" uptime="$2" accepted="$3" rejected="$4"
    local gpu_count="${#temps[@]}"
    local hs=()
    local per_gpu=0
    local i

    if [[ "$gpu_count" -gt 0 && "$total_khs" -gt 0 ]]; then
        per_gpu="$((total_khs / gpu_count))"
    fi

    for ((i = 0; i < gpu_count; i++)); do
        hs+=("$per_gpu")
    done

    khs="$total_khs"
    stats="$(printf '{"khs":%s,"total_khs":%s,"hs_units":"khs","hs":%s,"temp":%s,"fan":%s,"uptime":%s,"ver":"%s","ar":[%s,%s],"algo":"%s","bus_numbers":%s}' \
        "$total_khs" \
        "$total_khs" \
        "$(json_array_numbers "${hs[@]}")" \
        "$(json_array_numbers "${temps[@]}")" \
        "$(json_array_numbers "${fans[@]}")" \
        "$uptime" \
        "$(json_escape "$miner_version")" \
        "$accepted" \
        "$rejected" \
        "$(json_escape "${CUSTOM_ALGO:-unknown}")" \
        "$(json_array_numbers "${bus_numbers[@]}")")"

    if [[ "$hstats_sourced" -eq 0 ]]; then
        printf '%s\n%s\n' "$khs" "$stats"
    fi
}

read_gpu_telemetry
uptime_seconds="$(miner_uptime)"
total_khs="$(extract_total_khs_from_log)"
read -r accepted rejected < <(extract_shares_from_log)

emit_stats "$total_khs" "$uptime_seconds" "$accepted" "$rejected"

