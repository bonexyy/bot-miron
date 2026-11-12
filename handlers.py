from datetime import date

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import CommandStart
from rapidfuzz import fuzz

from config import (
    POINTS_CORRECT, DUEL_WIN_POINTS, DUEL_LOSE_POINTS,
    DAILY_FIRST_BONUS, DAILY_BASE_POINTS, DAILY_TOP_LIMIT,
)
from database import (
    get_or_create_user, get_random_riddle, get_user,
    mark_solved_and_reward, update_streak, get_top,
    normalize_text, count_riddles,
    get_duel_by_id, finish_duel, add_points, get_duel_stats,
    try_daily_solve, daily_leaderboard, daily_solved_count,
    get_riddle_by_id,
)
from keyboards import (
    main_menu, categories_menu, riddle_actions, back_to_menu,
    duel_menu, daily_menu,
)
from puzzles import make_puzzle, check_puzzle
from duels import (
    join_queue, leave_queue, start_duel, is_in_duel,
    clear_duel, active_duels,
)
from daily import get_today_challenge

router = Router()

# user_id -> {"type": "riddle"/"puzzle"/"daily", ...}
active = {}


# ==================== /start ====================
@router.message(CommandStart())
async def cmd_start(message: Message):
    await get_or_create_user(message.from_user.id, message.from_user.username)
    total = await count_riddles()
    await message.answer(
        f"Привет! Я бот-загадочник 🧠\n"
        f"В базе уже {total} загадок.\n\n"
        f"Решай, собирай очки и поднимайся в топе.",
        reply_markup=main_menu()
    )


# ==================== Меню ====================
@router.callback_query(F.data == "back")
async def go_back(cb: CallbackQuery):
    await cb.message.edit_text("Главное меню:", reply_markup=main_menu())


@router.callback_query(F.data == "categories")
async def show_categories(cb: CallbackQuery):
    await cb.message.edit_text("Выбери категорию:", reply_markup=categories_menu())


@router.callback_query(F.data == "profile")
async def show_profile(cb: CallbackQuery):
    row = await get_user(cb.from_user.id)
    points, streak, solved = row if row else (0, 0, 0)
    wins, total = await get_duel_stats(cb.from_user.id)
    await cb.message.edit_text(
        f"👤 <b>Профиль</b>\n\n"
        f"⭐ Очки: <b>{points}</b>\n"
        f"🔥 Стрик: <b>{streak}</b>\n"
        f"✅ Решено: <b>{solved}</b>\n"
        f"⚔️ Дуэли: <b>{wins}</b> побед из <b>{total}</b>",
        reply_markup=back_to_menu()
    )


@router.callback_query(F.data == "top")
async def show_top(cb: CallbackQuery):
    rows = await get_top(10)
    text = "🏆 <b>Топ-10</b>\n\n"
    if not rows:
        text += "Пока пусто."
    for i, (name, pts) in enumerate(rows, 1):
        text += f"{i}. @{name or 'аноним'} — {pts}\n"
    await cb.message.edit_text(text, reply_markup=back_to_menu())


# ==================== Обычные загадки ====================
@router.callback_query(F.data == "random")
async def send_random(cb: CallbackQuery):
    await _send_riddle(cb, category=None)


@router.callback_query(F.data.startswith("cat:"))
async def send_by_category(cb: CallbackQuery):
    category = cb.data.split(":", 1)[1]
    await _send_riddle(cb, category=category)


async def _send_riddle(cb: CallbackQuery, category):
    row = await get_random_riddle(category=category)
    if not row:
        await cb.message.edit_text(
            "Загадок в этой категории пока нет 😔",
            reply_markup=back_to_menu()
        )
        return

    rid, text, answer, alt, cat = row
    active[cb.from_user.id] = {
        "type": "riddle",
        "id": rid,
        "answer": answer,
        "alt": alt or "",
    }

    await cb.message.edit_text(
        f"🧩 <b>{cat}</b>\n\n{text}\n\n<i>Напиши ответ сообщением.</i>",
        reply_markup=riddle_actions(rid)
    )


