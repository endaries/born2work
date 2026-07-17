"""
Пам'ять асистента. Два шари:

1. Короткострокова (messages) — останні N реплік діалогу в конкретному чаті.
   Потрібна, щоб бот пам'ятав контекст поточної розмови.

2. Довгострокова (facts) — стійкі факти про користувача/домовленості,
   які не залежать від конкретного чату і не "виїжджають" з вікна контексту.
   На цьому етапі це прості key-value записи; пізніше можна замінити
   на векторний пошук, якщо фактів стане багато.

Це навмисно просто (SQLite, без ORM) — легко читати, легко міняти на
Postgres пізніше, якщо буде потрібно.
"""
import time
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,          -- 'user' або 'assistant'
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    fact TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_facts_user ON facts(user_id);
"""

# Скільки останніх реплік тягнути в контекст за замовчуванням
DEFAULT_HISTORY_LIMIT = 20


class Memory:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    # ---------- короткострокова пам'ять ----------

    async def add_message(self, chat_id: int, role: str, content: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, role, content, time.time()),
            )
            await db.commit()

    async def get_history(
        self, chat_id: int, limit: int = DEFAULT_HISTORY_LIMIT
    ) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT role, content FROM (
                    SELECT role, content, created_at FROM messages
                    WHERE chat_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ) ORDER BY created_at ASC
                """,
                (chat_id, limit),
            )
            rows = await cursor.fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in rows]

    async def clear_history(self, chat_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            await db.commit()

    # ---------- довгострокова пам'ять ----------

    async def add_fact(self, user_id: int, fact: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO facts (user_id, fact, created_at) VALUES (?, ?, ?)",
                (user_id, fact, time.time()),
            )
            await db.commit()

    async def get_facts(self, user_id: int) -> list[str]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT fact FROM facts WHERE user_id = ? ORDER BY created_at ASC",
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [r["fact"] for r in rows]
