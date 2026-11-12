from datetime import date
from database import get_or_create_daily, get_riddle_by_id


async def get_today_challenge():
    today = date.today().isoformat()
    rid = await get_or_create_daily(today)
    if not rid:
        return today, None
    riddle = await get_riddle_by_id(rid)
    return today, riddle