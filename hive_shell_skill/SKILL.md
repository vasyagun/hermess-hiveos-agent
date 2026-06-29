# HiveOS Hive Shell Operator Skill

Use this skill when the user asks the agent to connect to a HiveOS rig that has no public IP and perform terminal work through Hive Shell / `hssh`: deploy a node, install a release from GitHub, generate a wallet, inspect logs, restart a service, or resume a long-running setup.

## Objective

Create a reliable remote-terminal workflow for HiveOS rigs behind NAT:

- find the target farm and worker;
- request a temporary Hive Shell session through HiveOS API;
- wait for the delayed shell link/message;
- connect through that shell path when the runtime supports it;
- execute the user's terminal task safely;
- make long-running work resumable with `tmux`, `systemd`, PID files, logs, and idempotent scripts;
- regenerate Hive Shell when the link expires and continue by checking process/service state.

## Required HiveOS API

Base URL:

```text
https://api2.hiveos.farm/api/v2
```

Auth:

```http
Authorization: Bearer <HIVEOS_API_TOKEN>
Accept: application/json
Content-Type: application/json
```

Resolve target:

```http
GET /farms
GET /farms/{farmId}/workers
GET /farms/{farmId}/workers/{workerId}
```

Start Hive Shell:

```http
POST /farms/{farmId}/workers/{workerId}/command
```

Payload:

```json
{"command":"hssh","data":{"action":"start"}}
```

Stop or restart Hive Shell if needed:

```json
{"command":"hssh","data":{"action":"stop"}}
{"command":"hssh","data":{"action":"restart"}}
```

Poll messages for the delayed result:

```http
GET /farms/{farmId}/workers/{workerId}/messages?with_payload=1&start_time=<unix_ts>&per_page=25
GET /farms/{farmId}/workers/messages?worker_ids=<workerId>&with_payload=1&start_time=<unix_ts>
```

The link/connection string usually arrives in a worker message payload or command result after a delay. Extract:

- an `ssh ...` command, if present;
- a `https://...` shell/hive/hssh URL, if present;
- command id and message id for audit.

## Agent commands

Telegram command surface:

```text
/hssh farm:<id|name> worker:<id|name>
/hive_shell farm:<id|name> worker:<id|name>
/node_deploy farm:<id|name> worker:<id|name> repo:<github-url> name:<project-name>
```

Natural language:

```text
Подключись к rig1
Разверни ноду на rig1, релиз: https://github.com/org/project/releases/tag/v1.2.3
Сгенерируй кошелек для проекта X на rig1
Проверь статус синхронизации ноды на rig1
```

## Safety policy

Read-only actions can run after target resolution:

- inspect OS/GPU/disk;
- check process/service status;
- tail logs;
- check sync height/status;
- read public node status.

Require explicit confirmation before:

- installing packages;
- writing system files;
- opening firewall ports;
- creating/removing systemd units;
- changing miner/driver/HiveOS config;
- killing processes;
- deleting files;
- importing/exporting wallet material;
- sending wallet seed/private key through Telegram.

Never send private keys, seed phrases, or full wallet secrets to Telegram. If a wallet must be generated, store it on the rig with restrictive permissions and report only the public address and file path.

## Connection workflow

1. Resolve farm and worker by ID/name.
2. Read worker card and verify it is online.
3. Start Hive Shell:

```json
{"command":"hssh","data":{"action":"start"}}
```

4. Poll messages every 5 seconds for up to 60 seconds with `with_payload=1`.
5. Extract shell link or SSH command.
6. Report: `Hive Shell ready`.
7. Connect using the available runtime:
   - if an SSH command is returned, run it directly;
   - if a web URL is returned and the runtime has a browser/terminal bridge, open it;
   - if direct interactive connection is unavailable, use HiveOS `exec` as fallback only for bounded commands and state that fallback was used.
8. For multi-step work, immediately create a durable session:

```bash
tmux new -d -s hermess-<project> 'bash -lc "cd /opt/<project> && ./hermess-run.sh"'
```

9. Store progress:

