# generate_tastks.py
import asyncio
import json
import re
import random
import warnings
import uuid
import time
import httpx
import requests
import re 
from typing import Optional

from openai import AsyncOpenAI
from loguru import logger

from config import (
    GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE, GIGACHAT_MODEL, DB_PATH,
)
from database import init_db, add_riddle

warnings.filterwarnings("ignore")

# ============================================================
# ⚡ НАСТРОЙКИ
# ============================================================
TARGET_TOTAL        = 2000
RIDDLES_PER_REQUEST = 2      
CONCURRENCY         = 1      
MAX_TOKENS          = 3000
SLEEP_BETWEEN       = 5      
MAX_ATTEMPTS        = 100
MAX_RETRIES_429     = 5      

TOPICS = [
    "Загадки на игру слов и омонимы", "Сложные метаграммы", "Логогрифы",
    "Шарады", "Скрытые слова и акростихи", "Фразеологизмы в буквальном смысле",
    "Текстовые ребусы", "Загадки на знание алфавита", "Палиндромы",
    "Сложные анаграммы", "Парадокс лжеца", "Парадокс неожиданной казни",
    "Дилемма заключенного", "Загадки на шляпы (текстовые)", "Парадокс близнецов",
    "Кот Шредингера (философский)", "Отель Гильберта (метафора)", 
    "Оптические иллюзии в тексте", "Детективные истории на логику",
    "Бытовые ловушки и нестандартное мышление", "Загадки на перспективу",
    "Загадки-обманки для взрослых", "Сложные загадки на внимание"
]
# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def _to_str(value, joiner=", ") -> str:
    if value is None: return ""
    if isinstance(value, str): return value.strip()
    if isinstance(value, (int, float, bool)): return str(value)
    if isinstance(value, (list, tuple)):
        return joiner.join(p for p in (_to_str(v, joiner) for v in value) if p)
    return str(value).strip()

def _to_int(value, default=5) -> int:
    if isinstance(value, int): return max(1, min(5, value))
    if isinstance(value, str) and value.isdigit(): return max(1, min(5, int(value)))
    return default

def build_prompt(topic: str, count: int, avoid: list[str]) -> str:
    avoid_block = ""
    if avoid:
        preview = "\n".join(f"- {t[:60]}" for t in avoid[-15:])
        avoid_block = f"\nНЕ ПОВТОРЯЙ:\n{preview}\n"
    
    return f"""Ты — составитель сложных текстовых загадок для интеллектуального клуба. 
ТЕМА: «{topic}»

КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:
- Генерировать математические задачи, уравнения, задачи на вычисления или вероятность.
- Генерировать задачи с сетками, клетками, геометрическими фигурами или взвешиванием.
- Давать длинные ответы (ответ строго 1-3 слова).

ТВОЯ ЗАДАЧА: Сгенерируй РОВНО {count} СЛОЖНЫХ ЗАГАДОК (уровень 4-5 из 5).
Используй игру слов, парадоксы, скрытый смысл, каламбуры и нестандартное мышление. Текст должен быть атмосферным и завуалированным.

ПРИМЕР:
{{
  "text": "Он может быть острым, но не режет. Он может быть длинным, но не измеряется линейкой. Если его потерять, становится только хуже. Что это?",
  "answer": "Ум",
  "hint": "Связано с головой.",
  "alt_answers": "разум",
  "difficulty": 5
}}

Верни ТОЛЬКО валидный JSON-объект вида {{"riddles": [...]}}. Без markdown, без вступлений.
{avoid_block}"""

def _strip_md(raw: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())

def _salvage(raw: str) -> Optional[dict]:
    m = re.search(r'"riddles"\s*:\s*\[', raw)
    if not m: return None
    pos = m.end(); riddles = []
    while pos < len(raw):
        while pos < len(raw) and raw[pos] in " \t\n\r,": pos += 1
        if pos >= len(raw) or raw[pos] == "]": break
        if raw[pos] != "{": break
        depth, in_str, esc, start = 0, False, False, pos
        while pos < len(raw):
            c = raw[pos]
            if in_str:
                if esc: esc = False
                elif c == "\\": esc = True
                elif c == '"': in_str = False
            else:
                if c == '"': in_str = True
                elif c == "{": depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try: riddles.append(json.loads(raw[start:pos + 1]))
                        except: pass
                        pos += 1; break
            pos += 1
        else: break
    return {"riddles": riddles} if riddles else None

def extract_json(raw: str) -> Optional[dict]:
    if not raw: return None
    raw = _strip_md(raw)
    try: return json.loads(raw)
    except: pass
    s, e = raw.find("{"), raw.rfind("}")
    if s != -1 and e > s:
        try: return json.loads(raw[s:e+1])
        except: pass
    return _salvage(raw)

