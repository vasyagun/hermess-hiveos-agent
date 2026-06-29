# Suggested Task Prompt For An AI Agent

You are given a raw Linux miner binary or release archive. Build a HiveOS custom miner package.

Requirements:

1. Inspect the miner binary, included libraries, documentation, and sample logs.
2. Create a HiveOS package with:
   - `h-manifest.conf`
   - `h-config.sh`
   - `h-run.sh`
   - `h-stats.sh`
   - `miner/<binary>`
   - any required libraries under `miner/lib/`
3. The archive top-level folder must exactly match `CUSTOM_MINER`.
4. Preserve executable permissions.
5. Map HiveOS flight sheet values into the miner CLI or environment.
6. Parse logs or API output to set HiveOS `khs` and `stats` variables.
7. Validate by running:
   - archive structure check
   - permission check
   - manual `h-stats.sh` check
   - miner startup check
   - HiveOS agent stats check
8. If the miner fails, infer the reason from logs and adjust:
   - archive folder
   - permissions
   - wallet/template parsing
   - pool/TLS config
   - GPU workload parameter
   - stats parser

Do not return only a theoretical plan. Produce the fixed archive and the exact flight sheet settings needed to run it.