# ==================== Обработка ответов ====================
@router.message(F.text)
async def check_answer(message: Message, bot: Bot):
    user_id = message.from_user.id

    # 1) Дуэль?
    if is_in_duel(user_id):
        await _handle_duel_answer(message, bot)
        return

    state = active.get(user_id)
    if not state:
        await message.answer("Сначала выбери загадку 👇", reply_markup=main_menu())
        return

    # 2) Пазл
    if state["type"] == "puzzle":
        correct = [int(x) for x in state["answer"].split()]
        if check_puzzle(message.text, correct):
            active.pop(user_id, None)
            await message.answer("✅ Пазл собран! Молодец 🎉", reply_markup=main_menu())
        else:
            await message.answer("❌ Порядок неверный. Попробуй ещё.")
        return

    # 3) Обычная или daily
    rid = state["id"]
    answer = state["answer"]
    alt = state["alt"]
    variants = [answer] + [a for a in alt.split("|") if a]
    user_norm = normalize_text(message.text)
    is_correct = any(
        fuzz.ratio(user_norm, normalize_text(v)) >= 85 for v in variants
    )

    if not is_correct:
        await message.answer("❌ Не то. Попробуй ещё или нажми «Сдаюсь».")
        return

    if state["type"] == "daily":
        today = state["date"]
        position = await try_daily_solve(today, user_id)
        active.pop(user_id, None)
        if position is None:
            await message.answer("Ты уже решил сегодняшний челлендж 😉",
                                 reply_markup=main_menu())
            return
        points = DAILY_FIRST_BONUS if position == 1 else DAILY_BASE_POINTS
        await add_points(user_id, points)
        medal = "🥇" if position == 1 else "🎖"
        await message.answer(
            f"✅ <b>Верно!</b>\n"
            f"{medal} Ты #{position} сегодня\n"
            f"+{points} очков",
            reply_markup=main_menu()
        )
        return

    # Обычная
    rewarded = await mark_solved_and_reward(user_id, rid, POINTS_CORRECT)
    if not rewarded:
        active.pop(user_id, None)
        await message.answer("Ты уже решал эту загадку 😉", reply_markup=main_menu())
        return

    today = date.today().isoformat()
    streak = await update_streak(user_id, today)
    active.pop(user_id, None)

    await message.answer(
        f"✅ <b>Верно!</b>\n+{POINTS_CORRECT} очков\n🔥 Стрик: {streak}",
        reply_markup=main_menu()
    )


async def _handle_duel_answer(message: Message, bot: Bot):
    user_id = message.from_user.id
    duel_id = active_duels.get(user_id)
    if not duel_id:
        return

    duel = await get_duel_by_id(duel_id)
    if not duel or duel[5] != "active":
        clear_duel(duel_id)
        return

    _, p1, p2, rid, _, _, chat_id = duel
    opponent = p2 if user_id == p1 else p1

    riddle = await get_riddle_by_id(rid)
    if not riddle:
        return
    _, text, answer, alt, _ = riddle

    variants = [answer] + [a for a in (alt or "").split("|") if a]
    user_norm = normalize_text(message.text)
    is_correct = any(
        fuzz.ratio(user_norm, normalize_text(v)) >= 85 for v in variants
    )

    if not is_correct:
        await message.answer("❌ Не то. Соперник может успеть первым!")
        return

    await finish_duel(duel_id, winner=user_id)
    await add_points(user_id, DUEL_WIN_POINTS)
    await add_points(opponent, DUEL_LOSE_POINTS)
    clear_duel(duel_id)

    await message.answer(
        f"🏆 <b>Ты победил в дуэли!</b>\n+{DUEL_WIN_POINTS} очков",
        reply_markup=main_menu()
    )
    try:
        await bot.send_message(
            opponent,
            f"😔 Соперник оказался быстрее. +{DUEL_LOSE_POINTS} за участие.",
            reply_markup=main_menu()
        )
    except Exception:
        pass


# ==================== Сдаюсь / Подсказка ====================
@router.callback_query(F.data.startswith("give_up:"))
async def give_up(cb: CallbackQuery):
    state = active.get(cb.from_user.id)
    if not state or state["type"] != "riddle":
        await cb.answer("Загадка уже закрыта")
        return
    answer = state["answer"]
    active.pop(cb.from_user.id, None)
    await cb.message.edit_text(
        f"Правильный ответ: <b>{answer}</b>",
        reply_markup=main_menu()
    )


@router.callback_query(F.data.startswith("hint:"))
async def hint(cb: CallbackQuery):
    state = active.get(cb.from_user.id)
    if not state or state["type"] != "riddle":
        await cb.answer("Нет активной загадки")
        return
    answer = state["answer"]
    first = answer[0].upper()
    await cb.answer(f"Подсказка: ответ начинается на «{first}»", show_alert=True)


# ==================== Пазл ====================
@router.callback_query(F.data == "puzzle")
async def send_puzzle(cb: CallbackQuery):
    try:
        with open("data/sample.jpg", "rb") as f:
            img_bytes = f.read()
    except FileNotFoundError:
        await cb.answer("Картинка не найдена", show_alert=True)
        return

    puzzle_bytes, correct = make_puzzle(img_bytes, grid=3)
    active[cb.from_user.id] = {
        "type": "puzzle",
        "id": -1,
        "answer": " ".join(map(str, correct)),
        "alt": "",
    }

    await cb.message.answer_photo(
        BufferedInputFile(puzzle_bytes, filename="puzzle.jpg"),
        caption=(
            "🧩 <b>Собери пазл!</b>\n\n"
            "На каждом куске — номер. Напиши, в каком порядке они должны "
            "стоять (например: <code>1 2 3 4 5 6 7 8 9</code>)."
        )
    )


