import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "bookings.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                duration_min INTEGER NOT NULL DEFAULT 60,
                price INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT,
                service_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                reminded INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (service_id) REFERENCES services(id)
            )
        """)
        cursor = await db.execute("SELECT COUNT(*) FROM services")
        count = (await cursor.fetchone())[0]
        if count == 0:
            demo = [
                ("Женская стрижка", 60, 2500),
                ("Мужская стрижка", 45, 1500),
                ("Окрашивание", 120, 4000),
                ("Маникюр с гель-лаком", 60, 2500),
                ("Укладка", 45, 1500),
            ]
            await db.executemany(
                "INSERT INTO services (name, duration_min, price) VALUES (?, ?, ?)",
                demo,
            )
        await db.commit()


async def get_services():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM services ORDER BY id")
        return await cursor.fetchall()


async def get_service(service_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM services WHERE id = ?", (service_id,))
        return await cursor.fetchone()


async def create_booking(user_id: int, username: str, full_name: str,
                         service_id: int, date: str, time: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO bookings (user_id, username, full_name, service_id, date, time)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, username, full_name, service_id, date, time),
        )
        await db.commit()
        return cursor.lastrowid


async def get_bookings_for_date(date: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT b.*, s.name as service_name, s.duration_min, s.price
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.date = ? AND b.status = 'active'
               ORDER BY b.time""",
            (date,),
        )
        return await cursor.fetchall()


async def get_user_bookings(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT b.*, s.name as service_name, s.price
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.user_id = ? AND b.status = 'active'
               ORDER BY b.date, b.time""",
            (user_id,),
        )
        return await cursor.fetchall()


async def cancel_booking(booking_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND status = 'active'",
            (booking_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_all_active_bookings():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT b.*, s.name as service_name, s.price
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.status = 'active'
               ORDER BY b.date, b.time""",
        )
        return await cursor.fetchall()


async def get_cancelled_bookings():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT b.*, s.name as service_name, s.price
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.status = 'cancelled'
               ORDER BY b.date, b.time""",
        )
        return await cursor.fetchall()


async def get_unreminded_bookings(date: str, time_from: str, time_to: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT b.*, s.name as service_name
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.date = ? AND b.time >= ? AND b.time <= ?
                 AND b.status = 'active' AND b.reminded = 0""",
            (date, time_from, time_to),
        )
        rows = await cursor.fetchall()
        for row in rows:
            await db.execute(
                "UPDATE bookings SET reminded = 1 WHERE id = ?", (row["id"],)
            )
        await db.commit()
        return rows


async def is_time_taken(date: str, time: str, service_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT COUNT(*) FROM bookings
               WHERE date = ? AND time = ? AND status = 'active'""",
            (date, time),
        )
        count = (await cursor.fetchone())[0]
        return count > 0
