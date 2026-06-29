# Log Diagnostics For HiveOS Miner Packaging

Use miner logs to infer required wrapper fixes.

## Install Path Problems

```text
No <miner>/h-manifest.conf
chown: cannot access '/hive/miners/custom/<miner>'
```

Cause: wrong top-level archive folder.

Fix: rebuild archive with top-level folder exactly equal to the custom miner name.

## Permission Problems

```text
h-run.sh: Permission denied
custom exited (exitcode=126)
```

Cause: executable bit missing in archive.

Fix: `chmod +x h-run.sh h-config.sh h-stats.sh scripts/*.sh miner/<binary>` before `tar`.

## Wallet Problems

```text
Invalid wallet
Invalid MDL address
wallet=%WAL%
worker=%WORKER_NAME%
```

Cause: HiveOS template was not expanded by `h-config.sh`.

Fix:

- Source `/hive-config/wallet.conf` and `/hive-config/rig.conf`.
- Expand `%WAL%`, `%WORKER_NAME%`, and `%WORKER%`.
- Split `wallet.worker` carefully.

## Pool/TLS Problems

```text
connect/handshake timed out
tls=False - check the port is reachable and the TLS setting matches the server
```

Fix:

- Verify pool reachability:

```bash
timeout 5 bash -lc 'cat < /dev/null > /dev/tcp/<host>/<port>'
```

- Confirm TLS mode and port.
- Strip URL schemes in `h-config.sh`.

## GPU Memory Problems

```text
workspace_alloc rc=-30
GPU benchmark failed
CUDA out of memory
```

Cause: workload/tuning parameter too high for GPU memory.

Fix:

- Lower the miner workload parameter.
- Test in steps.
- Keep a table of parameter -> result.

Example:

```text
458752 -> workspace_alloc rc=-30
393216 -> works
262144 -> works but lower hashrate
```

## Stats Problems

HiveOS agent sends:

```json
"total_khs":0,"miner_stats":{"status":"running"}
```

Cause: `h-stats.sh` did not set `khs` and `stats` shell variables when sourced.

Fix:

```bash
khs="$total_khs"
stats="$json"
```

Do not only print JSON.

## Accepted Shares But Bad Pool Accounting

Look at accepted shares and payout over time, not only local raw hashrate.

Important signals:

```text
authorize ... -> True
session ready
mining started
accepted=True
submit_share failed
no inbound from pool
```

If network path is unstable, try a TCP proxy or a reliable VPN path. Verify with pool-side statistics.

