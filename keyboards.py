from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎯 Челлендж",       callback_data="daily")
    kb.button(text="⚔️ Дуэль",          callback_data="duel")
    kb.button(text="🎲 Загадка",        callback_data="random")
    kb.button(text="📂 Категории",      callback_data="categories")
    kb.button(text="🧩 Пазл",           callback_data="puzzle")
    kb.button(text="⭐ Избранное",      callback_data="favorites")
    kb.button(text="📊 Профиль",        callback_data="profile")
    kb.button(text="🏆 Топ",            callback_data="top")
    kb.adjust(1, 1, 2, 2, 2)
    return kb.as_markup()


def categories_menu():
    kb = InlineKeyboardBuilder()
    for cat in ["Логика", "Математика", "Детские", "Смекалка", "Детективные"]:
        kb.button(text=cat, callback_data=f"cat:{cat}")
    kb.button(text="⬅️ Назад", callback_data="back")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def riddle_actions(riddle_id: int, is_fav: bool = False):
    kb = InlineKeyboardBuilder()
    kb.button(text="💡 Подсказка",  callback_data=f"hint:{riddle_id}")
    kb.button(text="🏳️ Сдаюсь",    callback_data=f"give_up:{riddle_id}")
    fav_text = "💔 Убрать" if is_fav else "⭐ Сохранить"
    kb.button(text=fav_text,         callback_data=f"fav_toggle:{riddle_id}")
    kb.button(text="⏭ Пропустить", callback_data="random")
    kb.adjust(2, 2)
    return kb.as_markup()


def back_to_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 В меню", callback_data="back")
    return kb.as_markup()


def duel_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔍 Найти соперника",  callback_data="duel_find")
    kb.button(text="🚪 Выйти из очереди", callback_data="duel_leave")
    kb.button(text="🏠 В меню",           callback_data="back")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def daily_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ Решить челлендж", callback_data="daily_solve")
    kb.button(text="📋 Лидерборд дня",   callback_data="daily_top")
    kb.button(text="🏠 В меню",          callback_data="back")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def feedback_rating_keyboard(riddle_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="👍 Всё ок",        callback_data=f"fb_up:{riddle_id}")
    kb.button(text="👎 Что-то не так", callback_data=f"fb_down:{riddle_id}")
    kb.adjust(2)
    return kb.as_markup()


def feedback_skip_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="⏭ Пропустить", callback_data="fb_skip")
    return kb.as_markup()


def feedback_admin_keyboard(rows):
    kb = InlineKeyboardBuilder()
    for (fid, uid, uname, rid, rtext, rating, text, created) in rows:
        emoji = "👍" if rating == "up" else "👎"
        kb.button(text=f"🗑 {emoji} задача #{rid}",
                  callback_data=f"fb_del:{rid}:{fid}")
    kb.adjust(2)
    return kb.as_markup()


def confirm_delete_keyboard(riddle_id: int, feedback_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить",
              callback_data=f"fb_del_yes:{riddle_id}:{feedback_id}")
    kb.button(text="❌ Отмена",
              callback_data=f"fb_del_no:{riddle_id}:{feedback_id}")
    kb.adjust(2)
    return kb.as_markup()


# ======================= МОДЕРАЦИЯ =======================
def review_keyboard(riddle_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Одобрить", callback_data=f"review_ok:{riddle_id}")
    kb.button(text="❌ Отклонить", callback_data=f"review_no:{riddle_id}")
    kb.adjust(2)
    return kb.as_markup()


# ======================= ПРОФИЛЬ / НАСТРОЙКИ =======================
def profile_keyboard(reminder_on: bool):
    kb = InlineKeyboardBuilder()
    text = "🔔 Напоминания: вкл" if reminder_on else "🔕 Напоминания: выкл"
    kb.button(text=text, callback_data="toggle_reminder")
    kb.button(text="🏠 В меню", callback_data="back")
    kb.adjust(1, 1)
    return kb.as_markup()


def favorites_list_keyboard(rows):
    kb = InlineKeyboardBuilder()
    for (rid, text, cat) in rows:
        short = text[:30] + ("…" if len(text) > 30 else "")
        kb.button(text=f"#{rid} {short}", callback_data=f"open_fav:{rid}")
    kb.button(text="🏠 В меню", callback_data="back")
    kb.adjust(1)
    return kb.as_markup()