import os
import asyncio
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.filters import CommandStart, Command
from aiogram.types import BotCommand
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import db
import rag
import scheduler

load_dotenv()
logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
router = Router()
dp.include_router(router)

ADMIN_IDS: set[int] = set()
MANAGER_LINK = "https://t.me/your_manager"

START_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Старт")]],
    resize_keyboard=True,
)

def fmt_date(date_str: str) -> str:
    """2026-05-03 -> 03.05.2026"""
    d = datetime.fromisoformat(date_str).date()
    return d.strftime("%d.%m.%Y")


WORK_HOURS = list(range(9, 21))
TIME_SLOTS = [f"{h}:{m:02d}" for h in WORK_HOURS for m in (0, 30)]


class BookingStates(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()
    confirming = State()


class AskStates(StatesGroup):
    waiting_question = State()


# ── Главное меню ─────────────────────────────────────────

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Записаться", callback_data="menu_book"),
            InlineKeyboardButton(text="Задать вопрос", callback_data="menu_ask"),
        ],
        [
            InlineKeyboardButton(text="Мои записи", callback_data="menu_mybookings"),
            InlineKeyboardButton(text="Менеджер", url=MANAGER_LINK),
        ],
    ])


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Привет! Я ассистент компании.", reply_markup=START_KB)
    await message.answer(
        "Выберите, что вам нужно:",
        reply_markup=main_menu(),
    )


@router.message(F.text == "Старт")
async def btn_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Выберите, что вам нужно:",
        reply_markup=main_menu(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu())


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    ADMIN_IDS.add(message.from_user.id)
    await message.answer(
        "Ты добавлен как админ.\n\n"
        "/all — записи на сегодня\n"
        "/allweek — все записи\n"
        "/upload — загрузить документ в базу знаний\n"
        "/stats — статистика базы знаний"
    )


# ── Задать вопрос (AI) ──────────────────────────────────

@router.callback_query(F.data == "menu_ask")
async def menu_ask(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AskStates.waiting_question)
    await callback.message.edit_text(
        "Напишите ваш вопрос — я постараюсь ответить.\n\n"
        "Для возврата в меню — /menu"
    )
    await callback.answer()


@router.message(AskStates.waiting_question, F.text)
async def handle_question(message: Message, state: FSMContext):
    if rag.collection.count() == 0:
        await message.answer(
            "База знаний пуста. Обратитесь к менеджеру.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад в меню", callback_data="back_menu")],
            ]),
        )
        return

    thinking = await message.answer("Думаю...")

    try:
        answer = rag.ask(message.text)
        if not answer:
            answer = "К сожалению, я не нашёл ответа."
    except Exception as e:
        logging.error(f"RAG error: {e}")
        answer = "Произошла ошибка. Попробуйте переформулировать вопрос."

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Полезно", callback_data="fb_good"),
            InlineKeyboardButton(text="Не помогло", callback_data="fb_bad"),
        ],
        [InlineKeyboardButton(text="Назад в меню", callback_data="back_menu")],
    ])

    await thinking.edit_text(answer, reply_markup=keyboard)


@router.callback_query(F.data == "fb_good")
async def fb_good(callback: CallbackQuery):
    await callback.answer("Спасибо за отзыв!")


@router.callback_query(F.data == "fb_bad")
async def fb_bad(callback: CallbackQuery):
    await callback.answer("Спасибо! Попробуйте связаться с менеджером.", show_alert=True)


# ── Загрузка документов (админ) ──────────────────────────

@router.message(Command("upload"))
async def cmd_upload(message: Message):
    await message.answer("Отправь файл (.txt или .pdf) — я добавлю его в базу знаний.")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    count = rag.collection.count()
    bookings = await db.get_all_active_bookings()
    cancelled = await db.get_cancelled_bookings()

    text = f"База знаний: {count} фрагментов\n"
    text += f"Активных записей: {len(bookings)}\n"
    text += f"Отменённых записей: {len(cancelled)}\n"

    if bookings:
        text += "\nАктивные записи:\n\n"
        for i, b in enumerate(bookings, 1):
            name = b["full_name"] or "—"
            username = f" (@{b['username']})" if b["username"] else ""
            text += (
                f"#{i} | {fmt_date(b['date'])} {b['time']}\n"
                f"   {b['service_name']} — {b['price']} руб.\n"
                f"   Клиент: {name}{username}\n\n"
            )

    if cancelled:
        text += "—————————————————\n"
        text += "Отменённые записи:\n\n"
        for i, b in enumerate(cancelled, 1):
            name = b["full_name"] or "—"
            username = f" (@{b['username']})" if b["username"] else ""
            text += (
                f"#{i} | {fmt_date(b['date'])} {b['time']}\n"
                f"   {b['service_name']} — {b['price']} руб.\n"
                f"   Клиент: {name}{username}\n\n"
            )

    await message.answer(text)


