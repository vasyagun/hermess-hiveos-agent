# HiveOS scenarios for `hermess`

Base URL: `https://api2.hiveos.farm/api/v2`

Auth:

```http
Authorization: Bearer <HIVEOS_API_TOKEN>
Accept: application/json
Content-Type: application/json
```

## 1. Show farm names

Telegram:

```text
/farms
Покажи фермы
```

API:

```http
GET /farms
```

Agent output:

```text
id | name | workers | status
123 | main-farm | 8 | ok
```

Rules:

- cache `farmId -> name` for the current dialog;
- if user later says farm name, resolve by exact match first, then fuzzy match.

## 2. Show rigs/workers in a farm

Telegram:

```text
/rigs farm:main-farm
Покажи риги на main-farm
```

API:

```http
GET /farms/{farmId}/workers
```

Output fields:

```text
id | name | active | platform | miner | hashrate | temp
```

If farm is omitted and only one farm exists, use it. If several farms exist, ask for farm.

## 3. Show one rig card

Telegram:

```text
/rig farm:main-farm worker:rig-3090-01
```

API:

```http
GET /farms/{farmId}/workers/{workerId}
```

Output:

- worker id/name;
- active/online state;
- current flight sheet id/name if present;
- miner state and hashrate;
- GPU list, temperatures, fans, power if present;
- OC profile/config summary if present.

## 4. Show flight sheets

Telegram:

```text
/flight_sheets farm:main-farm
Покажи полетные листы
```

API:

```http
GET /farms/{farmId}/fs
GET /farms/{farmId}/fs/{fsId}
```

Output:

```text
id | name | workers_count | miners/pools summary
```

For details, show flight sheet `items`, miner name, pool, wallet template, and custom miner fields if present. Redact wallet values where possible.

## 5. Show saved wallets

Telegram:

```text
/wallets farm:main-farm
Покажи кошельки
```

API:

```http
GET /farms/{farmId}/wallets
GET /farms/{farmId}/wallets/{walletId}
```

Output:

```text
id | name | coin | wallet | used_by
```

Mask wallet:

```text
0x1234...abcd
```

Never show private keys or full secrets.

## 6. Show available coins and pools

Telegram:

```text
/coins
/pools coin:KAS
```

API:

```http
GET /hive/coins
GET /pools/by_coin/{coin}
```

Output:

```text
symbol | name | algo
KAS | Kaspa | kHeavyHash
```

For pools, show pool name, URLs, SSL support if returned by API.

## 7. Apply a flight sheet to a rig

Telegram:

```text
/apply_fs farm:main-farm worker:rig-5090-02 fs:modelos
Поставь modelos на rig-5090-02
```

Discovery:

```http
GET /farms
GET /farms/{farmId}/workers
GET /farms/{farmId}/fs
GET /farms/{farmId}/workers/{workerId}
```

Plan:

```http
PATCH /farms/{farmId}/workers/{workerId}
```

Payload:

```json
{"fs_id":12345}
```

Approval required:

```text
CONFIRM <short-id>
```

Rollback:

```json
{"fs_id":<previous_fs_id>}
```

After apply:

```http
GET /farms/{farmId}/workers/{workerId}
POST /farms/{farmId}/workers/{workerId}/command
{"command":"miner","data":{"action":"restart","miner_index":0}}
```

Miner restart is a separate dangerous action unless the user included it in the confirmed plan.

## 8. Restart miner on a rig

Telegram:

```text
/miner_restart farm:main-farm worker:rig-3090-01
```

API:

```http
POST /farms/{farmId}/workers/{workerId}/command
```

Payload:

```json
{"command":"miner","data":{"action":"restart","miner_index":0}}
```

Approval required.

After command, poll worker state and recent messages/events if available.

## 9. Read miner log

Telegram:

```text
/miner_log farm:main-farm worker:rig-3090-01 lines:100
```

Preferred safe command:

```http
POST /farms/{farmId}/workers/{workerId}/command
```

Payload:

```json
{"command":"miner","data":{"action":"log","miner_index":0}}
```

If the API returns an async command id/message, fetch messages:

```http
GET /farms/{farmId}/workers/{workerId}/messages
```

Do not use shell `exec` for logs unless the owner confirms it.

## 10. Change worker name

Telegram:

```text
/rename_worker farm:main-farm worker:old-name name:new-name
```

API:

```http
PATCH /farms/{farmId}/workers/{workerId}
```

Payload:

```json
{"name":"new-name"}
```

Approval required.

Rollback:

```json
{"name":"old-name"}
```

## 11. Apply OC profile

Telegram:

```text
/set_oc farm:main-farm worker:rig-3090-01 oc:12
```

API:

```http
PATCH /farms/{farmId}/workers/{workerId}
```

Payload:

```json
{"oc_id":12,"oc_apply_mode":"replace"}
```

Approval required.

Rollback:

```json
{"oc_id":<previous_oc_id>,"oc_apply_mode":"replace"}
```

For direct OC config, use `oc_config` only after displaying the exact GPU brand fields to the owner.

## 12. Change a specific rig parameter

Pattern:

1. Read current worker:

```http
GET /farms/{farmId}/workers/{workerId}
```

2. Build minimal patch payload with only the changed fields.
3. Show dry-run.
4. Wait for `CONFIRM <short-id>`.
5. Apply:

```http
PATCH /farms/{farmId}/workers/{workerId}
```

6. Read worker again and show diff.

Example:

```json
{"description":"RTX 5090 modelos test rig"}
```

Never send a full worker object back as patch unless HiveOS explicitly requires it. Minimal patch reduces accidental overwrites.

## 13. Run shell command through HiveOS

Telegram:

```text
/exec farm:main-farm worker:rig-3090-01 cmd:"nvidia-smi"
```

API:

```http
POST /farms/{farmId}/workers/{workerId}/command
```

Payload:

```json
{"command":"exec","data":{"cmd":"nvidia-smi"}}
```

Approval required every time.

Additional guardrails:

- reject destructive shell by default: `rm -rf`, `mkfs`, `dd`, `:(){`, package removal, arbitrary curl-pipe-shell;
- prefer specific HiveOS commands over shell `exec`;
- show command exactly as it will run.

## 14. Package a new/unknown Linux miner for HiveOS

Telegram:

```text
/package_miner name:modelos-miner source:<archive-or-path> logs:<optional>
```

Use:

```text
new_miner_skill/SKILL.md
```

Inputs:

- miner binary or release archive;
- Linux start script, batch-like script, README, sample logs;
- target custom miner name;
- pool URL, wallet template, coin/algo;
- required custom config keys.

Output:

- `.tar.gz` HiveOS custom miner archive;
- SHA256;
- flight sheet fields;
- validation commands;
- known limitations.

