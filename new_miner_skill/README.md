# HiveOS Custom Miner Packaging Guide

This guide is intended for an AI agent that receives a raw Linux miner binary and miner logs, then builds a working HiveOS custom miner archive.

The output must be a `.tar.gz` archive that HiveOS can install as a custom miner, launch from a flight sheet, and report hashrate, temperature, fan, uptime, and shares to the HiveOS dashboard.

## Required Archive Shape

HiveOS expects the archive to extract into exactly one top-level directory. That directory name must match the custom miner name used in the flight sheet.

Correct:

```text
modelos-miner/
modelos-miner/h-manifest.conf
modelos-miner/h-config.sh
modelos-miner/h-run.sh
modelos-miner/h-stats.sh
modelos-miner/miner/modelos-miner
modelos-miner/miner/lib/...
modelos-miner/scripts/...
```

If the flight sheet miner name is `modelos-miner`, the archive top-level folder must be `modelos-miner`, not `modelos-miner-2.2.0`, not `modelos-miner-fixed8`, and not a nested folder.

Bad archive symptoms:

```text
chown: cannot access '/hive/miners/custom/<miner-name>': No such file or directory
No <miner-name>/h-manifest.conf
```

## Required File Permissions

The archive must preserve executable bits. If it does not, HiveOS fails with exit code 126:

```text
/hive/miners/custom/h-run.sh: line 15: /hive/miners/custom/<miner-name>/h-run.sh: Permission denied
custom exited (exitcode=126)
```

Required permissions:

```bash
chmod +x h-run.sh h-config.sh h-stats.sh
chmod +x scripts/*.sh
chmod +x miner/<binary-name>
```

Shared libraries should normally be readable, not executable:

```bash
chmod 0644 miner/lib/*.so*
```

## HiveOS File Contract

HiveOS root wrappers live in `/hive/miners/custom/` and delegate into `/hive/miners/custom/$CUSTOM_MINER/`.

The package must provide:

```text
h-manifest.conf
h-config.sh
h-run.sh
h-stats.sh
```

### h-manifest.conf

Static defaults and metadata. It must not contain user-specific secrets. It may include safe defaults for template, pool URL, algo, and log basename.

### h-config.sh

Translates HiveOS flight sheet variables into environment variables understood by the miner.

Common HiveOS variables:

```bash
CUSTOM_TEMPLATE      # usually wallet.worker, often expanded from %WAL%.%WORKER_NAME%
CUSTOM_URL           # pool host:port
CUSTOM_USER_CONFIG   # extra KEY=value lines from "Custom miner config"
WORKER_NAME          # rig name
```

Important: source `/hive-config/wallet.conf` and `/hive-config/rig.conf` defensively because HiveOS does not always export every custom value into the miner process.

### h-run.sh

Starts the miner. It must:

1. `cd` into its own package directory.
2. Source `h-manifest.conf`.
3. Source `h-config.sh`.
4. Prepare `LD_LIBRARY_PATH` if bundled libraries exist.
5. Create log/runtime directories.
6. `exec` the miner process.

### h-stats.sh

This is the most important compatibility point.

HiveOS does not simply execute `h-stats.sh` and parse stdout. The HiveOS agent runs it like this:

```bash
cd /hive/miners/<miner>
{ source h-manifest.conf; source h-config.sh; source h-stats.sh; } 1>&2
printf "%q\n" "$khs"
echo "$stats"
```

Therefore `h-stats.sh` must set shell variables:

```bash
khs=<number>
stats=<compact-json>
```

When executed directly, it is useful to print two lines for manual debugging:

```text
<khs>
<json>
```

Do not rely only on `echo "$json"` inside `h-stats.sh`. HiveOS will ignore it because sourced output is redirected to stderr.

## HiveOS Stats JSON

Recommended fields:

```json
{
  "khs": 218000000000,
  "total_khs": 218000000000,
  "hs_units": "khs",
  "hs": [218000000000],
  "temp": [57],
  "fan": [60],
  "uptime": 420,
  "ver": "2.2.0",
  "ar": [634, 19],
  "algo": "modelos",
  "bus_numbers": [3]
}
```

Notes:

- `khs` and `total_khs` should be numeric.
- `hs` should be an array with one value per GPU.
- `temp` and `fan` should be arrays aligned with GPU order.
- `ar` is accepted/rejected shares.
- `bus_numbers` helps HiveOS map stats to GPUs.
- If exact per-GPU hashrate is unavailable, do not blindly divide total hashrate across GPUs unless that is the least bad option. Prefer parsing per-worker log lines if available.