@router.message(F.document)
async def handle_document(message: Message):
    doc = message.document
    filename = doc.file_name or "unknown"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in (".txt", ".pdf"):
        await message.answer("Поддерживаются только .txt и .pdf файлы.")
        return

    status = await message.answer("Загружаю и обрабатываю документ...")

    file_path = f"documents/{filename}"
    await bot.download(doc, destination=file_path)

    try:
        chunks = rag.add_document(file_path)
        await status.edit_text(f"Документ «{filename}» добавлен ({chunks} фрагментов).")
    except Exception as e:
        logging.error(f"Error processing document: {e}")
        await status.edit_text("Ошибка при обработке документа.")


# ── Записаться ───────────────────────────────────────────

@router.callback_query(F.data == "menu_book")
async def menu_book(callback: CallbackQuery, state: FSMContext):
    services = await db.get_services()
    buttons = []
    for s in services:
        buttons.append([
            InlineKeyboardButton(
                text=f"{s['name']} — {s['price']} руб.",
                callback_data=f"srv_{s['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="Назад в меню", callback_data="back_menu")])

    await callback.message.edit_text(
        "Выберите услугу:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await state.set_state(BookingStates.choosing_service)
    await callback.answer()


@router.callback_query(BookingStates.choosing_service, F.data.startswith("srv_"))
async def choose_service(callback: CallbackQuery, state: FSMContext):
    service_id = int(callback.data.split("_")[1])
    service = await db.get_service(service_id)
    await state.update_data(service_id=service_id, service_name=service["name"],
                            service_price=service["price"])

    buttons = []
    today = datetime.now().date()
    for i in range(7):
        d = today + timedelta(days=i)
        label = d.strftime("%d.%m (%a)")
        buttons.append([
            InlineKeyboardButton(text=label, callback_data=f"date_{d.isoformat()}")
        ])
    buttons.append([InlineKeyboardButton(text="Назад в меню", callback_data="back_menu")])

    await callback.message.edit_text(
        f"Услуга: {service['name']}\n\nВыберите дату:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await state.set_state(BookingStates.choosing_date)
    await callback.answer()


@router.callback_query(BookingStates.choosing_date, F.data.startswith("date_"))
async def choose_date(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split("_")[1]
    await state.update_data(date=date_str)

    bookings = await db.get_bookings_for_date(date_str)
    taken = {b["time"] for b in bookings}

    now = datetime.now()
    chosen_date = datetime.fromisoformat(date_str).date()

    buttons = []
    row = []
    for slot in TIME_SLOTS:
        if chosen_date == now.date():
            slot_hour, slot_min = map(int, slot.split(":"))
            if slot_hour < now.hour or (slot_hour == now.hour and slot_min <= now.minute):
                continue
        if slot in taken:
            continue
        row.append(InlineKeyboardButton(text=slot, callback_data=f"time_{slot}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    if not buttons:
        buttons.append([InlineKeyboardButton(text="Назад в меню", callback_data="back_menu")])
        await callback.message.edit_text(
            "На эту дату нет свободных слотов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
        await state.clear()
        await callback.answer()
        return

    buttons.append([InlineKeyboardButton(text="Назад в меню", callback_data="back_menu")])
    data = await state.get_data()
    await callback.message.edit_text(
        f"Услуга: {data['service_name']}\nДата: {fmt_date(date_str)}\n\nВыберите время:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await state.set_state(BookingStates.choosing_time)
    await callback.answer()


@router.callback_query(BookingStates.choosing_time, F.data.startswith("time_"))
async def choose_time(callback: CallbackQuery, state: FSMContext):
    time_str = callback.data.split("_", 1)[1]
    await state.update_data(time=time_str)
    data = await state.get_data()

    buttons = [
        [
            InlineKeyboardButton(text="Подтвердить", callback_data="confirm_yes"),
            InlineKeyboardButton(text="Отмена", callback_data="back_menu"),
        ]
    ]

    await callback.message.edit_text(
        f"Подтвердите запись:\n\n"
        f"Услуга: {data['service_name']}\n"
        f"Дата: {fmt_date(data['date'])}\n"
        f"Время: {time_str}\n"
        f"Цена: {data['service_price']} руб.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await state.set_state(BookingStates.confirming)
    await callback.answer()


@router.callback_query(BookingStates.confirming, F.data == "confirm_yes")
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = callback.from_user

    if await db.is_time_taken(data["date"], data["time"], data["service_id"]):
        await callback.message.edit_text(
            "Это время уже занято. Попробуйте другое.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад в меню", callback_data="back_menu")]
            ]),
        )
        await state.clear()
        await callback.answer()
        return

    booking_id = await db.create_booking(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        service_id=data["service_id"],
        date=data["date"],
        time=data["time"],
    )

    await callback.message.edit_text(
        f"Вы записаны!\n\n"
        f"Услуга: {data['service_name']}\n"
        f"Дата: {fmt_date(data['date'])}\n"
        f"Время: {data['time']}\n"
        f"Цена: {data['service_price']} руб.\n\n"
        f"Напоминание придёт за 2 часа.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад в меню", callback_data="back_menu")]
        ]),
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"Новая запись!\n"
                f"Клиент: {user.full_name} (@{user.username})\n"
                f"Услуга: {data['service_name']}\n"
                f"Дата: {fmt_date(data['date'])} в {data['time']}",
            )
        except Exception:
            pass

    await state.clear()
    await callback.answer()


# ── Мои записи ───────────────────────────────────────────

@router.callback_query(F.data == "menu_mybookings")
async def menu_mybookings(callback: CallbackQuery):
    bookings = await db.get_user_bookings(callback.from_user.id)
    if not bookings:
        await callback.message.edit_text(
            "У вас нет активных записей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Записаться", callback_data="menu_book")],
                [InlineKeyboardButton(text="Назад в меню", callback_data="back_menu")],
            ]),
        )
        await callback.answer()
        return

    text = "Ваши записи:\n\n"
    buttons = []
    for i, b in enumerate(bookings, 1):
        text += f"#{i} | {b['service_name']}\n   {fmt_date(b['date'])} в {b['time']} — {b['price']} руб.\n\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"Отменить #{i}",
                callback_data=f"cancelb_{b['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="Назад в меню", callback_data="back_menu")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancelb_"))
