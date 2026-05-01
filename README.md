# Smart Telegram Bot — AI Support + Booking

Telegram-бот 2-в-1: AI-поддержка клиентов по документам + онлайн-запись на услуги.

## Возможности

### AI-поддержка (RAG)
- Загрузка документов (.txt, .pdf) прямо в бот
- Ответы на вопросы клиентов на основе базы знаний (OpenAI + ChromaDB)
- Обратная связь: "Полезно" / "Не помогло"
- Кнопка связи с менеджером

### Онлайн-запись
- Выбор услуги → дата → время → подтверждение
- Напоминание клиенту за 2 часа
- Просмотр и отмена записей с подтверждением
- Защита от двойной записи на один слот

### Админ-панель
- `/admin` — стать админом
- `/stats` — статистика: база знаний + активные + отменённые записи
- `/all` — записи на сегодня
- `/allweek` — все записи
- `/upload` — загрузить документ в базу знаний
- Уведомления о новых записях

### Интерфейс
- Главное меню с кнопками 2×2
- Кнопка "Старт" внизу чата
- Кнопка "Назад в меню" на каждом экране
- Формат дат: ДД.ММ.ГГГГ

## Стек

- Python 3.12+
- aiogram 3.15
- OpenAI API (GPT-4o-mini)
- ChromaDB — векторный поиск по документам
- SQLite — записи клиентов
- systemd — автозапуск на сервере

## Установка

```bash
git clone https://github.com/Shikaro/smart-telegram-bot.git
cd smart-telegram-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Настройка

Создайте `.env`:

```
BOT_TOKEN=ваш_токен_из_BotFather
OPENAI_API_KEY=ваш_ключ_OpenAI
```

## Запуск

```bash
python bot.py
```

Для запуска 24/7 на сервере — systemd:

```bash
sudo cp smart-bot.service /etc/systemd/system/
sudo systemctl enable smart-bot
sudo systemctl start smart-bot
```

## Структура

```
smart-bot/
├── .env              — токены (не в git)
├── bot.py            — основной бот, меню, FSM, админка
├── rag.py            — RAG: загрузка документов, поиск, ответы через AI
├── db.py             — SQLite: услуги, записи
├── scheduler.py      — напоминания клиентам
├── requirements.txt  — зависимости
└── documents/        — загруженные документы
```

## Автор

Сергей Саплинов — [AIBuild](https://t.me/AI_Build_TOP_BOT)
