"""
Парсер deti-online.com/zagadki/
Обходит все категории, подкатегории и страницы пагинации.
Собирает максимум загадок, какие есть на сайте.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from database import init_db, add_riddle

BASE_URL = "https://deti-online.com"
START_URL = f"{BASE_URL}/zagadki/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Не ходим глубже, чем на 4 уровня от /zagadki/
MAX_DEPTH = 4
# Пауза между запросами (сек)
DELAY = 1.2

# Сюда запишем все URL, куда нельзя заходить (например, /bitrix/, /ajax/)
SKIP_PATTERNS = (
    "/bitrix/", "/ajax/", "/upload/", "/include/",
    "/search/", "/personal/", "/auth/", "/login/",
    ".jpg", ".png", ".gif", ".svg", ".css", ".js", ".pdf",
    "?", "#",
)


# ---------- Утилиты ----------

_robots_cache: dict[str, RobotFileParser] = {}


async def can_fetch(url: str) -> bool:
    """Проверка robots.txt (с кешем)."""
    parsed = urlparse(url)
    host_root = f"{parsed.scheme}://{parsed.netloc}"
    if host_root in _robots_cache:
        rp = _robots_cache[host_root]
    else:
        rp = RobotFileParser()
        rp.set_url(f"{host_root}/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        _robots_cache[host_root] = rp
    if rp is None:
        return True
    return rp.can_fetch("*", url)


def is_relevant(url: str) -> bool:
    """Отсекаем мусорные ссылки."""
    if not url.startswith(BASE_URL):
        return False
    if not url.startswith(f"{BASE_URL}/zagadki"):
        return False
    for p in SKIP_PATTERNS:
        if p in url:
            return False
    return True


async def fetch(session: aiohttp.ClientSession, url: str) -> str | None:
    """Загрузка HTML с обработкой ошибок."""
    try:
        async with session.get(url, headers=HEADERS, timeout=25) as resp:
            if resp.status != 200:
                return None
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype and "xml" not in ctype:
                return None
            return await resp.text()
    except Exception as e:
        print(f"    ! {url}: {type(e).__name__}")
        return None


# ---------- Парсинг загадок на странице ----------

def extract_riddles(html: str, page_url: str) -> list[tuple[str, str, str]]:
    """
    Возвращает список (текст, ответ, категория).
    Пробует несколько разных вёрсток сайта.
    """
    soup = BeautifulSoup(html, "html.parser")
    found: list[tuple[str, str, str]] = []

    # Категория — берём из заголовка страницы <h1>
    h1 = soup.find("h1")
    category = h1.get_text(strip=True) if h1 else "Без категории"

    # --- Вариант 1: <div class="card"> с <p> и <button data-a="..."> ---
    for card in soup.select(".card, .zagadka, .riddle, li.item, article"):
        p = card.find("p")
        btn = card.find("button", class_="answer") or card.find("button", attrs={"data-a": True})
        if p and btn and btn.get("data-a"):
            text = p.get_text(" ", strip=True)
            answer = btn["data-a"].strip()
            if len(text) >= 10 and answer:
                found.append((text, answer, category))

    # --- Вариант 2: загадки просто в <p> с ответом в скобках ---
    if not found:
        for p in soup.find_all("p"):
            text = p.get_text(" ", strip=True)
            if len(text) < 15 or "(" not in text or ")" not in text:
                continue
            # Обрезаем по последней скобке
            open_i = text.rfind("(")
            close_i = text.rfind(")")
            if open_i == -1 or close_i == -1 or close_i < open_i:
                continue
            answer = text[open_i + 1:close_i].strip()
            riddle = text[:open_i].strip()
            # Фильтр — ответ короткий (1-4 слова), загадка длинная
            if 1 <= len(answer.split()) <= 5 and len(riddle) >= 15:
                found.append((riddle, answer, category))

    # --- Вариант 3: <li> в общем списке, ответ спрятан в data-атрибуте любого элемента ---
    if not found:
        for el in soup.select("[data-a]"):
            answer = (el.get("data-a") or "").strip()
            if not answer:
                continue
            parent_text = el.parent.get_text(" ", strip=True) if el.parent else ""
            # Убираем из текста часть, совпадающую с ответом
            riddle = parent_text.replace(answer, "").strip(" .-—:;")
            if len(riddle) >= 15:
                found.append((riddle, answer, category))

    # Дедупликация внутри страницы
    seen = set()
    unique = []
    for t, a, c in found:
        key = (t[:80], a[:40])
        if key in seen:
            continue
        seen.add(key)
        unique.append((t, a, c))
    return unique


# ---------- Сбор ссылок ----------

def extract_links(html: str, page_url: str) -> set[str]:
    """Все релевантные ссылки на странице (включая пагинацию)."""
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(page_url, href)
        # убираем якоря
        full = full.split("#", 1)[0]
        if is_relevant(full):
            links.add(full)
    return links


# ---------- Обход ----------

async def crawl():
    await init_db()

    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(START_URL, 0)]

    total_added = 0
    total_pages = 0

    async with aiohttp.ClientSession() as session:
        while queue:
            url, depth = queue.pop(0)

            if url in visited:
                continue
            if depth > MAX_DEPTH:
                continue
            visited.add(url)

            if not await can_fetch(url):
                print(f"[skip robots] {url}")
                continue

            html = await fetch(session, url)
            if html is None:
                continue

            total_pages += 1

            # 1. Загадки на этой странице
            riddles = extract_riddles(html, url)
            added_here = 0
            for text, answer, category in riddles:
                ok = await add_riddle(
                    text=text,
                    answer=answer,
                    category=category,
                    difficulty=2,
                    source=url,
                )
                if ok:
                    added_here += 1
            total_added += added_here

            print(f"[{total_pages}] d={depth} +{added_here:3d} | {url}")

            # 2. Новые ссылки
            for link in extract_links(html, url):
                if link not in visited:
                    queue.append((link, depth + 1))

            await asyncio.sleep(DELAY)

    print(f"\n=== Готово ===")
    print(f"Страниц обработано: {total_pages}")
    print(f"Загадок добавлено:  {total_added}")
    print(f"Уникальных URL:     {len(visited)}")


async def main():
    await crawl()


if __name__ == "__main__":
    asyncio.run(main())