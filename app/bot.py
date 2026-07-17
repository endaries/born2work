"""
Точка входу. Логіка навмисно тонка:
handlers лише координують Memory + ClaudeClient, вся "бізнес-логіка"
живе в тих двох модулях.
"""
import asyncio
import logging
import time
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings
from app.memory import Memory
from app.claude_client import ClaudeClient
from app.voice import VoiceTranscriber
from app.reminders import Reminders
from app.remind_parser import parse_remind

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

memory = Memory(settings.db_path)
claude = ClaudeClient(settings.anthropic_api_key)
transcriber = VoiceTranscriber(settings.openai_api_key) if settings.openai_api_key else None
reminders = Reminders(settings.db_path)

dp = Dispatcher()

# Заповнюється в main() перед стартом polling — потрібен, щоб розпізнавати
# згадки бота (@ім'я_бота) у групових чатах.
BOT_USERNAME: str | None = None


def is_allowed(user_id: int) -> bool:
    if not settings.allowed_user_ids:
        return True  # доступ не обмежено (лише для тестового етапу)
    return user_id in settings.allowed_user_ids


def is_group_chat(message: Message) -> bool:
    return message.chat.type in ("group", "supergroup")


def should_respond_in_group(message: Message) -> bool:
    """У групах бот відповідає лише якщо його явно покликали:
    згадали через @ім'я_бота або відповіли на його повідомлення.
    Інакше він мовчки читає далі, не втручаючись у кожну розмову.

    (Насправді Telegram у режимі Privacy Mode й так надсилає боту лише
    такі повідомлення — ця перевірка є додатковим запобіжником.)"""
    reply = message.reply_to_message
    if reply and reply.from_user and reply.from_user.is_bot:
        if BOT_USERNAME and reply.from_user.username == BOT_USERNAME:
            return True
    if message.text and BOT_USERNAME and f"@{BOT_USERNAME}" in message.text:
        return True
    return False


def strip_mention(text: str) -> str:
    if BOT_USERNAME:
        return text.replace(f"@{BOT_USERNAME}", "").strip()
    return text


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привіт! Я твій AI-асистент. Просто пиши мені, і я відповім.\n\n"
        "Команди:\n"
        "/remember <текст> — запам'ятати факт надовго\n"
        "/facts — показати, що я про тебе пам'ятаю\n"
        "/forget_all — очистити коротку історію цього чату\n\n"
        "Нагадування:\n"
        "/remind 30m Текст — нагадати через 30 хвилин\n"
        "/remind 2h Текст — через 2 години\n"
        "/remind 1d Текст — через 1 день\n"
        "/remind 17.07.2026 15:30 Текст — на конкретну дату й час\n"
        "/reminders — список активних нагадувань\n"
        "/cancel_reminder <номер> — скасувати нагадування"
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


@dp.message(Command("remind"))
async def cmd_remind(message: Message) -> None:
    if not is_allowed(message.from_user.id):
        return
    args = message.text.removeprefix("/remind").strip()
    parsed = parse_remind(args)
    if parsed is None:
        await message.answer(
            "Не розпізнав формат. Приклади:\n"
            "/remind 30m Подзвонити клієнту\n"
            "/remind 2h Забрати посилку\n"
            "/remind 17.07.2026 15:30 Зустріч"
        )
        return
    due_at, text = parsed
    if due_at <= time.time():
        await message.answer("Цей час вже минув — вкажи час у майбутньому.")
        return
    reminder_id = await reminders.add(message.chat.id, due_at, text)
    due_str = datetime.fromtimestamp(due_at).strftime("%d.%m.%Y %H:%M")
    await message.answer(f"Домовились, нагадаю {due_str} (№{reminder_id}): {text}")


@dp.message(Command("reminders"))
async def cmd_reminders(message: Message) -> None:
    if not is_allowed(message.from_user.id):
        return
    upcoming = await reminders.get_upcoming(message.chat.id)
    if not upcoming:
        await message.answer("Активних нагадувань немає.")
        return
    lines = []
    for r in upcoming:
        due_str = datetime.fromtimestamp(r["due_at"]).strftime("%d.%m.%Y %H:%M")
        lines.append(f"№{r['id']} — {due_str} — {r['text']}")
    await message.answer("Активні нагадування:\n" + "\n".join(lines))