```text
/var/log/hermess/<project>.log
/run/hermess/<project>.pid
/etc/systemd/system/<project>.service
/opt/<project>/hermess-state.json
```

10. If the shell expires, request `hssh start` again and resume by checking `tmux`, PID, service, log, and state file.

## Long-running deployment pattern

For node deployments, do not rely on an interactive shell staying alive. Build an idempotent installer on the rig:

```bash
install -d -m 0755 /opt/<project> /var/log/hermess /run/hermess
cat >/opt/<project>/hermess-install.sh <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
exec > >(tee -a /var/log/hermess/<project>.log) 2>&1

echo "{\"phase\":\"start\",\"ts\":$(date +%s)}" >/opt/<project>/hermess-state.json

# install dependencies
# download release
# verify checksum if available
# generate wallet without printing private material
# write systemd unit
# start service
# poll sync status

echo "{\"phase\":\"done\",\"ts\":$(date +%s)}" >/opt/<project>/hermess-state.json
EOF
chmod 0700 /opt/<project>/hermess-install.sh
```

Run it in `tmux`:

```bash
tmux new -d -s hermess-<project> '/opt/<project>/hermess-install.sh'
```

Resume checks:

```bash
tmux has-session -t hermess-<project>
pgrep -af '<project>|hermess-install'
systemctl status <project> --no-pager
tail -n 120 /var/log/hermess/<project>.log
cat /opt/<project>/hermess-state.json
```

## GitHub release deployment workflow

When the user gives a GitHub release URL:

1. Parse owner, repo, tag/version, asset name if specified.
2. Prefer official release assets over source tarballs.
3. Fetch release metadata from GitHub if internet is available.
4. Choose asset for HiveOS rig architecture:

```bash
uname -m
ldd --version | head -n1
```

5. Download with retries to `/opt/<project>/downloads`.
6. Verify checksum/signature if the project publishes one.
7. Unpack under `/opt/<project>/current`.
8. Generate config and wallet.
9. Install systemd service.
10. Start service.
11. Report:
    - public address;
    - service name;
    - log path;
    - sync status;
    - next check command.

## Wallet generation rules

- Generate wallet on the rig, not in Telegram.
- Save private material as `0600`, owned by root or a dedicated service user.
- Report only public address unless the user explicitly requests export.
- If export is requested, require explicit confirmation and prefer a file path on the rig over Telegram text.

Example:

```bash
umask 077
mkdir -p /opt/<project>/wallet
<node-cli> wallet create --output /opt/<project>/wallet/wallet.json
<node-cli> wallet address > /opt/<project>/wallet/address.txt
```

Report:

```text
Wallet generated.
Public address: <address>
Private file: /opt/<project>/wallet/wallet.json
Permissions: 600
```

## Expired shell recovery

If commands stop responding or the link expires:

1. Start a new Hive Shell with `hssh start`.
2. Poll worker messages again.
3. Reconnect.
4. Check durable state:

```bash
tmux ls
cat /opt/<project>/hermess-state.json
tail -n 120 /var/log/hermess/<project>.log
systemctl status <project> --no-pager
pgrep -af '<project>'
```

5. Continue from the last completed phase. Do not rerun destructive steps blindly.

## Fallback through HiveOS exec

If the environment cannot attach to the Hive Shell link directly, use HiveOS `exec` only for bounded, non-interactive commands:

```http
POST /farms/{farmId}/workers/{workerId}/command
```

Payload:

```json
{"command":"exec","data":{"cmd":"tmux ls || true"}}
```

For longer commands, send a small bootstrap script that starts `tmux`/`systemd`, then poll messages/logs. Always tell the user when fallback mode is used.

## Deliverables

For a completed task, report:

- farm and worker;
- whether Hive Shell or fallback `exec` was used;
- project path;
- service/process name;
- public wallet address, if generated;
- log path;
- current sync/deploy status;
- commands used for future status checks.

For an in-progress long task, report:

- current phase;
- PID/tmux/session/service status;
- latest log lines;
- whether a new Hive Shell link was generated;
- next automatic check interval or manual command.

