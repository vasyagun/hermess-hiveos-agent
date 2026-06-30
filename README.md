# Hermess HiveOS Agent

Hermess is a Telegram-controlled operations agent for HiveOS rigs.

It can:

- answer in Telegram using natural Russian text;
- inspect HiveOS farms, rigs, wallets, coins, flight sheets, and miner status;
- request confirmation before dangerous actions;
- start Hive Shell / `hssh` for rigs without public IP;
- help package unknown Linux miners as HiveOS custom miners;
- use Gonka's OpenAI-compatible API for reasoning and intent parsing.

There is no separate public "Hermess image" to download. The Docker image is built locally from this repository's `Dockerfile`.

## Architecture

```text
Telegram user
  -> Telegram Bot API
  -> hermess Docker container
  -> Gonka API: https://gate.joingonka.ai/v1
  -> HiveOS API: https://api2.hiveos.farm/api/v2
```

## Requirements

On the server or local machine:

- Docker
- Docker Compose v2
- Git

On Windows, Docker Desktop is enough. On Ubuntu VPS:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git
sudo systemctl enable --now docker
```

## Tokens You Need

### 1. Telegram bot token

Create a bot through Telegram `@BotFather`:

```text
/newbot
```

Copy the token into:

```text
TELEGRAM_BOT_TOKEN=...
```

To restrict access, get your Telegram user/chat id and set:

```text
TELEGRAM_ALLOWED_CHAT_IDS=123456789
TELEGRAM_ALLOWED_USER_IDS=123456789
```

For first launch you can leave allowlists empty, but that means anyone who knows the bot token can talk to it.

### 2. Gonka API key

Create/copy a Gonka API key from your Gonka account and set:

```text
GONKA_BASE_URL=https://gate.joingonka.ai/v1
GONKA_MODEL=moonshotai/Kimi-K2.6
GONKA_API_KEY=...
```

Hermess uses Gonka for natural language understanding and `/ask`.

### 3. HiveOS API token

Create/copy a HiveOS API token from HiveOS account settings / API tokens and set:

```text
HIVEOS_BASE_URL=https://api2.hiveos.farm/api/v2
HIVEOS_API_TOKEN=...
```

If the token is invalid, HiveOS returns `401 Unauthorized`.

## Quick Start

Clone the repository:

```bash
git clone https://github.com/vasyagun/hermess-hiveos-agent.git
cd hermess-hiveos-agent
```

Create `.env`:

```bash
cp hermess_agent/.env.example .env
nano .env
```

Fill at least:

```text
GONKA_API_KEY=...
HIVEOS_API_TOKEN=...
TELEGRAM_BOT_TOKEN=...
```

Build and run:

```bash
docker compose up -d --build
```

View logs:

```bash
docker compose logs -f hermess
```

Expected log:

```text
hermess started
```

## Verify Setup

Check container:

```bash
docker ps --filter name=hermess
```

Check HiveOS token from inside the container:

```bash
docker exec hermess python -c "from hermess_agent.app import HiveOS; h=HiveOS(); print(len(h.farms()))"
```

Check Telegram:

```text
привет
покажи фермы
какой риг онлайн и что там запущено
```

## Natural Language Examples

Hermess should understand normal messages, not only slash commands:

```text
Какой риг у меня онлайн?
Что там сейчас запущено, какой полетный лист?
Покажи кошельки
Покажи полетные листы
Подключись к rig1
Перезапусти майнер на rig1
Поставь flight sheet modelos на rig2
Разверни ноду на rig1, github ссылка: ...
```

Dangerous actions are not executed immediately. Hermess sends a plan and waits for:

```text
CONFIRM <code>
```

## Slash Commands

Slash commands are still available:

```text
/farms
/rigs farm:<id|name>
/rig farm:<id|name> worker:<id|name>
/flight_sheets farm:<id|name>
/wallets farm:<id|name>
/coins
/hssh farm:<id|name> worker:<id|name>
/miner_restart farm:<id|name> worker:<id|name>
/apply_fs farm:<id|name> worker:<id|name> fs:<id|name>
/set_oc farm:<id|name> worker:<id|name> oc:<id>
/exec farm:<id|name> worker:<id|name> cmd:"nvidia-smi"
/ask <question>
```

## Runtime Files

The default Docker Compose setup mounts:

```text
.env -> /config/.env
hermess_logs volume -> /var/log/hermess
```

This allows Hermess to:

- persist chat memory in `/var/log/hermess/chat_memory.json`;
- update `HIVEOS_API_TOKEN` in `/config/.env` when the owner sends a replacement token through Telegram.

Secrets are not committed to Git. Keep `.env` private.

## Updating HiveOS Token

If HiveOS returns `401 Unauthorized`, send the new HiveOS JWT token to the bot with a clear instruction:

```text
Замени HIVEOS_API_TOKEN:
<token>
```

Hermess applies it in runtime, writes it to `/config/.env`, and checks HiveOS access.

Manual server update:

```bash
cd /opt/hermess
nano .env
docker compose restart hermess
```

## VPS Deploy

Recommended path:

```bash
sudo mkdir -p /opt/hermess
sudo chown "$USER":"$USER" /opt/hermess
cd /opt/hermess
git clone https://github.com/vasyagun/hermess-hiveos-agent.git .
cp hermess_agent/.env.example .env
nano .env
docker compose up -d --build
docker compose logs -f hermess
```

Update existing deployment:

```bash
cd /opt/hermess
git pull
docker compose up -d --build
```

## Project Structure

```text
hermess_agent/app.py              Main Telegram bot and HiveOS/Gonka clients
hermess_agent/.env.example        Environment template
hermess_agent/hiveos_scenarios.md HiveOS operation scenarios
hive_shell_skill/SKILL.md         Hive Shell / hssh workflow
new_miner_skill/SKILL.md          HiveOS custom miner packaging skill
Dockerfile                        Builds the hermess image
docker-compose.yml                Runs the hermess container
docs.md                           Project-level design notes
```

## Troubleshooting

### Bot says `HiveOS 401 Unauthorized`

`HIVEOS_API_TOKEN` is invalid, expired, or not authorized. Replace it in `.env` or through Telegram.

### Bot does not answer

Check logs:

```bash
docker compose logs --tail=100 hermess
```

Check the Telegram token and allowlists.

### Bot asks for farm when it should not

Read-only questions like "which rig is online" should scan all farms. Pull the latest code and rebuild:

```bash
git pull
docker compose up -d --build
```

### Where is the Docker image?

It is built locally:

```bash
docker compose build
```

The image name is generated by Compose, usually similar to:

```text
hermess-hermess:latest
```