# ============================================================
# АВТО-ОБНОВЛЕНИЕ ТОКЕНА (Класс для httpx)
# ============================================================
class GigaChatAuth(httpx.Auth):
    def __init__(self, credentials, scope):
        self.credentials = credentials
        self.scope = scope
        self.token = None
        self.expires_at = 0

    def _fetch_token(self):
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        payload = f"scope={self.scope}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Bearer {self.credentials}",
        }
        resp = requests.post(url, data=payload, headers=headers, verify=False)
        resp.raise_for_status()
        data = resp.json()
        self.token = data["access_token"]
        self.expires_at = data["expires_at"] / 1000.0
        logger.info("🔑 Токен GigaChat успешно обновлен.")

    async def async_auth_flow(self, request):
        # Если токена нет или он истекает через 2 минуты
        if not self.token or time.time() > (self.expires_at - 120):
            self._fetch_token()
        
        request.headers["Authorization"] = f"Bearer {self.token}"
        response = yield request

        # Если внезапно получили 401 (токен протух), обновляем и пробуем еще раз
        if response.status_code == 401:
            logger.warning("⚠️ Токен истек (401). Принудительно обновляем...")
            self._fetch_token()
            request.headers["Authorization"] = f"Bearer {self.token}"
            yield request

# ============================================================
# ГЕНЕРАЦИЯ
# ============================================================
async def generate_batch(client: AsyncOpenAI, topic: str, collected_texts: list[str]) -> int:
    prompt = build_prompt(topic, RIDDLES_PER_REQUEST, collected_texts)
    
    for attempt in range(MAX_RETRIES_429):
        try:
            response = await client.chat.completions.create(
                model=GIGACHAT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5, # Держим низкую температуру для логики
                max_tokens=MAX_TOKENS,
            )
            raw = response.choices[0].message.content
            if not raw: return 0
            break
        except Exception as e:
            if "429" in str(e):
                await asyncio.sleep(SLEEP_BETWEEN * (2 ** attempt))
                if attempt == MAX_RETRIES_429 - 1: return 0
            else:
                return 0
    else:
        return 0

    data = extract_json(raw)
    if not data or "riddles" not in data:
        return 0

    added = 0
    for riddle in data["riddles"]:
        if not isinstance(riddle, dict): continue
        text = _to_str(riddle.get("text"))
        answer = _to_str(riddle.get("answer"))
        if not text or not answer: continue

        # ⚠️ ФИЛЬТР 1: Длина ответа не больше 3 слов
        if len(answer.split()) > 3:
            continue

        # ⚠️ ФИЛЬТР 2: Запрещаем цифры в тексте (выдает математику)
        if re.search(r'\d', text):
            logger.info(f"[{topic}] ❌ Отклонено (содержит цифры/математику)")
            continue

        # ⚠️ ФИЛЬТР 3: Запрещаем типичные математические слова
        bad_words = ["сетк", "клетк", "уравнен", "вероятност", "процент", 
                     "километр", "килограмм", "градус", "треугольник", 
                     "прямоугольник", "линейк", "весы", "взвес"]
        if any(w in text.lower() for w in bad_words):
            logger.info(f"[{topic}] ❌ Отклонено (математический термин)")
            continue

        ok = await add_riddle(
            text=text, answer=answer, category=topic,
            difficulty=_to_int(riddle.get("difficulty", 5)),
            source="GigaChat",
            alt_answers=_to_str(riddle.get("alt_answers")),
            solution="",
            hint=_to_str(riddle.get("hint")),
        )
        if ok:
            collected_texts.append(text)
            added += 1

    if added > 0:
        logger.info(f"[{topic}] ✅ +{added} (из {len(data['riddles'])})")
    return added

# ============================================================
# ЗАПУСК
# ============================================================
async def worker(client: AsyncOpenAI, queue: asyncio.Queue, collected_texts: list[str], sem: asyncio.Semaphore):
    while True:
        try:
            topic = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        
        async with sem:
            await generate_batch(client, topic, collected_texts)
            await asyncio.sleep(SLEEP_BETWEEN)
            queue.task_done()

async def main():
    logger.info(f"DB={DB_PATH} | Model={GIGACHAT_MODEL} | Генерация ЗАГАДОК")
    await init_db()
    
    # Создаем клиент с авто-обновлением токена
    auth = GigaChatAuth(GIGACHAT_CREDENTIALS, GIGACHAT_SCOPE)
    http_client = httpx.AsyncClient(verify=False, auth=auth)
    
    client = AsyncOpenAI(
        api_key="dummy_key", # Ключ не используется, так как авторизация идет через http_client
        base_url="https://api.giga.chat/v1",
        http_client=http_client
    )

    collected = []
    queue = asyncio.Queue()
    for _ in range(MAX_ATTEMPTS):
        random.shuffle(TOPICS)
        for t in TOPICS:
            queue.put_nowait(t)

    sem = asyncio.Semaphore(CONCURRENCY)
    workers = [
        asyncio.create_task(worker(client, queue, collected, sem))
        for _ in range(CONCURRENCY)
    ]

    try:
        while not queue.empty():
            await asyncio.sleep(2)
    finally:
        for w in workers: w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        await http_client.aclose()
        logger.success("Готово! Загадки сгенерированы.")

if __name__ == "__main__":
    asyncio.run(main())