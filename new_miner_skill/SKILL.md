# HiveOS Custom Miner Builder Skill

Use this skill when the user provides a raw Linux miner binary, miner release archive, shell script, batch-like launch script, HiveOS custom miner attempt, or miner logs and asks to build a HiveOS custom miner archive.

The user may call these launch scripts "батники". Treat that as any file or text that starts a miner with CLI flags or environment variables, including `.sh`, `.bat`, `.cmd`, one-line examples from README files, Docker commands, and copied terminal commands.

## Objective

Produce a working HiveOS custom miner `.tar.gz` package that:

- installs into `/hive/miners/custom/<custom-miner-name>`;
- starts from a HiveOS flight sheet;
- maps wallet, worker, pool, TLS, coin/algo, and custom user config;
- reports hashrate, GPU temperatures, fan speeds, uptime, and shares to the HiveOS dashboard;
- preserves executable permissions in the archive.

## Required reading

Before acting, read:

- `README.md`
- `templates/h-manifest.conf`
- `templates/h-config.sh`
- `templates/h-run.sh`
- `templates/h-stats.sh`
- `checklists/build-and-verify.md`
- `checklists/log-diagnostics.md`
- `checklists/agent-task-prompt.md`

## Inputs to collect

Required:

- custom miner name used in HiveOS flight sheet;
- miner binary or release archive;
- launch command, shell script, "батник", README snippet, or logs showing startup arguments;
- target pool URL and TLS mode;
- wallet template, usually `%WAL%.%WORKER_NAME%`;
- coin/algo name;
- expected GPU vendor: NVIDIA, AMD, ASIC, or mixed.

Optional but useful:

- successful miner log;
- failed miner log;
- API port or stats endpoint if the miner has one;
- examples of accepted/rejected share lines;
- required libraries;
- tuning parameters and known good values per GPU model.

## Workflow

1. Identify the custom miner name.
2. Create a staging directory whose top-level folder exactly matches that miner name.
3. Inspect the binary and included libraries:

```bash
file <binary>
ldd <binary>
strings <binary> | head
```

4. Parse the launch script into normalized fields:
   - executable path;
   - pool host/port/scheme;
   - wallet;
   - worker;
   - TLS flag;
   - algo/coin;
   - device selection;
   - extra tuning parameters;
   - log path;
   - API/stats port.
5. Replace hardcoded values with HiveOS variables:
   - wallet -> `CUSTOM_TEMPLATE`, `%WAL%`, `WAL`, `WALLET`;
   - worker -> `%WORKER_NAME%`, `%WORKER%`, `WORKER_NAME`;
   - pool -> `CUSTOM_URL`;
   - extra options -> whitelisted `CUSTOM_USER_CONFIG`.
6. Create `h-manifest.conf`.
7. Create `h-config.sh` that translates HiveOS flight sheet variables into miner CLI/env values.
8. Create `h-run.sh` that starts the miner and writes logs.
9. Create `h-stats.sh` that sets HiveOS variables `khs` and `stats` when sourced.
10. Preserve executable bits.
11. Build and checksum the archive.
12. Validate archive structure and permissions.
13. Validate on a HiveOS rig if access is available.
14. If logs show a failure, use `checklists/log-diagnostics.md`, repair, and rebuild.

## Batch/script conversion rules

When converting launch scripts:

- treat Windows line continuations `^` and Linux line continuations `\` as command continuation;
- strip `set VAR=value`, `export VAR=value`, and inline `VAR=value command` into environment assignments;
- convert `%WAL%`, `%WORKER_NAME%`, `%WORKER%`, `$WAL`, `$WORKER_NAME`, `${WAL}` into HiveOS-aware expansion in `h-config.sh`;
- do not preserve local absolute paths from the original script unless they point inside the package;
- move bundled `.so` files to `miner/lib/` and set `LD_LIBRARY_PATH` in `h-run.sh`;
- keep unknown miner flags, but make hardcoded wallet/pool/worker values configurable;
- never use `eval` for `CUSTOM_USER_CONFIG`;
- whitelist custom config keys before export.

Example input:

```bash
./unknown-miner --pool stratum+tcp://pool.example.com:3333 --user WALLET.rig01 --pass x --algo coin --tls 0 --work 393216
```

HiveOS mapping:

```text
CUSTOM_URL=pool.example.com:3333
CUSTOM_TEMPLATE=%WAL%.%WORKER_NAME%
CUSTOM_USER_CONFIG:
MINER_ALGO=coin
MINER_TLS=0
MINER_WORK=393216
```

`h-run.sh` should build the actual command from those variables instead of keeping `WALLET.rig01`.

## Non-negotiable HiveOS rules

- The archive top-level directory must equal the HiveOS `CUSTOM_MINER` value.
- `h-run.sh`, `h-config.sh`, `h-stats.sh`, helper scripts, and the miner binary must be executable.
- `h-stats.sh` must set shell variables:

```bash
khs=<numeric_khs>
stats=<compact_json>
```

- Do not rely only on printing JSON from `h-stats.sh`; HiveOS sources it and redirects output.
- Use `${BASH_SOURCE[0]}` to find the script directory when a file may be sourced.
- Do not use `eval` on `CUSTOM_USER_CONFIG`.
- Whitelist allowed environment variable names from `CUSTOM_USER_CONFIG`.
- Keep secrets out of `h-manifest.conf`.

## Stats strategy

Prefer stats sources in this order:

1. Miner HTTP/API endpoint, if stable and documented.
2. Miner JSON or structured log lines.
3. Human log lines with hashrate/share regexes.
4. Conservative fallback: report `0` hashrate with real temp/fan telemetry until parser is known.

Recommended JSON fields:

```json
{
  "khs": 12345,
  "total_khs": 12345,
  "hs_units": "khs",
  "hs": [12345],
  "temp": [57],
  "fan": [60],
  "uptime": 420,
  "ver": "1.0.0",
  "ar": [10, 0],
  "algo": "example",
  "bus_numbers": [3]
}
```

## Validation targets

A successful HiveOS run should show:

```text
miner process is running
wallet is not a literal placeholder
pool host and port are correct
benchmark completed or mining started
authorize -> True
session ready
accepted=True
```

The HiveOS agent log should show nonzero hashrate:

```json
"miner":"custom",
"total_khs":12345,
"miner_stats":{"status":"running","total_khs":12345}
```

## Deliverables

Return:

- path or URL to the `.tar.gz`;
- SHA256 checksum;
- custom miner name;
- flight sheet fields;
- custom miner config block;
- validation commands;
- short summary of tested GPUs, workload parameters, and known limitations.

