import aiosqlite
import hashlib
import re
from datetime import date, timedelta
from config import DB_PATH, MODERATION_MODE


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = text.replace("ё", "е")
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def make_hash(text: str) -> str:
    return hashlib.md5(normalize_text(text).encode()).hexdigest()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS riddles (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            text         TEXT NOT NULL,
            answer       TEXT NOT NULL,
            solution     TEXT NOT NULL DEFAULT '',
            hint         TEXT NOT NULL DEFAULT '',
            alt_answers  TEXT DEFAULT '',
            category     TEXT NOT NULL,
            difficulty   INTEGER DEFAULT 1,
            source       TEXT DEFAULT '',
            hash         TEXT UNIQUE,
            status       TEXT NOT NULL DEFAULT 'approved',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id          INTEGER PRIMARY KEY,
            username         TEXT,
            points           INTEGER DEFAULT 0,
            streak           INTEGER DEFAULT 0,
            last_solve       TEXT,
            solved_total     INTEGER DEFAULT 0,
            reminder_enabled INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS solved (
            user_id      INTEGER,
            riddle_id    INTEGER,
            solved_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, riddle_id)
        );

        CREATE TABLE IF NOT EXISTS duels (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            player1      INTEGER NOT NULL,
            player2      INTEGER NOT NULL,
            riddle_id    INTEGER NOT NULL,
            winner       INTEGER,
            status       TEXT DEFAULT 'active',
            chat_id      INTEGER,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at  TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS daily (
            date        TEXT PRIMARY KEY,
            riddle_id   INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_solved (
            date        TEXT,
            user_id     INTEGER,
            position    INTEGER,
            solved_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, user_id)
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            username    TEXT DEFAULT '',
            riddle_id   INTEGER NOT NULL,
            riddle_text TEXT NOT NULL DEFAULT '',
            rating      TEXT NOT NULL,
            text        TEXT NOT NULL DEFAULT '',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS achievements (
            user_id     INTEGER,
            code        TEXT,
            unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, code)
        );

        CREATE TABLE IF NOT EXISTS favorites (
            user_id     INTEGER,
            riddle_id   INTEGER,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, riddle_id)
        );

                CREATE INDEX IF NOT EXISTS idx_feedback_rating  ON feedback(rating);
        CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at);
        """)
        # --- миграции ---
        async with db.execute("PRAGMA table_info(riddles)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        for col, ddl in {
            "solution": "ALTER TABLE riddles ADD COLUMN solution TEXT NOT NULL DEFAULT ''",
            "hint":     "ALTER TABLE riddles ADD COLUMN hint TEXT NOT NULL DEFAULT ''",
            "status":   "ALTER TABLE riddles ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'",
            "created_at": "ALTER TABLE riddles ADD COLUMN created_at TIMESTAMP",
        }.items():
            if col not in cols:
                await db.execute(ddl)

        async with db.execute("PRAGMA table_info(users)") as cur:
            ucols = {row[1] for row in await cur.fetchall()}
        if "reminder_enabled" not in ucols:
            await db.execute("ALTER TABLE users ADD COLUMN reminder_enabled INTEGER DEFAULT 1")

        await db.commit()


# ============ ЗАГАДКИ ============

async def add_riddle(text, answer, category, difficulty=1,
                     source="", alt_answers="", solution="", hint="",
                     status: str | None = None):
    if status is None:
        status = "pending" if MODERATION_MODE else "approved"
    h = make_hash(text)
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO riddles "
                "(text, answer, alt_answers, category, difficulty, source, hash, solution, hint, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (text, answer, alt_answers, category, difficulty,
                 source, h, solution, hint, status)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def delete_riddle(rid: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM riddles WHERE id = ?", (rid,))
        await db.execute("DELETE FROM daily WHERE riddle_id = ?", (rid,))
        await db.execute("DELETE FROM favorites WHERE riddle_id = ?", (rid,))
        await db.commit()
        return cur.rowcount > 0


async def approve_riddle(rid: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE riddles SET status = 'approved' WHERE id = ?", (rid,))
        await db.commit()
        return cur.rowcount > 0


async def reject_riddle(rid: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE riddles SET status = 'rejected' WHERE id = ?", (rid,))
        await db.commit()
        return cur.rowcount > 0


async def get_pending_riddles(limit: int = 5):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, text, answer, category, difficulty, solution, hint "
            "FROM riddles WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
            (limit,)
        ) as cur:
            return await cur.fetchall()


async def count_pending() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM riddles WHERE status='pending'") as cur:
            return (await cur.fetchone())[0]


async def get_random_riddle(category=None, exclude_ids=None, difficulty=None):
    query = ("SELECT id, text, answer, alt_answers, category, difficulty "
             "FROM riddles WHERE status = 'approved'")
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)
    if difficulty:
        query += " AND difficulty >= ?"
        params.append(difficulty)
    if exclude_ids:
        placeholders = ",".join("?" * len(exclude_ids))
        query += f" AND id NOT IN ({placeholders})"
        params.extend(exclude_ids)

    query += " ORDER BY RANDOM() LIMIT 1"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cur:
            return await cur.fetchone()


async def get_riddle_by_id(rid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, text, answer, alt_answers, category, solution, hint "
            "FROM riddles WHERE id = ?", (rid,)
        ) as cur:
            return await cur.fetchone()


async def count_riddles():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM riddles WHERE status='approved'") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def count_by_category():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT category, COUNT(*) FROM riddles WHERE status='approved' "
            "GROUP BY category ORDER BY COUNT(*) DESC"
        ) as cur:
            return await cur.fetchall()


# ============ ПОЛЬЗОВАТЕЛИ ============

async def get_or_create_user(user_id, username):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        await db.commit()


async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT points, streak, solved_total FROM users WHERE user_id = ?",
            (user_id,)
        ) as cur:
            return await cur.fetchone()


async def add_points(user_id: int, points: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET points = points + ? WHERE user_id = ?",
            (points, user_id)
        )
        await db.commit()


async def mark_solved_and_reward(user_id, riddle_id, points):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO solved (user_id, riddle_id) VALUES (?, ?)",
                (user_id, riddle_id)
            )
        except aiosqlite.IntegrityError:
            return False
        await db.execute(
            "UPDATE users SET points = points + ?, solved_total = solved_total + 1 "
            "WHERE user_id = ?", (points, user_id)
        )
        await db.commit()
        return True


async def update_streak(user_id, today: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_solve, streak FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        last_solve, streak = row if row else (None, 0)
        if last_solve == today:
            return streak
        yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
        new_streak = streak + 1 if last_solve == yesterday else 1
        await db.execute(
            "UPDATE users SET last_solve = ?, streak = ? WHERE user_id = ?",
            (today, new_streak, user_id)
        )
        await db.commit()
        return new_streak


async def get_top(limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username, points FROM users ORDER BY points DESC LIMIT ?",
            (limit,)
        ) as cur:
            return await cur.fetchall()


async def get_preferred_difficulty(user_id: int) -> int:
    """Автоподбор сложности по истории пользователя и его 👎."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT solved_total, streak FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        solved_total, streak = row if row else (0, 0)

        async with db.execute(
            "SELECT COUNT(*) FROM feedback WHERE user_id = ? AND rating = 'down'",
            (user_id,)
        ) as cur:
            downs = (await cur.fetchone())[0]

    if solved_total < 5:
        return 1
    if downs >= 3 and downs * 2 > solved_total:
        return 1   # много жалоб → полегче
    if solved_total >= 30 and streak >= 5:
        return 4
    if solved_total >= 10:
        return 3
    return 2