## Flight Sheet Mapping

Example flight sheet fields:

```text
Miner name: modelos-miner
Installation URL: http://server/releases/modelos-miner-fixed.tar.gz
Pool URL: pool.example.com:5566
Wallet and worker template: %WAL%.%WORKER_NAME%
Wallet: mdl1...
Custom miner config:
MODELOS_MINE_M=528384
MODELOS_POOL_PEARL_WALLET=prl1...
```

The package should parse `CUSTOM_USER_CONFIG` as newline-separated or semicolon-separated `KEY=value` assignments. Only export allowed keys. Do not eval arbitrary user text.

## Log-Driven Configuration Workflow

1. Install and run the miner with conservative defaults.
2. Read miner startup logs.
3. Confirm wallet expansion. If logs show `wallet=%WAL%`, `h-config.sh` failed to consume HiveOS template values.
4. Confirm pool endpoint and TLS.
5. Confirm benchmark success.
6. If logs show memory/workspace errors, reduce the miner workload parameter.
7. Confirm `authorize -> True`.
8. Confirm `session ready`.
9. Confirm `accepted=True` shares.
10. Confirm HiveOS dashboard stats by checking `/var/log/hive-agent.log`.

Useful log patterns:

```text
Invalid MDL address
workspace_alloc rc=-30
authorize ... -> True
session ready
mining started
accepted=True
submit_share failed
no inbound from pool
Permission denied
```

## Common Failure Modes

### Archive Folder Name Mismatch

HiveOS installs to `/hive/miners/custom/$CUSTOM_MINER`. If archive extracts as a different folder name, install fails.

Fix: rebuild archive with the top-level directory exactly equal to the miner name.

### Executable Bit Missing

Symptom:

```text
h-run.sh: Permission denied
exitcode=126
```

Fix: `chmod +x` scripts and binary before creating the tarball.

### Wallet Placeholder Leaks

Symptom:

```text
wallet=%WAL% worker=%WORKER_NAME%
Invalid MDL address
```

Fix: source HiveOS config files and expand `%WAL%`, `%WORKER_NAME%`, and `%WORKER%` in `h-config.sh`.

### Stats Show Running But Hashrate Is Zero

Symptom in `/var/log/hive-agent.log`:

```json
"miner":"custom","total_khs":0,"miner_stats":{"status":"running"}
```

Cause: `h-stats.sh` printed JSON but did not set `khs` and `stats` variables when sourced.

Fix: assign `khs` and `stats` in `h-stats.sh`.

### Stats Script Uses `$0`

When HiveOS sources `h-stats.sh`, `$0` points to the wrapper, not the script. Use:

```bash
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
```

### Miner Works But Pool Accounting Is Poor

Raw local hashrate can be misleading. Optimize for accepted shares and payout per block over time.

For memory/workspace parameters, test one variable at a time. Example from RTX 3090 / RTX 5090 tuning:

```text
RTX 3090 24 GB:
458752 -> workspace_alloc rc=-30
393216 -> works, about 55-58 TH/s per GPU
262144 -> works, lower hashrate

RTX 5090 32 GB:
528384 -> works and improves pool accounting, about 218-220 TH/s
```

## Packaging Command

Build from a staging directory whose top-level folder is the miner name:

```bash
cd /tmp/package-build
chmod +x modelos-miner/h-run.sh modelos-miner/h-config.sh modelos-miner/h-stats.sh
chmod +x modelos-miner/scripts/*.sh modelos-miner/miner/modelos-miner
tar -czf modelos-miner-fixed.tar.gz modelos-miner
sha256sum modelos-miner-fixed.tar.gz > modelos-miner-fixed.tar.gz.sha256
```

Verify:

```bash
tar -tzvf modelos-miner-fixed.tar.gz | head
tar -tzvf modelos-miner-fixed.tar.gz | grep -E 'h-run.sh|h-stats.sh|h-config.sh|miner/.+$'
```

## Minimal Validation Commands On HiveOS

```bash
ls -l /hive/miners/custom/<miner-name>/
CUSTOM_MINER=<miner-name> MINER_DIR=/hive/miners/custom bash /hive/miners/custom/h-stats.sh
tail -n 100 /var/log/miner/<miner-name>/<miner-name>.log
tail -n 100 /var/log/hive-agent.log | grep '"method":"stats"'
miner restart
```
