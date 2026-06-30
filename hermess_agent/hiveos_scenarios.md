# HiveOS scenarios for `hermess`

Base URL: `https://api2.hiveos.farm/api/v2`

Auth:

```http
Authorization: Bearer <HIVEOS_API_TOKEN>
Accept: application/json
Content-Type: application/json
```

## 0. Natural language interpretation layer

The Telegram user is not required to send slash commands. The agent must process each free-form message through this pipeline:

1. Understand the task in plain Russian.
2. Extract entities:
   - `farm`: farm id/name, or empty when unknown;
   - `worker`: rig/worker id/name, "this rig", "single online rig";
   - `coin`: coin symbol/name such as `PEARL`;
   - `flight_sheet`: flight sheet id/name;
   - `wallet`: wallet id/name/coin;
   - `action`: read-only, shell, restart, apply flight sheet, balance, package miner, deploy node.
3. Map entities to HiveOS objects by reading live HiveOS state.
4. Decide whether the task is read-only or state-changing.
5. For read-only tasks, execute immediately and answer with the result.
6. For state-changing tasks, show a dry-run plan and wait for `CONFIRM <id>`.
7. If something is ambiguous, answer what was understood and ask for the missing entity. Do not fall back to a generic help message.

Core abstractions:

| User object | HiveOS object | Discovery API |
| --- | --- | --- |
| farm / ферма | farm | `GET /farms` |
| rig / риг / worker / сервер | worker | `GET /farms/{farmId}/workers` |
| current online rig / единственный онлайн риг | online worker across all farms | `GET /farms`, then `GET /farms/{farmId}/workers` |
| flight sheet / полетный лист | fs | `GET /farms/{farmId}/fs` |
| coin / монета | coin symbol in fs/items/coins | `GET /hive/coins`, `GET /farms/{farmId}/fs` |
| wallet / кошелек | wallet | `GET /farms/{farmId}/wallets` |
| Hive Shell / hssh | worker command | `POST /farms/{farmId}/workers/{workerId}/command` |
| balance / деньги / остаток | account billing fields | `GET /account` |

High-confidence local intents must be handled before calling the model:

- `Какие полетные листы есть для монеты PEARL?` -> list flight sheets filtered by coin `PEARL`.
- `Какой риг онлайн и что там запущено?` -> scan all farms and show online workers with miner and flight sheet.
- `Сгенерируй hive shell ссылку для моего единственного рига который сейчас онлайн` -> find the single online worker and start `hssh`.
- `Сколько денег осталось на балансе Hive аккаунта?` -> read account balance.

The model layer is still used for less obvious requests. Its job is not to execute code directly; it returns a structured intent with extracted entities. The execution layer then verifies entities against HiveOS and performs the safe API workflow.

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

Exception: for read-only natural language questions like "какой риг онлайн", "что сейчас запущено", or "какой полетный лист", do not ask for farm. Scan all farms with:

```http
GET /farms
GET /farms/{farmId}/workers
```

Return online workers across all farms with farm name, worker name/id, miner, coin/algo, hashrate, and flight sheet if available.

If exactly one worker is online, remember it as the current rig context for follow-up phrases like "этот риг", "мой единственный риг", or "онлайн риг".

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

Important: if the user asks "полетные листы для монеты PEARL", do not call `/hive/coins` as the main answer. The correct object is `flight sheet`, filtered by `coin=PEARL` across the available farms.

## 6.1. Show HiveOS account balance

Telegram:

```text
Сколько денег у меня осталось на балансе hive аккаунта?
Покажи баланс HiveOS
```

API:

```http
GET /account
```

Output:

```text
field | value
balance | ...
deposit | ...
credit | ...
```

The exact HiveOS response can vary. Extract fields whose names indicate billing or money: `balance`, `deposit`, `credit`, `debt`, `paid`, `unpaid`, `money`, `usd`, `billing`. If the response does not expose an obvious balance field, show a short redacted account summary and say that no explicit balance field was found.

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