@dp.message(Command("cancel_reminder"))
async def cmd_cancel_reminder(message: Message) -> None:
    if not is_allowed(message.from_user.id):
        return
    arg = message.text.removeprefix("/cancel_reminder").strip()
    if not arg.isdigit():
        await message.answer("Напиши так: /cancel_reminder 3 (номер із /reminders)")
        return
    removed = await reminders.cancel(message.chat.id, int(arg))
    if removed:
        await message.answer("Нагадування скасовано.")
    else:
        await message.answer("Не знайшов нагадування з таким номером у цьому чаті.")


async def generate_reply(chat_id: int, user_id: int, user_text: str) -> str:
    """Спільна логіка: зберегти повідомлення користувача, звернутись до Claude,
    зберегти й повернути відповідь. Використовується і текстовим, і голосовим
    обробниками, щоб не дублювати код."""
    await memory.add_message(chat_id, "user", user_text)

    history = await memory.get_history(chat_id)
    facts = await memory.get_facts(user_id)

    reply_text = await claude.reply(history, facts)

    await memory.add_message(chat_id, "assistant", reply_text)
    return reply_text


@dp.message(F.text)
async def handle_text(message: Message) -> None:
    if not is_allowed(message.from_user.id):
        if not is_group_chat(message):
            await message.answer("У тебе немає доступу до цього бота.")
        return

    if is_group_chat(message) and not should_respond_in_group(message):
        return  # у групі мовчимо, якщо нас не покликали

    user_text = strip_mention(message.text)

    try:
        reply_text = await generate_reply(message.chat.id, message.from_user.id, user_text)
    except Exception:
        logger.exception("Claude API call failed")
        await message.answer("Сталася помилка при зверненні до Claude. Спробуй ще раз.")
        return

    await message.answer(reply_text)


@dp.message(F.voice)
async def handle_voice(message: Message, bot: Bot) -> None:
    if not is_allowed(message.from_user.id):
        if not is_group_chat(message):
            await message.answer("У тебе немає доступу до цього бота.")
        return

    if is_group_chat(message) and not should_respond_in_group(message):
        return  # у групі реагуємо на голос лише якщо відповіли на повідомлення бота

    if transcriber is None:
        await message.answer(
            "Розшифровка голосу поки не налаштована (немає OPENAI_API_KEY)."
        )
        return

    try:
        file_info = await bot.get_file(message.voice.file_id)
        file_bytes_io = await bot.download_file(file_info.file_path)
        audio_bytes = file_bytes_io.read()
        recognized_text = await transcriber.transcribe(audio_bytes)
    except Exception:
        logger.exception("Voice transcription failed")
        await message.answer("Не вдалося розпізнати голосове повідомлення. Спробуй ще раз.")
        return

    if not recognized_text:
        await message.answer("Не почув нічого розбірливого в голосовому повідомленні.")
        return

    try:
        reply_text = await generate_reply(message.chat.id, message.from_user.id, recognized_text)
    except Exception:
        logger.exception("Claude API call failed")
        await message.answer("Сталася помилка при зверненні до Claude. Спробуй ще раз.")
        return

    await message.answer(f"🎤 Я почув: «{recognized_text}»\n\n{reply_text}")


REMINDER_CHECK_INTERVAL_SECONDS = 30


async def reminder_check_loop(bot: Bot) -> None:
    """Фоновий цикл: раз на REMINDER_CHECK_INTERVAL_SECONDS перевіряє, чи є
    прострочені нагадування, і надсилає їх у відповідний чат."""
    while True:
        try:
            due = await reminders.get_due(time.time())
            for r in due:
                try:
                    await bot.send_message(r["chat_id"], f"🔔 Нагадування: {r['text']}")
                except Exception:
                    logger.exception("Failed to send reminder %s", r["id"])
                await reminders.mark_sent(r["id"])
        except Exception:
            logger.exception("Reminder check loop failed")
        await asyncio.sleep(REMINDER_CHECK_INTERVAL_SECONDS)


async def main() -> None:
    global BOT_USERNAME
    settings.validate()
    await memory.init()
    await reminders.init()

    bot = Bot(token=settings.telegram_bot_token)
    me = await bot.get_me()
    BOT_USERNAME = me.username
    logger.info("Bot starting as @%s...", BOT_USERNAME)

    asyncio.create_task(reminder_check_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())