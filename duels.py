import asyncio
import time
from database import get_random_riddle, create_duel

_queue: dict[int, float] = {}
_queue_lock = asyncio.Lock()
active_duels: dict[int, int] = {}

QUEUE_TIMEOUT = 300


async def join_queue(user_id: int):
    async with _queue_lock:
        now = time.time()
        for uid in list(_queue.keys()):
            if now - _queue[uid] > QUEUE_TIMEOUT:
                _queue.pop(uid, None)

        if user_id in _queue:
            return None

        for opponent in list(_queue.keys()):
            if opponent != user_id:
                _queue.pop(opponent, None)
                return opponent

        _queue[user_id] = now
        return None


async def leave_queue(user_id: int) -> bool:
    async with _queue_lock:
        return _queue.pop(user_id, None) is not None


async def start_duel(player1: int, player2: int, chat_id: int):
    riddle = await get_random_riddle()
    if not riddle:
        return None, None
    rid = riddle[0]
    duel_id = await create_duel(player1, player2, rid, chat_id)
    active_duels[player1] = duel_id
    active_duels[player2] = duel_id
    return duel_id, riddle


def is_in_duel(user_id: int) -> bool:
    return user_id in active_duels


def clear_duel(duel_id: int):
    for uid, did in list(active_duels.items()):
        if did == duel_id:
            active_duels.pop(uid, None)