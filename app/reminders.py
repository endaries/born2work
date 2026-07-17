"""
Нагадування/задачі. Окрема таблиця в тій самій SQLite базі, що й пам'ять.

Логіка навмисно проста: жодного окремого планувальника (APScheduler тощо) —
просто фоновий цикл у bot.py раз на хвилину питає "чи є прострочені
нагадування?" і надсилає їх. Для десятків-сотень нагадувань цього достатньо.
"""
import time
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    due_at REAL NOT NULL,
    text TEXT NOT NULL,
    created_at REAL NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at, sent);
"""


class Reminders:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def add(self, chat_id: int, due_at: float, text: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO reminders (chat_id, due_at, text, created_at, sent) "
                "VALUES (?, ?, ?, ?, 0)",
                (chat_id, due_at, text, time.time()),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_upcoming(self, chat_id: int) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, due_at, text FROM reminders "
                "WHERE chat_id = ? AND sent = 0 ORDER BY due_at ASC",
                (chat_id,),
            )
            rows = await cursor.fetchall()
            return [{"id": r["id"], "due_at": r["due_at"], "text": r["text"]} for r in rows]

    async def get_due(self, now: float) -> list[dict]:
        """Всі нагадування (з усіх чатів), час яких настав і які ще не надіслані."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, chat_id, text FROM reminders WHERE sent = 0 AND due_at <= ?",
                (now,),
            )
            rows = await cursor.fetchall()
            return [{"id": r["id"], "chat_id": r["chat_id"], "text": r["text"]} for r in rows]

    async def mark_sent(self, reminder_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
            await db.commit()

    async def cancel(self, chat_id: int, reminder_id: int) -> bool:
        """Повертає True, якщо щось справді видалено."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM reminders WHERE id = ? AND chat_id = ?",
                (reminder_id, chat_id),
            )
            await db.commit()
            return cursor.rowcount > 0