import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot

import db

logger = logging.getLogger(__name__)


async def check_reminders(bot: Bot):
    now = datetime.now()
    remind_time = now + timedelta(hours=2)

    if now.date() != remind_time.date():
        return

    date_str = now.strftime("%Y-%m-%d")
    time_from = now.strftime("%H:%M")
    time_to = remind_time.strftime("%H:%M")

    bookings = await db.get_unreminded_bookings(date_str, time_from, time_to)

    for b in bookings:
        try:
            await bot.send_message(
                b["user_id"],
                f"Напоминание!\n\n"
                f"Через ~2 часа у вас запись:\n"
                f"Услуга: {b['service_name']}\n"
                f"Время: {b['time']}\n\n"
                f"Ждём вас!",
            )
        except Exception as e:
            logger.error(f"Failed to send reminder to {b['user_id']}: {e}")


async def reminder_loop(bot: Bot):
    while True:
        try:
            await check_reminders(bot)
        except Exception as e:
            logger.error(f"Reminder check error: {e}")
        await asyncio.sleep(600)
