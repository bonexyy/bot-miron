import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import BOT_TOKEN, ADMIN_ID
from database import init_db
from handlers import router
from scheduler import scheduler_loop


async def set_commands(bot: Bot):
    cmds = [BotCommand(command="start", description="Главное меню")]
    if ADMIN_ID:
        cmds += [
            BotCommand(command="feedback", description="[admin] Отзывы"),
            BotCommand(command="stats",    description="[admin] Статистика"),
            BotCommand(command="review",   description="[admin] Модерация"),
        ]
    await bot.set_my_commands(cmds)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан в .env")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    await init_db()
    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)

    # Фоновые задачи: ежедневный отчёт + напоминания
    task = asyncio.create_task(scheduler_loop(bot))

    print("Бот запущен ✅")
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\nЗавершение по Ctrl+C")