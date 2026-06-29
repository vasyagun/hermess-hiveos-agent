# Hermess: Telegram agent for HiveOS rig control

Цель проекта: поднять агента `hermess` в Docker-контейнере на VPS. Агент общается с ядром через Gonka OpenAI-compatible API, принимает команды только через Telegram-бота и управляет майнинг-ригами через HiveOS API.

Важно: исходный черновик содержал живые токены и пароль VPS. В документации они заменены на имена переменных окружения. Секреты нужно хранить в `.env` на сервере, Docker secrets или другом secret-хранилище. После публикации/передачи репозитория токены стоит перевыпустить.

## Entity: `hermess`

`hermess` - операционный агент для управления майнинг-инфраструктурой владельца.

Основная роль:

- принимать задачи владельца через Telegram;
- читать состояние HiveOS: фермы, риги, flight sheets, кошельки, монеты, статистику, события;
- выполнять безопасные команды после явного подтверждения владельца;
- готовить HiveOS custom miner архивы из Linux-скриптов, батников, неизвестных miner binary и логов;
- объяснять каждое изменение перед применением: что будет изменено, на каком farm/worker, каким API-вызовом и как откатить.

Ограничения:

- не выполнять destructive-команды без подтверждения: reboot, shutdown, upgrade, flash ROM, массовый overclock, изменение flight sheet, shell `exec`;
- не писать секреты в логи Telegram, stdout контейнера и документы;
- не использовать `eval` при обработке пользовательских miner config;
- при неуверенности сначала читать HiveOS API/состояние, затем предлагать dry-run.

## Runtime architecture

```text
Telegram user
  -> Telegram Bot API
  -> hermess container on VPS
  -> Gonka API: https://gate.joingonka.ai/v1
  -> HiveOS API: https://api2.hiveos.farm/api/v2
```

Компоненты контейнера:

- `telegram_adapter` - long polling или webhook, allowlist Telegram user/chat id;
- `agent_core` - OpenAI-compatible client к Gonka;
- `hiveos_client` - HTTP-клиент HiveOS API v2;
- `command_router` - переводит пользовательские фразы в намерения и API-вызовы;
- `approval_guard` - требует подтверждение для опасных операций;
- `skill_runner` - использует `new_miner_skill/SKILL.md` для сборки HiveOS custom miner пакетов;
- `audit_log` - пишет локальный журнал операций без токенов.

## Gonka model context policy

`hermess` настроен так, чтобы не раздувать контекст модели без необходимости:

- HiveOS read/write команды выполняются напрямую через HiveOS API и не тратят контекст Gonka;
- Gonka используется для `/ask` и будущих reasoning-задач;
- история Telegram-чата не отправляется в модель автоматически;
- входной prompt режется по `GONKA_MAX_INPUT_CHARS`;
- ответ модели ограничивается `GONKA_MAX_OUTPUT_TOKENS`;
- `GONKA_CONTEXT_RESERVE_TOKENS` зарезервирован под логи, tool output и рабочий план;
- длинные логи, README, GitHub release notes и install guides должны идти через chunking/summarization, а не целиком одним запросом;
- состояние долгих задач хранится вне модели: `tmux`, `systemd`, PID, logs, `hermess-state.json`.

Рекомендуемые значения для `moonshotai/Kimi-K2.6`:

```text
GONKA_MAX_INPUT_CHARS=120000
GONKA_MAX_OUTPUT_TOKENS=4096
GONKA_CONTEXT_RESERVE_TOKENS=8192
GONKA_TEMPERATURE=0.2
GONKA_TELEGRAM_REPLY_CHARS=3500
```

## Required environment

См. [hermess_agent/.env.example](hermess_agent/.env.example).

Минимальный набор:

```text
GONKA_BASE_URL=https://gate.joingonka.ai/v1
GONKA_MODEL=moonshotai/Kimi-K2.6
GONKA_API_KEY=...
GONKA_MAX_INPUT_CHARS=120000
GONKA_MAX_OUTPUT_TOKENS=4096
GONKA_CONTEXT_RESERVE_TOKENS=8192
GONKA_TEMPERATURE=0.2
GONKA_TIMEOUT_SECONDS=180
GONKA_TELEGRAM_REPLY_CHARS=3500
HIVEOS_BASE_URL=https://api2.hiveos.farm/api/v2
HIVEOS_API_TOKEN=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_IDS=...
TELEGRAM_ALLOWED_USER_IDS=...
```

## HiveOS API reference

Спецификация: https://app.swaggerhub.com/apis/HiveOS/public/2.1-beta

Проверенная база из Swagger:

- scheme: `https`
- host: `api2.hiveos.farm`
- base path: `/api/v2`
- auth header: `Authorization: Bearer <HIVEOS_API_TOKEN>`

Ключевые endpoints:

