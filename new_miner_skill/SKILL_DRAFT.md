# HiveOS Custom Miner Builder Skill

Use this skill when the user provides a raw Linux miner binary, a miner release archive, or miner logs and asks to build a HiveOS custom miner archive.

## Objective

Produce a working HiveOS custom miner `.tar.gz` package that:

- Installs into `/hive/miners/custom/<custom-miner-name>`.
- Starts from a HiveOS flight sheet.
- Correctly maps wallet, worker, pool, TLS, and custom user config.
- Reports hashrate, GPU temperatures, fan speeds, uptime, and shares to the HiveOS dashboard.
- Preserves executable permissions in the archive.

## Required Reading

Before acting, read:

- `README.md`
- `templates/h-manifest.conf`
- `templates/h-config.sh`
- `templates/h-run.sh`
- `templates/h-stats.sh`
- `checklists/build-and-verify.md`
- `checklists/log-diagnostics.md`

## Workflow

1. Identify the custom miner name.
2. Create a staging directory whose top-level folder exactly matches that miner name.
3. Inspect the binary and included libraries:
   - `file <binary>`
   - `ldd <binary>`
   - `strings <binary> | head`
4. Read miner documentation or infer CLI/env arguments from logs and binary strings.
5. Create `h-manifest.conf`.
6. Create `h-config.sh` that translates HiveOS flight sheet variables into miner CLI/env values.
7. Create `h-run.sh` that starts the miner and writes logs.
8. Create `h-stats.sh` that sets HiveOS variables `khs` and `stats` when sourced.
9. Preserve executable bits.
10. Build and checksum the archive.
11. Validate on a HiveOS rig if access is available.
12. If logs show a failure, use `checklists/log-diagnostics.md` to repair the package and rebuild.

## Non-Negotiable HiveOS Rules

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

## Validation Targets

A successful HiveOS run should show:

```text
miner process is running
wallet is not a literal placeholder
pool host and port are correct
benchmark completed
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

- Path or URL to the `.tar.gz`.
- SHA256 checksum.
- Custom miner name.
- Flight sheet fields.
- Custom miner config block.
- Short summary of tested GPUs, workload parameters, and any known limitations.

