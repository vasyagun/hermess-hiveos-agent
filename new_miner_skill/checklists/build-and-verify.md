# Build And Verify Checklist

## Inputs

- Raw miner binary or release archive.
- Miner CLI documentation, if available.
- Sample miner logs from a successful or failed run.
- Pool host/port/TLS requirements.
- Wallet template format.
- Known extra tuning parameters.

## Build Steps

1. Create a staging folder named exactly as the HiveOS custom miner name.
2. Put scripts at the staging root:
   - `h-manifest.conf`
   - `h-config.sh`
   - `h-run.sh`
   - `h-stats.sh`
3. Put the binary under `miner/`.
4. Put required libraries under `miner/lib/`.
5. Put helper scripts under `scripts/`.
6. Ensure executable bits:

```bash
chmod +x <miner>/h-run.sh <miner>/h-config.sh <miner>/h-stats.sh
chmod +x <miner>/scripts/*.sh
chmod +x <miner>/miner/<binary>
```

7. Build:

```bash
tar -czf <miner>-fixed.tar.gz <miner>
sha256sum <miner>-fixed.tar.gz > <miner>-fixed.tar.gz.sha256
```

## Archive Verification

```bash
tar -tzf <miner>-fixed.tar.gz | head
tar -tzvf <miner>-fixed.tar.gz | grep -E '<miner>/(h-run.sh|h-config.sh|h-stats.sh|miner/<binary>)$'
```

Check for:

- Single top-level folder.
- Folder name equals custom miner name.
- `h-run.sh`, `h-config.sh`, `h-stats.sh`, helper scripts, and binary are executable.

## HiveOS Installation Verification

```bash
ls -la /hive/miners/custom/<miner>
CUSTOM_MINER=<miner> MINER_DIR=/hive/miners/custom bash /hive/miners/custom/h-stats.sh
miner restart
tail -n 100 /var/log/miner/<miner>/<miner>.log
tail -n 100 /var/log/hive-agent.log | grep '"method":"stats"'
```

Expected agent stats include nonzero `total_khs` and non-null `miner_stats`.