async def cancel_booking_cb(callback: CallbackQuery):
    booking_id = callback.data.split("_")[1]
    await callback.message.edit_text(
        "Вы уверены, что хотите отменить запись?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, отменить", callback_data=f"confirmcancel_{booking_id}"),
                InlineKeyboardButton(text="Нет, оставить", callback_data="menu_mybookings"),
            ]
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirmcancel_"))
async def confirm_cancel_cb(callback: CallbackQuery):
    booking_id = int(callback.data.split("_")[1])
    success = await db.cancel_booking(booking_id)
    text = "Запись отменена." if success else "Запись не найдена."
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад в меню", callback_data="back_menu")]
        ]),
    )
    await callback.answer()


# ── Назад в меню ─────────────────────────────────────────

@router.callback_query(F.data == "back_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите, что вам нужно:",
        reply_markup=main_menu(),
    )
    await callback.answer()


# ── Админ ────────────────────────────────────────────────

@router.message(Command("all"))
async def cmd_all_today(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Сначала нажми /admin")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    bookings = await db.get_bookings_for_date(today)
    if not bookings:
        await message.answer("На сегодня записей нет.")
        return
    text = f"Записи на {fmt_date(today)}:\n\n"
    for i, b in enumerate(bookings, 1):
        name = b["full_name"] or "—"
        username = f"@{b['username']}" if b["username"] else "—"
        text += f"#{i} | {b['time']} | {b['service_name']}\n   Клиент: {name} ({username})\n\n"
    await message.answer(text)


@router.message(Command("allweek"))
async def cmd_all_week(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Сначала нажми /admin")
        return
    bookings = await db.get_all_active_bookings()
    if not bookings:
        await message.answer("Активных записей нет.")
        return
    text = "Все активные записи:\n\n"
    current_date = ""
    counter = 1
    for b in bookings:
        if b["date"] != current_date:
            current_date = b["date"]
            text += f"\n{fmt_date(current_date)}\n"
        name = b["full_name"] or "—"
        username = f"@{b['username']}" if b["username"] else "—"
        text += f"  #{counter} | {b['time']} | {b['service_name']}\n    {name} ({username})\n"
        counter += 1
    await message.answer(text)


# ── Обработка любого текста без состояния ─────────────────

@router.message(F.text)
async def fallback_text(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return
    await message.answer(
        "Выберите, что вам нужно:",
        reply_markup=main_menu(),
    )


# ── Запуск ───────────────────────────────────────────────

async def main():
    await db.init_db()
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="menu", description="Главное меню"),
    ])
    asyncio.create_task(scheduler.reminder_loop(bot))
    logging.info("Smart bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
