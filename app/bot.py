"""
Точка входу. Логіка навмисно тонка:
handlers лише координують Memory + ClaudeClient, вся "бізнес-логіка"
живе в тих двох модулях.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app.memory import Memory
from app.claude_client import ClaudeClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

memory = Memory(settings.db_path)
claude = ClaudeClient(settings.anthropic_api_key)

dp = Dispatcher()


def is_allowed(user_id: int) -> bool:
    if not settings.allowed_user_ids:
        return True  # доступ не обмежено (лише для тестового етапу)
    return user_id in settings.allowed_user_ids


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привіт! Я твій AI-асистент. Просто пиши мені, і я відповім.\n\n"
        "Команди:\n"
        "/remember <текст> — запам'ятати факт надовго\n"
        "/facts — показати, що я про тебе пам'ятаю\n"
        "/forget_all — очистити коротку історію цього чату"
    )


@dp.message(Command("remember"))
async def cmd_remember(message: Message) -> None:
    if not is_allowed(message.from_user.id):
        return
    fact_text = message.text.removeprefix("/remember").strip()
    if not fact_text:
        await message.answer("Напиши так: /remember Andrew трейдер, живе у Ларнаці")
        return
    await memory.add_fact(message.from_user.id, fact_text)
    await message.answer("Запам'ятав.")


@dp.message(Command("facts"))
async def cmd_facts(message: Message) -> None:
    if not is_allowed(message.from_user.id):
        return
    facts = await memory.get_facts(message.from_user.id)
    if not facts:
        await message.answer("Поки що я нічого довгострокового не пам'ятаю.")
        return
    listing = "\n".join(f"• {f}" for f in facts)
    await message.answer(f"Ось що я пам'ятаю:\n{listing}")


@dp.message(Command("forget_all"))
async def cmd_forget_all(message: Message) -> None:
    if not is_allowed(message.from_user.id):
        return
    await memory.clear_history(message.chat.id)
    await message.answer("Коротку історію цього чату очищено.")


@dp.message(F.text)
async def handle_text(message: Message) -> None:
    if not is_allowed(message.from_user.id):
        await message.answer("У тебе немає доступу до цього бота.")
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    await memory.add_message(chat_id, "user", message.text)

    history = await memory.get_history(chat_id)
    facts = await memory.get_facts(user_id)

    try:
        reply_text = await claude.reply(history, facts)
    except Exception:
        logger.exception("Claude API call failed")
        await message.answer("Сталася помилка при зверненні до Claude. Спробуй ще раз.")
        return

    await memory.add_message(chat_id, "assistant", reply_text)
    await message.answer(reply_text)


async def main() -> None:
    settings.validate()
    await memory.init()

    bot = Bot(token=settings.telegram_bot_token)
    logger.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
