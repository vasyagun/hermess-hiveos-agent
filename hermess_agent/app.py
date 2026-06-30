from __future__ import annotations

import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any

import requests


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_int(name: str, default: int) -> int:
    raw = env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def mask(value: str, keep: int = 6) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return value[:2] + "..."
    return f"{value[:keep]}...{value[-keep:]}"


JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
BOT_TOKEN_RE = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")


def extract_jwt(text: str) -> str:
    match = JWT_RE.search(text)
    return match.group(0) if match else ""


def redact_text(text: str) -> str:
    text = JWT_RE.sub("[REDACTED_JWT]", text)
    text = BOT_TOKEN_RE.sub("[REDACTED_TELEGRAM_TOKEN]", text)
    return text


def table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "Нет данных."
    widths = [len(h) for h in headers]
    text_rows = [[str(cell if cell is not None else "") for cell in row] for row in rows]
    for row in text_rows:
        for idx, cell in enumerate(row):
            widths[idx] = min(max(widths[idx], len(cell)), 42)
    lines = [" | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))]
    lines.append("-+-".join("-" * w for w in widths))
    for row in text_rows:
        clipped = [cell if len(cell) <= widths[i] else cell[: widths[i] - 1] + "…" for i, cell in enumerate(row)]
        lines.append(" | ".join(clipped[i].ljust(widths[i]) for i in range(len(headers))))
    return "\n".join(lines)


class Telegram:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.session = requests.Session()
        self.reply_chars = env_int("GONKA_TELEGRAM_REPLY_CHARS", 3500)

    def get_updates(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 45, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        response = self.session.get(f"{self.base}/getUpdates", params=payload, timeout=60)
        response.raise_for_status()
        return response.json().get("result", [])

    def send(self, chat_id: int, text: str) -> None:
        limit = min(max(self.reply_chars, 1000), 3900)
        chunks = [text[i : i + limit] for i in range(0, len(text), limit)] or [""]
        for chunk in chunks:
            response = self.session.post(
                f"{self.base}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
                timeout=30,
            )
            response.raise_for_status()


class Gonka:
    def __init__(self) -> None:
        self.base_url = env("GONKA_BASE_URL", "https://gate.joingonka.ai/v1").rstrip("/")
        self.model = env("GONKA_MODEL", "moonshotai/Kimi-K2.6")
        self.api_key = env("GONKA_API_KEY")
        self.max_input_chars = env_int("GONKA_MAX_INPUT_CHARS", 120000)
        self.max_output_tokens = env_int("GONKA_MAX_OUTPUT_TOKENS", 4096)
        self.context_reserve_tokens = env_int("GONKA_CONTEXT_RESERVE_TOKENS", 8192)
        self.temperature = env_float("GONKA_TEMPERATURE", 0.2)
        self.timeout = env_int("GONKA_TIMEOUT_SECONDS", 180)
        self.session = requests.Session()

    def ask(self, prompt: str) -> str:
        if not self.api_key:
            return "GONKA_API_KEY не задан."
        prompt = self.prepare_prompt(prompt)
        response = self.session.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "max_tokens": self.max_output_tokens,
                "temperature": self.temperature,
                "messages": [
                    {
                        "role": "system",
                        "content": self.system_prompt(),
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def prepare_prompt(self, prompt: str) -> str:
        prompt = prompt.strip()
        if len(prompt) <= self.max_input_chars:
            return prompt
        head = self.max_input_chars // 2
        tail = self.max_input_chars - head
        omitted = len(prompt) - self.max_input_chars
        return (
            prompt[:head]
            + f"\n\n[hermess: input compacted, omitted {omitted} characters from the middle. "
            + "Use retained beginning/end and ask for more specific chunks if needed.]\n\n"
            + prompt[-tail:]
        )

    def system_prompt(self) -> str:
        return (
            "Ты hermess, краткий Telegram-агент для HiveOS, майнинг-операций, Hive Shell и упаковки custom miners. "
            "Отвечай по-русски. Учитывай, что ответ идет в Telegram: сначала давай короткий результат, затем команды. "
            f"Лимит ответа модели: {self.max_output_tokens} tokens. "
            f"Резерв контекста под инструменты/логи: примерно {self.context_reserve_tokens} tokens. "
            "Не проси присылать огромные логи целиком: предлагай chunking, tail, grep и summary. "
            "Для длинных задач храни состояние во внешних файлах, tmux/systemd/logs, а не в контексте модели."
        )


class HiveOS:
    def __init__(self) -> None:
        self.base_url = env("HIVEOS_BASE_URL", "https://api2.hiveos.farm/api/v2").rstrip("/")
        self.token = env("HIVEOS_API_TOKEN")
        self.session = requests.Session()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.token:
            raise RuntimeError("HIVEOS_API_TOKEN не задан.")
        headers = kwargs.pop("headers", {})
        headers.update({"Authorization": f"Bearer {self.token}", "Accept": "application/json"})
        if method.upper() in {"POST", "PATCH", "PUT"}:
            headers.setdefault("Content-Type", "application/json")
        response = self.session.request(method, f"{self.base_url}{path}", headers=headers, timeout=45, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"HiveOS {response.status_code}: {response.text[:1000]}")
        if response.status_code == 204 or not response.text:
            return {}
        return response.json()

    def farms(self) -> list[dict[str, Any]]:
        return self._data(self.request("GET", "/farms"))

    def workers(self, farm_id: int) -> list[dict[str, Any]]:
        return self._data(self.request("GET", f"/farms/{farm_id}/workers"))

    def worker(self, farm_id: int, worker_id: int) -> dict[str, Any]:
        return self.request("GET", f"/farms/{farm_id}/workers/{worker_id}")

    def flight_sheets(self, farm_id: int) -> list[dict[str, Any]]:
        return self._data(self.request("GET", f"/farms/{farm_id}/fs"))

    def wallets(self, farm_id: int) -> list[dict[str, Any]]:
        return self._data(self.request("GET", f"/farms/{farm_id}/wallets"))

    def coins(self) -> list[dict[str, Any]]:
        return self._data(self.request("GET", "/hive/coins"))

    @staticmethod
    def _data(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return payload["data"]
        if isinstance(payload, list):
            return payload
        return []


@dataclass
class PendingAction:
    created_at: float
    chat_id: int
    farm_id: int
    worker_id: int
    method: str
    path: str
    payload: dict[str, Any]
    description: str
    rollback: str


class HermessBot:
    def __init__(self) -> None:
        token = env("TELEGRAM_BOT_TOKEN")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN не задан.")
        self.telegram = Telegram(token)
        self.hive = HiveOS()
        self.gonka = Gonka()
        self.allowed_chats = self._parse_ids(env("TELEGRAM_ALLOWED_CHAT_IDS"))
        self.allowed_users = self._parse_ids(env("TELEGRAM_ALLOWED_USER_IDS"))
        self.approval_ttl = int(env("HERMESS_APPROVAL_TTL_SECONDS", "300"))
        self.pending: dict[str, PendingAction] = {}
        self.audit_log = env("HERMESS_AUDIT_LOG", "/var/log/hermess/audit.log")
        self.memory_path = env("HERMESS_MEMORY_PATH", "/var/log/hermess/chat_memory.json")
        self.env_file = env("HERMESS_ENV_FILE", "/config/.env")
        self.max_memory_messages = env_int("HERMESS_MAX_MEMORY_MESSAGES", 40)
        self.chat_memory: dict[str, list[dict[str, str]]] = self.load_memory()
        os.makedirs(os.path.dirname(self.audit_log), exist_ok=True)

    @staticmethod
    def _parse_ids(raw: str) -> set[int]:
        return {int(part) for part in re.split(r"[,\s]+", raw) if part.strip().lstrip("-").isdigit()}

    def load_memory(self) -> dict[str, list[dict[str, str]]]:
        try:
            with open(self.memory_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict):
                return {str(k): v for k, v in payload.items() if isinstance(v, list)}
        except FileNotFoundError:
            return {}
        except Exception as exc:
            print(f"memory load error: {exc}", flush=True)
        return {}

    def save_memory(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
            with open(self.memory_path, "w", encoding="utf-8") as fh:
                json.dump(self.chat_memory, fh, ensure_ascii=False)
        except Exception as exc:
            print(f"memory save error: {exc}", flush=True)

    def remember(self, chat_id: int, role: str, text: str) -> None:
        key = str(chat_id)
        messages = self.chat_memory.setdefault(key, [])
        messages.append({"role": role, "text": redact_text(text), "ts": str(int(time.time()))})
        del messages[:-self.max_memory_messages]
        self.save_memory()

    def recent_context(self, chat_id: int, limit: int = 16) -> str:
        messages = self.chat_memory.get(str(chat_id), [])[-limit:]
        if not messages:
            return "Истории чата пока нет."
        return "\n".join(f"{item.get('role')}: {item.get('text')}" for item in messages)

    def run(self) -> None:
        offset: int | None = None
        print("hermess started", flush=True)
        while True:
            try:
                for update in self.telegram.get_updates(offset):
                    offset = update["update_id"] + 1
                    self.handle_update(update)
            except Exception as exc:
                print(f"loop error: {exc}", flush=True)
                time.sleep(5)

    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        chat_id = int(message.get("chat", {}).get("id", 0))
        user_id = int(message.get("from", {}).get("id", 0))
        if not text or not self.authorized(chat_id, user_id):
            if chat_id:
                self.telegram.send(chat_id, "Доступ запрещен.")
            return
        try:
            reply = self.dispatch(chat_id, text)
        except Exception as exc:
            reply = f"Ошибка: {exc}"
        self.telegram.send(chat_id, reply)
        self.remember(chat_id, "user", text)
        self.remember(chat_id, "assistant", reply)

    def authorized(self, chat_id: int, user_id: int) -> bool:
        chat_ok = not self.allowed_chats or chat_id in self.allowed_chats
        user_ok = not self.allowed_users or user_id in self.allowed_users
        return chat_ok and user_ok

    def dispatch(self, chat_id: int, text: str) -> str:
        lowered = text.lower()
        command = lowered.split(maxsplit=1)[0].split("@", 1)[0]
        if command in {"/start", "/help"} or lowered in {"help", "помощь", "команды"}:
            return self.help()
        if any(phrase in lowered for phrase in ["привет", "здарова", "здравствуй", "ты работаешь", "работаешь", "ping"]):
            return self.greeting()
        if any(phrase in lowered for phrase in ["что ты умеешь", "что умеешь", "что можешь"]):
            return self.help()
        if any(phrase in lowered for phrase in ["о чем мы говорили", "что мы обсуждали", "напомни контекст", "что было выше"]):
            return self.summarize_memory(chat_id)
        if lowered.startswith("confirm "):
            return self.confirm(chat_id, text.split(maxsplit=1)[1].strip())
        if lowered.startswith("/ask ") or lowered.startswith("спроси "):
            prompt = text.split(maxsplit=1)[1]
            return self.gonka.ask(self.with_context(chat_id, prompt))
        token = extract_jwt(text)
        token_context = (lowered + "\n" + self.recent_context(chat_id).lower())
        if token and any(marker in token_context for marker in ["hive", "хайв", "hiveos_api_token", "401", "токен", "ключ"]):
            return self.update_hive_token(token)
        if "hiveos_api_token" in lowered or "hive os токен" in lowered or "ключ для доступа" in lowered or "ключ для хайв" in lowered:
            if token:
                return self.update_hive_token(token)
        if "риг" in lowered and any(marker in lowered for marker in ["онлайн", "online", "запущ", "работает", "полетный", "полётный", "flight"]):
            return self.show_workers_all_farms(online_only=True)
        if lowered.startswith("/farms") or "покажи фермы" in lowered:
            return self.show_farms()
        if lowered.startswith("/rigs") or "покажи риги" in lowered:
            farm_value = self.arg(text, "farm")
            if not farm_value:
                return self.show_workers_all_farms(online_only="онлайн" in lowered)
            farm = self.resolve_farm(farm_value)
            return self.show_workers(farm)
        if lowered.startswith("/rig "):
            farm = self.resolve_farm(self.arg(text, "farm"))
            worker = self.resolve_worker(farm["id"], self.arg(text, "worker"))
            return self.show_worker(farm, worker)
        if lowered.startswith("/flight_sheets") or "покажи полетные" in lowered or "покажи полётные" in lowered or "flight sheets" in lowered:
            farm = self.resolve_farm(self.arg(text, "farm"))
            return self.show_flight_sheets(farm)
        if lowered.startswith("/wallets") or "кошель" in lowered:
            farm = self.resolve_farm(self.arg(text, "farm"))
            return self.show_wallets(farm)
        if lowered.startswith("/coins") or "монет" in lowered:
            return self.show_coins()
        if lowered.startswith("/miner_restart"):
            farm = self.resolve_farm(self.arg(text, "farm"))
            worker = self.resolve_worker(farm["id"], self.arg(text, "worker"))
            payload = {"command": "miner", "data": {"action": "restart", "miner_index": 0}}
            return self.plan(chat_id, farm, worker, "Перезапуск майнера", "POST", f"/farms/{farm['id']}/workers/{worker['id']}/command", payload, "Повторно выполнить miner start/restart или применить прежний flight sheet.")
        if lowered.startswith("/hssh") or lowered.startswith("/hive_shell"):
            farm = self.resolve_farm(self.arg(text, "farm"))
            worker = self.resolve_worker(farm["id"], self.arg(text, "worker"))
            return self.start_hssh(farm, worker)
        if lowered.startswith("/apply_fs"):
            farm = self.resolve_farm(self.arg(text, "farm"))
            worker = self.resolve_worker(farm["id"], self.arg(text, "worker"))
            fs = self.resolve_fs(farm["id"], self.arg(text, "fs"))
            payload = {"fs_id": fs["id"]}
            current = worker.get("fs_id") or worker.get("flight_sheet_id")
            return self.plan(chat_id, farm, worker, f"Применить flight sheet {fs.get('name')} ({fs.get('id')})", "PATCH", f"/farms/{farm['id']}/workers/{worker['id']}", payload, f"Вернуть fs_id={current}")
        if lowered.startswith("/set_oc"):
            farm = self.resolve_farm(self.arg(text, "farm"))
            worker = self.resolve_worker(farm["id"], self.arg(text, "worker"))
            oc_id = int(self.arg(text, "oc"))
            payload = {"oc_id": oc_id, "oc_apply_mode": "replace"}
            return self.plan(chat_id, farm, worker, f"Применить OC profile {oc_id}", "PATCH", f"/farms/{farm['id']}/workers/{worker['id']}", payload, "Вернуть предыдущий OC profile/config из карточки worker.")
        if lowered.startswith("/exec"):
            farm = self.resolve_farm(self.arg(text, "farm"))
            worker = self.resolve_worker(farm["id"], self.arg(text, "worker"))
            cmd = self.arg(text, "cmd")
            if self.dangerous_shell(cmd):
                return "Команда выглядит разрушительной. Я не буду планировать ее без ручной переработки."
            payload = {"command": "exec", "data": {"cmd": cmd}}
            return self.plan(chat_id, farm, worker, f"Shell exec: {cmd}", "POST", f"/farms/{farm['id']}/workers/{worker['id']}/command", payload, "Нет автоматического отката для shell exec.")
        return self.handle_natural_text(chat_id, text)

    def help(self) -> str:
        return "\n".join(
            [
                "hermess online. Я управляю HiveOS через Telegram и могу помогать с ригами, Hive Shell и custom miners.",
                "",
                "Быстрые команды:",
                "/farms",
                "/rigs farm:<id|name>",
                "/rig farm:<id|name> worker:<id|name>",
                "/flight_sheets farm:<id|name>",
                "/wallets farm:<id|name>",
                "/coins",
                "/apply_fs farm:<id|name> worker:<id|name> fs:<id|name>",
                "/miner_restart farm:<id|name> worker:<id|name>",
                "/hssh farm:<id|name> worker:<id|name>",
                "/set_oc farm:<id|name> worker:<id|name> oc:<id>",
                "/exec farm:<id|name> worker:<id|name> cmd:\"nvidia-smi\"",
                "/ask <вопрос к Gonka model>",
                "",
                "Можно писать обычным текстом. Для опасных действий я сначала покажу план и попрошу CONFIRM.",
            ]
        )

    def greeting(self) -> str:
        return "\n".join(
            [
                "На связи.",
                "Можешь писать обычным текстом: `покажи фермы`, `что с rig1`, `подключись к rig1`, `перезапусти майнер на rig1`, `поставь flight sheet X на rig2`.",
                "Опасные действия я не выполню молча: сначала покажу план и попрошу CONFIRM.",
            ]
        )

    def handle_natural_text(self, chat_id: int, text: str) -> str:
        try:
            intent = self.interpret_intent(chat_id, text)
            return self.execute_intent(chat_id, text, intent)
        except Exception as exc:
            return self.free_chat(chat_id, text)

    def interpret_intent(self, chat_id: int, text: str) -> dict[str, Any]:
        prompt = "\n".join(
            [
                "Ты intent parser для Telegram-агента hermess.",
                "Верни строго один JSON object без markdown и без пояснений.",
                "Пользователь пишет по-русски обычным текстом. Определи намерение и параметры.",
                "Учитывай историю чата: пользователь может писать 'что это значит', 'вот опять', 'замени его' после предыдущей ошибки.",
                "Допустимые intent:",
                "help, chat, farms_list, workers_list, worker_info, flight_sheets_list, wallets_list, coins_list,",
                "hssh, miner_restart, apply_fs, set_oc, exec, package_miner, node_deploy, update_hive_token.",
                "Поля JSON:",
                '{"intent":"...","farm":"id-or-name-or-empty","worker":"id-or-name-or-empty","fs":"id-or-name-or-empty","oc":"id-or-empty","cmd":"shell-command-or-empty","repo":"url-or-empty","token":"jwt-or-empty","reply":"short-reply-for-chat-or-empty"}',
                "Правила:",
                "- если пользователь хочет список ферм: farms_list;",
                "- если хочет риги/воркеры, спрашивает кто онлайн, что сейчас запущено или какой полетный лист: workers_list;",
                "- если спрашивает про конкретный rig/риг/worker: worker_info;",
                "- если хочет подключиться к ригу/серверу/терминалу/shell: hssh;",
                "- если хочет развернуть ноду/поставить node по GitHub: node_deploy;",
                "- если хочет перезапустить майнер: miner_restart;",
                "- если хочет применить полетный лист/flight sheet: apply_fs;",
                "- если хочет кошельки: wallets_list;",
                "- если хочет монеты: coins_list;",
                "- если пользователь прислал новый HIVEOS_API_TOKEN/JWT и просит заменить ключ HiveOS: update_hive_token;",
                "- если пользователь спрашивает 'что это значит' после ошибки 401: chat с объяснением, что HiveOS токен не авторизован;",
                "- если это разговор без действия: chat и короткий reply.",
                "История чата:",
                self.recent_context(chat_id),
                f"Сообщение: {text}",
            ]
        )
        raw = self.gonka.ask(prompt)
        return self.parse_json_object(raw)

    def execute_intent(self, chat_id: int, original_text: str, intent: dict[str, Any]) -> str:
        name = str(intent.get("intent") or "chat").strip()
        farm_value = str(intent.get("farm") or "").strip()
        worker_value = str(intent.get("worker") or "").strip()

        if name == "help":
            return self.help()
        if name == "farms_list":
            return self.show_farms()
        if name == "coins_list":
            return self.show_coins()
        if name in {"workers_list", "flight_sheets_list", "wallets_list"}:
            if name == "workers_list" and not farm_value:
                original_lower = original_text.lower()
                online_only = any(marker in original_lower for marker in ["онлайн", "online", "запущено", "работает", "активен"])
                return self.show_workers_all_farms(online_only=online_only)
            farm = self.resolve_farm(farm_value)
            if name == "workers_list":
                return self.show_workers(farm)
            if name == "flight_sheets_list":
                return self.show_flight_sheets(farm)
            return self.show_wallets(farm)
        if name == "worker_info":
            if not farm_value:
                original_lower = original_text.lower()
                online_only = any(marker in original_lower for marker in ["онлайн", "online", "запущено", "запущ", "работает", "полетный", "полётный", "flight"])
                return self.show_workers_all_farms(online_only=online_only)
            farm = self.resolve_farm(farm_value)
            worker = self.resolve_worker(int(farm["id"]), worker_value)
            return self.show_worker(farm, worker)
        if name == "hssh":
            farm = self.resolve_farm(farm_value)
            worker = self.resolve_worker(int(farm["id"]), worker_value)
            return self.start_hssh(farm, worker)
        if name == "miner_restart":
            farm = self.resolve_farm(farm_value)
            worker = self.resolve_worker(int(farm["id"]), worker_value)
            payload = {"command": "miner", "data": {"action": "restart", "miner_index": 0}}
            return self.plan(chat_id, farm, worker, "Перезапуск майнера", "POST", f"/farms/{farm['id']}/workers/{worker['id']}/command", payload, "Повторно выполнить miner start/restart или применить прежний flight sheet.")
        if name == "apply_fs":
            farm = self.resolve_farm(farm_value)
            worker = self.resolve_worker(int(farm["id"]), worker_value)
            fs_value = str(intent.get("fs") or "").strip()
            if not fs_value:
                return "Понял, надо применить flight sheet. Напиши название или id flight sheet и к какому ригу применить."
            fs = self.resolve_fs(int(farm["id"]), fs_value)
            payload = {"fs_id": fs["id"]}
            current = worker.get("fs_id") or worker.get("flight_sheet_id")
            return self.plan(chat_id, farm, worker, f"Применить flight sheet {fs.get('name')} ({fs.get('id')})", "PATCH", f"/farms/{farm['id']}/workers/{worker['id']}", payload, f"Вернуть fs_id={current}")
        if name == "set_oc":
            farm = self.resolve_farm(farm_value)
            worker = self.resolve_worker(int(farm["id"]), worker_value)
            oc_value = str(intent.get("oc") or "").strip()
            if not oc_value.isdigit():
                return "Понял, надо применить OC. Укажи id OC профиля."
            payload = {"oc_id": int(oc_value), "oc_apply_mode": "replace"}
            return self.plan(chat_id, farm, worker, f"Применить OC profile {oc_value}", "PATCH", f"/farms/{farm['id']}/workers/{worker['id']}", payload, "Вернуть предыдущий OC profile/config из карточки worker.")
        if name == "exec":
            farm = self.resolve_farm(farm_value)
            worker = self.resolve_worker(int(farm["id"]), worker_value)
            cmd = str(intent.get("cmd") or "").strip()
            if not cmd:
                return "Понял, надо выполнить команду на риге. Напиши саму shell-команду."
            if self.dangerous_shell(cmd):
                return "Команда выглядит разрушительной. Я не буду планировать ее без ручной переработки."
            payload = {"command": "exec", "data": {"cmd": cmd}}
            return self.plan(chat_id, farm, worker, f"Shell exec: {cmd}", "POST", f"/farms/{farm['id']}/workers/{worker['id']}/command", payload, "Нет автоматического отката для shell exec.")
        if name == "node_deploy":
            farm_hint = f" farm:{farm_value}" if farm_value else ""
            worker_hint = f" worker:{worker_value}" if worker_value else ""
            repo = str(intent.get("repo") or "").strip()
            repo_hint = f" repo:{repo}" if repo else " repo:<github-url>"
            return "Понял задачу развернуть ноду. Для этого я сначала подниму Hive Shell и буду вести long-running установку через tmux/systemd. Подтверди параметры или дополни командой:\n" + f"/node_deploy{farm_hint}{worker_hint}{repo_hint}"
        if name == "package_miner":
            return "Понял задачу по упаковке майнера для HiveOS. Пришли архив/путь к бинарнику, стартовый скрипт или логи, и имя custom miner."
        if name == "update_hive_token":
            token = str(intent.get("token") or "").strip() or extract_jwt(original_text)
            if not token:
                return "Понял, надо заменить HIVEOS_API_TOKEN. Пришли сам JWT токен одним сообщением."
            return self.update_hive_token(token)

        reply = str(intent.get("reply") or "").strip()
        if reply:
            return reply
        return self.free_chat(chat_id, original_text)

    def with_context(self, chat_id: int, prompt: str) -> str:
        return "\n".join(
            [
                "История текущего Telegram-чата:",
                self.recent_context(chat_id),
                "",
                "Текущее сообщение:",
                prompt,
            ]
        )

    def summarize_memory(self, chat_id: int) -> str:
        context = self.recent_context(chat_id, limit=24)
        prompt = "\n".join(
            [
                "Кратко напомни пользователю по-русски, о чем шла текущая переписка.",
                "Не раскрывай токены и секреты. Если в истории есть [REDACTED_JWT], называй это 'HiveOS token'.",
                "Сделай акцент на нерешенных проблемах и следующем действии.",
                "",
                context,
            ]
        )
        try:
            return self.gonka.ask(prompt)
        except Exception:
            return "Мы обсуждали управление HiveOS через hermess, ошибку 401 от HiveOS API, замену HIVEOS_API_TOKEN и то, что боту нужна память контекста между сообщениями."

    def update_hive_token(self, token: str) -> str:
        old_token = self.hive.token
        self.hive.token = token
        persisted = self.write_env_value("HIVEOS_API_TOKEN", token)
        try:
            farms = self.hive.farms()
            validation = f"Проверка HiveOS прошла: доступно ферм: {len(farms)}."
        except Exception as exc:
            validation = f"Токен записан, но проверка HiveOS пока не прошла: {exc}"
            if not persisted:
                self.hive.token = old_token
        status = "записан в .env и применен в runtime" if persisted else "применен только в runtime, .env недоступен для записи"
        return f"Принял новый HIVEOS_API_TOKEN ({mask(token)}), {status}. {validation}"

    def write_env_value(self, key: str, value: str) -> bool:
        if not self.env_file:
            return False
        try:
            lines: list[str] = []
            if os.path.exists(self.env_file):
                with open(self.env_file, "r", encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
            replaced = False
            next_lines: list[str] = []
            for line in lines:
                if line.startswith(f"{key}="):
                    next_lines.append(f"{key}={value}")
                    replaced = True
                else:
                    next_lines.append(line)
            if not replaced:
                next_lines.append(f"{key}={value}")
            with open(self.env_file, "w", encoding="utf-8") as fh:
                fh.write("\n".join(next_lines).rstrip() + "\n")
            return True
        except Exception as exc:
            print(f"env update error: {exc}", flush=True)
            return False

    @staticmethod
    def parse_json_object(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("No JSON object in model response")
        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("Intent response is not an object")
        return parsed

    def free_chat(self, chat_id: int, text: str) -> str:
        prompt = "\n".join(
            [
                "Пользователь написал hermess в Telegram свободным текстом.",
                "Ответь как живой оператор майнинг-инфраструктуры, по-русски, коротко и полезно.",
                "Если пользователь просит действие с HiveOS, предложи точную команду из списка ниже или скажи какие параметры нужны.",
                "Если это small talk, ответь нормально и по-человечески.",
                "Доступные команды:",
                self.help(),
                "",
                "История чата:",
                self.recent_context(chat_id),
                f"Сообщение пользователя: {text}",
            ]
        )
        try:
            return self.gonka.ask(prompt)
        except Exception as exc:
            return "Я на связи. Могу показать фермы, риги, кошельки, flight sheets, запустить Hive Shell или помочь с custom miner. Напиши /help или конкретную задачу."

    def show_farms(self) -> str:
        farms = self.hive.farms()
        rows = [[f.get("id"), f.get("name"), f.get("workers_count", ""), f.get("timezone", "")] for f in farms]
        return table(["id", "name", "workers", "timezone"], rows)

    def show_workers(self, farm: dict[str, Any]) -> str:
        workers = self.hive.workers(int(farm["id"]))
        rows = []
        for worker in workers:
            rows.append(self.worker_row(farm, self.enrich_worker_for_status(farm, worker)))
        return f"Farm: {farm.get('name')} ({farm.get('id')})\n" + table(["farm", "id", "name", "online", "miner", "hashrate", "flight sheet"], rows)

    def show_workers_all_farms(self, online_only: bool = False) -> str:
        farms = self.hive.farms()
        rows: list[list[Any]] = []
        total = 0
        for farm in farms:
            workers = self.hive.workers(int(farm["id"]))
            for worker in workers:
                total += 1
                if online_only and not self.worker_is_online(worker):
                    continue
                rows.append(self.worker_row(farm, self.enrich_worker_for_status(farm, worker)))
        if not rows:
            if online_only:
                return f"Онлайн-ригов не нашел. Проверено ригов: {total}, ферм: {len(farms)}."
            return "Ригов не нашел."
        title = "Онлайн-риги по всем фермам" if online_only else "Риги по всем фермам"
        return f"{title}: {len(rows)} из {total}\n" + table(["farm", "id", "name", "online", "miner", "hashrate", "flight sheet"], rows)

    def worker_row(self, farm: dict[str, Any], worker: dict[str, Any]) -> list[Any]:
        return [
            farm.get("name"),
            worker.get("id"),
            worker.get("name"),
            "yes" if self.worker_is_online(worker) else "no",
            self.worker_miner(worker),
            self.worker_hashrate(worker),
            self.worker_flight_sheet(worker),
        ]

    def enrich_worker_for_status(self, farm: dict[str, Any], worker: dict[str, Any]) -> dict[str, Any]:
        if not self.worker_is_online(worker):
            return worker
        if any(worker.get(key) for key in ("flight_sheet", "fs", "flight_sheet_name", "fs_name", "flight_sheet_id", "fs_id")):
            return worker
        try:
            full = self.hive.worker(int(farm["id"]), int(worker["id"]))
            if isinstance(full, dict):
                merged = dict(worker)
                merged.update(full)
                return merged
        except Exception:
            return worker
        return worker

    @staticmethod
    def worker_is_online(worker: dict[str, Any]) -> bool:
        stats = worker.get("stats") or {}
        return bool(stats.get("online") or worker.get("online"))

    @staticmethod
    def worker_miner(worker: dict[str, Any]) -> str:
        summary = worker.get("miners_summary") or {}
        hashrates = summary.get("hashrates") or []
        if hashrates:
            first = hashrates[0]
            miner = first.get("miner") or "miner"
            coin = first.get("coin") or ""
            algo = first.get("algo") or ""
            parts = [miner]
            if coin:
                parts.append(coin)
            if algo:
                parts.append(algo)
            return "/".join(str(part) for part in parts)
        stats = worker.get("stats") or {}
        return str(stats.get("miner") or "")

    @staticmethod
    def worker_hashrate(worker: dict[str, Any]) -> str:
        summary = worker.get("miners_summary") or {}
        hashrates = summary.get("hashrates") or []
        if hashrates:
            value = hashrates[0].get("hash")
            if isinstance(value, (int, float)):
                if value >= 1_000_000_000:
                    return f"{value / 1_000_000_000:.2f} GH/s"
                if value >= 1_000_000:
                    return f"{value / 1_000_000:.2f} MH/s"
                if value >= 1_000:
                    return f"{value / 1_000:.2f} KH/s"
                return f"{value} H/s"
        stats = worker.get("stats") or {}
        return str(stats.get("hs") or "")

    @staticmethod
    def worker_flight_sheet(worker: dict[str, Any]) -> str:
        for key in ("flight_sheet", "fs"):
            value = worker.get(key)
            if isinstance(value, dict):
                return str(value.get("name") or value.get("id") or "")
            if isinstance(value, str):
                return value
        for key in ("flight_sheet_name", "fs_name", "flight_sheet_id", "fs_id"):
            if worker.get(key):
                return str(worker.get(key))
        return "unknown"

    def show_worker(self, farm: dict[str, Any], worker: dict[str, Any]) -> str:
        full = self.hive.worker(int(farm["id"]), int(worker["id"]))
        return json.dumps(self.redact(full), ensure_ascii=False, indent=2)[:3500]

    def show_flight_sheets(self, farm: dict[str, Any]) -> str:
        sheets = self.hive.flight_sheets(int(farm["id"]))
        rows = [[fs.get("id"), fs.get("name"), fs.get("workers_count", ""), len(fs.get("items") or [])] for fs in sheets]
        return f"Farm: {farm.get('name')} ({farm.get('id')})\n" + table(["id", "name", "workers", "items"], rows)

    def show_wallets(self, farm: dict[str, Any]) -> str:
        wallets = self.hive.wallets(int(farm["id"]))
        rows = [[w.get("id"), w.get("name"), w.get("coin"), mask(str(w.get("wal") or "")), w.get("workers_count", "")] for w in wallets]
        return f"Farm: {farm.get('name')} ({farm.get('id')})\n" + table(["id", "name", "coin", "wallet", "workers"], rows)

    def show_coins(self) -> str:
        coins = self.hive.coins()[:120]
        rows = [[c.get("coin") or c.get("symbol") or c.get("name"), c.get("name", ""), c.get("algo", "")] for c in coins]
        return table(["symbol", "name", "algo"], rows)

    def start_hssh(self, farm: dict[str, Any], worker: dict[str, Any]) -> str:
        started_at = int(time.time()) - 5
        path = f"/farms/{farm['id']}/workers/{worker['id']}/command"
        payload = {"command": "hssh", "data": {"action": "start"}}
        result = self.hive.request("POST", path, json=payload)
        link = self.wait_hssh_link(int(farm["id"]), int(worker["id"]), started_at)
        if link:
            return "\n".join(
                [
                    f"Hive Shell готов для {worker.get('name')} ({worker.get('id')}).",
                    link,
                    "Ссылка временная. Для долгих задач запускай процесс в tmux/systemd и проверяй статус отдельно.",
                ]
            )
        return "\n".join(
            [
                "Команда hssh отправлена, но ссылка еще не найдена в worker messages.",
                f"Result: {json.dumps(self.redact(result), ensure_ascii=False)[:1200]}",
                "Повтори /hssh через несколько секунд или проверь сообщения рига.",
            ]
        )

    def wait_hssh_link(self, farm_id: int, worker_id: int, started_at: int) -> str:
        deadline = time.time() + 60
        while time.time() < deadline:
            payload = self.hive.request(
                "GET",
                f"/farms/{farm_id}/workers/{worker_id}/messages",
                params={"with_payload": 1, "start_time": started_at, "per_page": 25},
            )
            link = self.extract_hssh_link(payload)
            if link:
                return link
            time.sleep(5)
        return ""

    @staticmethod
    def extract_hssh_link(payload: Any) -> str:
        text = json.dumps(payload, ensure_ascii=False)
        patterns = [
            r"ssh\s+[^\s\"']+",
            r"https?://[^\s\"']*(?:hive|shell|hssh)[^\s\"']*",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(0).replace("\\/", "/")
        return ""

    def plan(self, chat_id: int, farm: dict[str, Any], worker: dict[str, Any], desc: str, method: str, path: str, payload: dict[str, Any], rollback: str) -> str:
        code = secrets.token_hex(3).upper()
        self.pending[code] = PendingAction(time.time(), chat_id, int(farm["id"]), int(worker["id"]), method, path, payload, desc, rollback)
        return "\n".join(
            [
                f"Plan {code}",
                f"Farm: {farm.get('name')} ({farm.get('id')})",
                f"Worker: {worker.get('name')} ({worker.get('id')})",
                f"Action: {desc}",
                f"API: {method} {path}",
                f"Payload: {json.dumps(self.redact(payload), ensure_ascii=False)}",
                f"Rollback: {rollback}",
                f"Confirm: CONFIRM {code}",
            ]
        )

    def confirm(self, chat_id: int, code: str) -> str:
        code = code.strip().upper()
        action = self.pending.get(code)
        if not action or action.chat_id != chat_id:
            return "Нет такого ожидающего подтверждения."
        if time.time() - action.created_at > self.approval_ttl:
            self.pending.pop(code, None)
            return "Подтверждение истекло."
        result = self.hive.request(action.method, action.path, json=action.payload)
        self.pending.pop(code, None)
        self.audit(action)
        return f"Done: {action.description}\nResult: {json.dumps(self.redact(result), ensure_ascii=False)[:1500]}"

    def audit(self, action: PendingAction) -> None:
        record = {
            "ts": int(time.time()),
            "farm_id": action.farm_id,
            "worker_id": action.worker_id,
            "method": action.method,
            "path": action.path,
            "payload": self.redact(action.payload),
            "description": action.description,
        }
        with open(self.audit_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def resolve_farm(self, value: str) -> dict[str, Any]:
        farms = self.hive.farms()
        return self.resolve(farms, value, "farm")

    def resolve_worker(self, farm_id: int, value: str) -> dict[str, Any]:
        return self.resolve(self.hive.workers(farm_id), value, "worker")

    def resolve_fs(self, farm_id: int, value: str) -> dict[str, Any]:
        return self.resolve(self.hive.flight_sheets(farm_id), value, "flight sheet")

    @staticmethod
    def resolve(items: list[dict[str, Any]], value: str, entity: str) -> dict[str, Any]:
        if not value and len(items) == 1:
            return items[0]
        if not value:
            raise RuntimeError(f"Укажи {entity}.")
        lowered = value.lower()
        exact = [item for item in items if str(item.get("id")) == value or str(item.get("name", "")).lower() == lowered]
        if len(exact) == 1:
            return exact[0]
        fuzzy = [item for item in items if lowered in str(item.get("name", "")).lower()]
        if len(fuzzy) == 1:
            return fuzzy[0]
        if not exact and not fuzzy:
            raise RuntimeError(f"{entity} не найден: {value}")
        raise RuntimeError(f"Найдено несколько {entity}: " + ", ".join(f"{i.get('name')}({i.get('id')})" for i in exact + fuzzy))

    @staticmethod
    def arg(text: str, name: str) -> str:
        match = re.search(rf"{re.escape(name)}:(\"[^\"]+\"|'[^']+'|\S+)", text, flags=re.IGNORECASE)
        if not match:
            return ""
        value = match.group(1).strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        return value

    @staticmethod
    def dangerous_shell(cmd: str) -> bool:
        lowered = cmd.lower()
        patterns = ["rm -rf", "mkfs", " dd ", "curl ", "| sh", "| bash", ":(){", "apt remove", "apt purge"]
        return any(pattern in f" {lowered} " for pattern in patterns)

    @staticmethod
    def redact(value: Any) -> Any:
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                if any(secret_key in key.lower() for secret_key in ["token", "key", "password", "secret", "authorization"]):
                    redacted[key] = "***"
                elif key.lower() in {"wal", "wallet", "address"} and isinstance(item, str):
                    redacted[key] = mask(item)
                else:
                    redacted[key] = HermessBot.redact(item)
            return redacted
        if isinstance(value, list):
            return [HermessBot.redact(item) for item in value]
        return value


if __name__ == "__main__":
    HermessBot().run()