- `GET /farms` - список доступных ферм;
- `GET /farms/{farmId}` - карточка фермы;
- `GET /farms/{farmId}/workers` - список ригов/воркеров;
- `GET /farms/{farmId}/workers/{workerId}` - карточка конкретного рига;
- `PATCH /farms/{farmId}/workers/{workerId}` - изменить параметры рига, включая `name`, `fs_id`, `oc_id`, `oc_config`;
- `POST /farms/{farmId}/workers/{workerId}/command` - команда одному ригу;
- `POST /farms/{farmId}/workers/command` - команда нескольким ригам;
- `POST /farms/{farmId}/workers/overclock` - расширенное применение overclock;
- `POST /farms/{farmId}/workers/reload` - перезагрузка данных нескольких воркеров;
- `GET /farms/{farmId}/fs` - flight sheets фермы;
- `GET /farms/{farmId}/fs/{fsId}` - конкретный flight sheet;
- `GET /farms/{farmId}/wallets` - кошельки фермы;
- `GET /farms/{farmId}/wallets/{walletId}` - конкретный кошелек;
- `GET /hive/coins` - список доступных монет;
- `GET /pools/by_coin/{coin}` - пулы по монете.

Команды HiveOS worker command:

```json
{"command":"miner","data":{"action":"start|stop|restart|log|config|tuning","miner_index":0}}
{"command":"reboot"}
{"command":"shutdown","data":{"wakealarm":false}}
{"command":"upgrade","data":{"force":false,"reboot":true,"version":"..."}}
{"command":"exec","data":{"cmd":"..."}}
{"command":"pool_test","data":{"pool_urls":["stratum+tcp://host:port"],"pool_ssl":false}}
```

## Telegram command UX

Все команды должны иметь две формы: человеко-понятную и slash-команду.

Примеры:

```text
/farms
Покажи фермы

/rigs farm:<id|name>
Покажи риги на ферме main

/rig farm:<id|name> worker:<id|name>
Покажи карточку рига rig-3090-01

/flight_sheets farm:<id|name>
Покажи полетные листы

/wallets farm:<id|name>
Покажи сохраненные кошельки

/coins
Покажи список монет

/apply_fs farm:<id|name> worker:<id|name> fs:<id|name>
Поставь flight sheet modelos на rig-5090-02

/miner_restart farm:<id|name> worker:<id|name>
Перезапусти майнер на rig-3090-01

/set_oc farm:<id|name> worker:<id|name> oc:<id>
Примени OC профиль 12 на rig-3090-01

/exec farm:<id|name> worker:<id|name> cmd:"tail -n 100 /var/log/hive-agent.log"
```

## Approval policy

Read-only без подтверждения:

- список ферм, ригов, flight sheets, кошельков, монет, пулов;
- карточка рига;
- статистика и events;
- чтение miner log через безопасный HiveOS `miner log`, если команда не меняет состояние.

Требуют подтверждения `CONFIRM <short-id>`:

- `PATCH /workers/{workerId}`;
- применение flight sheet;
- miner start/stop/restart;
- reboot/shutdown/upgrade;
- overclock;
- массовые команды;
- `exec`;
- прошивка ROM.

Перед подтверждением агент обязан показать:

```text
Farm: <name> (<id>)
Worker: <name> (<id>)
Action: <human readable action>
API: <method> <path>
Payload: <redacted json>
Rollback: <how to revert>
Confirm: CONFIRM <short-id>
```

## HiveOS scenarios

Подробные сценарии см. [hermess_agent/hiveos_scenarios.md](hermess_agent/hiveos_scenarios.md).

Короткая карта:

- имена ферм: `GET /farms`, вывести `id`, `name`, статус/баланс если есть;
- имена ригов: `GET /farms/{farmId}/workers`, вывести `id`, `name`, `platform`, `active`, miner summary;
- полетные листы: `GET /farms/{farmId}/fs`, вывести `id`, `name`, `items`, `workers_count`;
- сохраненные кошельки: `GET /farms/{farmId}/wallets`, вывести `id`, `name`, `coin`, маскированный `wal`;
- монеты: `GET /hive/coins`, группировать по symbol/name;
- пулы монеты: `GET /pools/by_coin/{coin}`;
- сменить flight sheet на риге: `PATCH /farms/{farmId}/workers/{workerId}` с `{"fs_id": <id>}`;
- сменить OC профиль: `PATCH /farms/{farmId}/workers/{workerId}` с `{"oc_id": <id>, "oc_apply_mode": "replace"}`;
- изменить имя рига: `PATCH /farms/{farmId}/workers/{workerId}` с `{"name": "new-name"}`;
- перезапустить майнер: `POST /farms/{farmId}/workers/{workerId}/command` с `{"command":"miner","data":{"action":"restart","miner_index":0}}`.

## Custom miner skill

Скилл для заворачивания Linux-скриптов/батников неизвестных майнеров в HiveOS custom miner package находится в [new_miner_skill/SKILL.md](new_miner_skill/SKILL.md).

Главный результат скилла:

- архив `<custom-miner-name>.tar.gz`;
- `h-manifest.conf`, `h-config.sh`, `h-run.sh`, `h-stats.sh`;
- корректная структура `/hive/miners/custom/<custom-miner-name>`;
- flight sheet настройки;
- чеклист проверки на HiveOS.

## Hive Shell operator skill

Скилл для подключения к HiveOS ригам без белого IP через временную Hive Shell / `hssh` ссылку находится в [hive_shell_skill/SKILL.md](hive_shell_skill/SKILL.md).

Основной сценарий:

- агент по HiveOS API отправляет `{"command":"hssh","data":{"action":"start"}}`;
- ждет worker message с временной ссылкой или SSH-командой;
- подключается к ригу через доступный shell-канал;
- долгие задачи запускает через `tmux` или `systemd`;
- если ссылка истекла, генерирует новую и продолжает проверку по PID, service, tmux session, логам и state-файлу.
