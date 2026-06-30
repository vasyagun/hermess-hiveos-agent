# Deploy Hermess

There is no external Hermess Docker image to pull. Build it from this repository.

## Local build

```bash
cp hermess_agent/.env.example .env
# edit .env and fill GONKA_API_KEY, HIVEOS_API_TOKEN, TELEGRAM_BOT_TOKEN
docker compose build
docker compose up -d
```

## VPS layout

```text
/opt/hermess
  .env
  docker-compose.yml
  Dockerfile
  hermess_agent/
  hive_shell_skill/
  new_miner_skill/
  docs.md
```

## Required .env values

```text
GONKA_BASE_URL=https://gate.joingonka.ai/v1
GONKA_MODEL=moonshotai/Kimi-K2.6
GONKA_API_KEY=...

HIVEOS_BASE_URL=https://api2.hiveos.farm/api/v2
HIVEOS_API_TOKEN=...

TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_IDS=...
TELEGRAM_ALLOWED_USER_IDS=...
```

## Server commands

```bash
cd /opt/hermess
docker compose up -d --build
docker compose logs -f hermess
```

## Verify

```bash
docker exec hermess python -c "from hermess_agent.app import HiveOS; h=HiveOS(); print(len(h.farms()))"
```

Telegram smoke test:

```text
привет
покажи фермы
какой риг онлайн и что там запущено
```