# ============ ДУЭЛИ ============

async def create_duel(player1: int, player2: int, riddle_id: int, chat_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO duels (player1, player2, riddle_id, chat_id) VALUES (?, ?, ?, ?)",
            (player1, player2, riddle_id, chat_id)
        )
        await db.commit()
        return cur.lastrowid


async def get_duel_by_id(duel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, player1, player2, riddle_id, winner, status, chat_id "
            "FROM duels WHERE id = ?", (duel_id,)
        ) as cur:
            return await cur.fetchone()


async def finish_duel(duel_id: int, winner):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE duels SET status = 'finished', winner = ?, "
            "finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (winner, duel_id)
        )
        await db.commit()


async def get_duel_stats(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM duels WHERE status='finished' AND winner = ?",
            (user_id,)
        ) as cur:
            wins = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM duels WHERE status='finished' "
            "AND (player1 = ? OR player2 = ?)", (user_id, user_id)
        ) as cur:
            total = (await cur.fetchone())[0]
        return wins, total


# ============ ЕЖЕДНЕВНЫЙ ЧЕЛЛЕНДЖ ============

async def get_or_create_daily(today: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT riddle_id FROM daily WHERE date = ?", (today,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                async with db.execute(
                    "SELECT 1 FROM riddles WHERE id = ? AND status='approved'",
                    (row[0],)
                ) as cur2:
                    if await cur2.fetchone():
                        return row[0]
                await db.execute("DELETE FROM daily WHERE date = ?", (today,))

        async with db.execute(
            "SELECT id FROM riddles WHERE status='approved' ORDER BY RANDOM() LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            rid = row[0]

        await db.execute("INSERT INTO daily (date, riddle_id) VALUES (?, ?)",
                         (today, rid))
        await db.commit()
        return rid


async def try_daily_solve(today: str, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM daily_solved WHERE date = ?", (today,)
        ) as cur:
            count = (await cur.fetchone())[0]
        position = count + 1
        try:
            await db.execute(
                "INSERT INTO daily_solved (date, user_id, position) VALUES (?, ?, ?)",
                (today, user_id, position)
            )
        except aiosqlite.IntegrityError:
            return None
        await db.commit()
        return position


async def daily_leaderboard(today: str, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT u.username, d.position, d.solved_at "
            "FROM daily_solved d LEFT JOIN users u ON u.user_id = d.user_id "
            "WHERE d.date = ? ORDER BY d.position ASC LIMIT ?",
            (today, limit)
        ) as cur:
            return await cur.fetchall()


async def daily_solved_count(today: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM daily_solved WHERE date = ?", (today,)
        ) as cur:
            return (await cur.fetchone())[0]


# ============ ОТЗЫВЫ ============

async def add_feedback(user_id, username, riddle_id, riddle_text, rating, text="") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO feedback (user_id, username, riddle_id, riddle_text, rating, text) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username or "", riddle_id, riddle_text, rating, text)
        )
        await db.commit()
        return cur.lastrowid