# ==================== ДУЭЛИ ====================
@router.callback_query(F.data == "duel")
async def duel_entry(cb: CallbackQuery):
    wins, total = await get_duel_stats(cb.from_user.id)
    text = (
        f"⚔️ <b>Дуэли</b>\n\n"
        f"Победы: <b>{wins}</b> / {total}\n\n"
        f"Нажми «Найти соперника» — я подберу противника.\n"
        f"Победитель получает <b>+{DUEL_WIN_POINTS}</b>, "
        f"проигравший — <b>+{DUEL_LOSE_POINTS}</b>."
    )
    await cb.message.edit_text(text, reply_markup=duel_menu())


@router.callback_query(F.data == "duel_find")
async def duel_find(cb: CallbackQuery, bot: Bot):
    user_id = cb.from_user.id

    if is_in_duel(user_id):
        await cb.answer("Ты уже в дуэли", show_alert=True)
        return

    opponent = await join_queue(user_id)

    if opponent is None:
        await cb.message.edit_text(
            "🔍 Ищу соперника...\n"
            "Как только кто-то нажмёт «Найти соперника» — начнём.",
            reply_markup=duel_menu()
        )
        return

    duel_id, riddle = await start_duel(opponent, user_id, cb.message.chat.id)
    if not duel_id:
        await cb.message.edit_text("В базе нет загадок 😔", reply_markup=back_to_menu())
        return

    rid, text, answer, alt, cat = riddle
    msg = (
        f"⚔️ <b>Дуэль началась!</b>\n\n"
        f"🧩 <b>{cat}</b>\n\n{text}\n\n"
        f"<i>Кто первый напишет правильный ответ — победил.</i>"
    )
    await cb.message.edit_text(msg)
    try:
        await bot.send_message(opponent, msg)
    except Exception:
        pass


@router.callback_query(F.data == "duel_leave")
async def duel_leave(cb: CallbackQuery):
    left = await leave_queue(cb.from_user.id)
    if left:
        await cb.answer("Ты вышел из очереди", show_alert=True)
    else:
        await cb.answer("Тебя нет в очереди", show_alert=True)
    await cb.message.edit_text("Главное меню:", reply_markup=main_menu())


# ==================== ЕЖЕДНЕВНЫЙ ЧЕЛЛЕНДЖ ====================
@router.callback_query(F.data == "daily")
async def daily_entry(cb: CallbackQuery):
    today, riddle = await get_today_challenge()
    if not riddle:
        await cb.message.edit_text("Загадок пока нет 😔", reply_markup=back_to_menu())
        return

    count = await daily_solved_count(today)
    text = (
        f"🎯 <b>Челлендж на {today}</b>\n\n"
        f"Уже решили: <b>{count}</b> чел.\n"
        f"Первый получает <b>+{DAILY_FIRST_BONUS}</b>, "
        f"остальные — <b>+{DAILY_BASE_POINTS}</b>.\n\n"
        f"Жми «Решить», когда готов."
    )
    await cb.message.edit_text(text, reply_markup=daily_menu())


@router.callback_query(F.data == "daily_solve")
async def daily_solve(cb: CallbackQuery):
    today, riddle = await get_today_challenge()
    if not riddle:
        await cb.answer("Нет загадки на сегодня", show_alert=True)
        return

    rid, text, answer, alt, cat = riddle
    active[cb.from_user.id] = {
        "type": "daily",
        "id": rid,
        "answer": answer,
        "alt": alt or "",
        "date": today,
    }
    await cb.message.edit_text(
        f"🎯 <b>Челлендж дня</b>\n\n{text}\n\n<i>Напиши ответ сообщением.</i>",
        reply_markup=back_to_menu()
    )


@router.callback_query(F.data == "daily_top")
async def daily_top(cb: CallbackQuery):
    today, _ = await get_today_challenge()
    rows = await daily_leaderboard(today, DAILY_TOP_LIMIT)
    text = f"🏆 <b>Лидерборд {today}</b>\n\n"
    if not rows:
        text += "Пока никто не решил. Будь первым!"
    else:
        for i, (name, pos, _ts) in enumerate(rows, 1):
            medal = "🥇" if pos == 1 else "🥈" if pos == 2 else "🥉" if pos == 3 else "▪️"
            text += f"{medal} #{pos} @{name or 'аноним'}\n"
    await cb.message.edit_text(text, reply_markup=back_to_menu())