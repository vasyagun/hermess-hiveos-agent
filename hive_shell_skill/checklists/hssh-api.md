# HiveOS hssh API Checklist

## Start session

```http
POST /farms/{farmId}/workers/{workerId}/command
```

```json
{"command":"hssh","data":{"action":"start"}}
```

## Poll result

```http
GET /farms/{farmId}/workers/{workerId}/messages?with_payload=1&start_time=<unix_ts>&per_page=25
```

Look for:

- `command: hssh`
- `cmd_id` matching the start command response, if present
- `payload`
- `command_result`
- `ssh ...`
- `https://...shell...`
- `https://...hive...`

## Restart session

```json
{"command":"hssh","data":{"action":"restart"}}
```

## Stop session

```json
{"command":"hssh","data":{"action":"stop"}}
```

## Fallback command

```json
{"command":"exec","data":{"cmd":"tmux ls || true"}}
```