async def update_feedback_text(feedback_id: int, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE feedback SET text = ? WHERE id = ?", (text, feedback_id))
        await db.commit()


async def get_recent_feedback(limit: int = 20, rating: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if rating:
            q = ("SELECT id, user_id, username, riddle_id, riddle_text, rating, text, created_at "
                 "FROM feedback WHERE rating = ? ORDER BY id DESC LIMIT ?")
            params = (rating, limit)
        else:
            q = ("SELECT id, user_id, username, riddle_id, riddle_text, rating, text, created_at "
                 "FROM feedback ORDER BY id DESC LIMIT ?")
            params = (limit,)
        async with db.execute(q, params) as cur:
            return await cur.fetchall()


async def get_feedback_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM feedback") as cur:
            total = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM feedback WHERE rating='up'") as cur:
            up = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM feedback WHERE rating='down'") as cur:
            down = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM feedback WHERE text != ''") as cur:
            with_text = (await cur.fetchone())[0]
        return total, up, down, with_text


async def get_top_downvoted_riddles(limit: int = 5):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT riddle_id, COUNT(*) AS c, MIN(riddle_text) "
            "FROM feedback WHERE rating='down' "
            "GROUP BY riddle_id ORDER BY c DESC LIMIT ?", (limit,)
        ) as cur:
            return await cur.fetchall()


# ============ ДОСТИЖЕНИЯ ============

async def unlock_achievement(user_id: int, code: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO achievements (user_id, code) VALUES (?, ?)",
                (user_id, code)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def has_achievement(user_id: int, code: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM achievements WHERE user_id = ? AND code = ?",
            (user_id, code)
        ) as cur:
            return await cur.fetchone() is not None


async def get_user_achievements(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT code, unlocked_at FROM achievements WHERE user_id = ? "
            "ORDER BY unlocked_at ASC", (user_id,)
        ) as cur:
            return await cur.fetchall()


# ============ ИЗБРАННОЕ ============

async def add_favorite(user_id: int, riddle_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO favorites (user_id, riddle_id) VALUES (?, ?)",
                (user_id, riddle_id)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_favorite(user_id: int, riddle_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM favorites WHERE user_id = ? AND riddle_id = ?",
            (user_id, riddle_id)
        )
        await db.commit()
        return cur.rowcount > 0


async def is_favorite(user_id: int, riddle_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND riddle_id = ?",
            (user_id, riddle_id)
        ) as cur:
            return await cur.fetchone() is not None


async def get_favorites(user_id: int, limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT r.id, r.text, r.category "
            "FROM favorites f JOIN riddles r ON r.id = f.riddle_id "
            "WHERE f.user_id = ? AND r.status = 'approved' "
            "ORDER BY f.created_at DESC LIMIT ?", (user_id, limit)
        ) as cur:
            return await cur.fetchall()


# ============ РАССЫЛКИ ============

async def get_users_for_reminder():
    """Пользователи, у которых last_solve == вчера и не сегодня, напоминания включены."""
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, streak FROM users "
            "WHERE last_solve = ? AND reminder_enabled = 1 AND streak > 0",
            (yesterday,)
        ) as cur:
            return await cur.fetchall()


async def toggle_reminder(user_id: int) -> bool:
    """Переключает напоминание. Возвращает новое значение."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT reminder_enabled FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        new_val = 0 if (row and row[0]) else 1
        await db.execute(
            "UPDATE users SET reminder_enabled = ? WHERE user_id = ?",
            (new_val, user_id)
        )
        await db.commit()
        return bool(new_val)


async def get_daily_report_data():
    """Данные для ежедневного отчёта админу."""
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM riddles WHERE date(created_at) = date('now') "
            "AND status = 'approved'"
        ) as cur:
            added_today = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM riddles WHERE status = 'pending'"
        ) as cur:
            pending = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE last_solve = ?", (today,)
        ) as cur:
            active_today = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM feedback WHERE date(created_at) = date('now') "
            "AND rating = 'up'"
        ) as cur:
            fb_up = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM feedback WHERE date(created_at) = date('now') "
            "AND rating = 'down'"
        ) as cur:
            fb_down = (await cur.fetchone())[0]
        top_down = await get_top_downvoted_riddles(3)

    return {
        "added_today": added_today,
        "pending": pending,
        "active_today": active_today,
        "fb_up": fb_up,
        "fb_down": fb_down,
        "top_down": top_down,
    }