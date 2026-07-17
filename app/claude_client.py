"""
Тонка обгортка над Anthropic API.
Формує системний промпт з довгострокових фактів + короткострокову історію
і повертає текстову відповідь.
"""
from anthropic import AsyncAnthropic

MODEL = "claude-sonnet-4-5"  # можна змінити на іншу модель пізніше
MAX_TOKENS = 1024

BASE_SYSTEM_PROMPT = """Ти — персональний AI-асистент користувача в Telegram.
Відповідай стисло, по суті, українською мовою (якщо користувач не пише іншою).
У тебе є доступ до веб-пошуку — використовуй його, коли питання стосується
поточних подій, погоди, новин, курсів валют чи будь-якої інформації,
яка могла змінитись після твого навчання.
Якщо в повідомленні користувача є стійкий факт про нього самого, його задачі
чи домовленості, які варто запам'ятати надовго — просто дай звичайну відповідь;
збереження фактів обробляється окремо командою користувача, не намагайся
сам вирішувати, що зберігати."""


class ClaudeClient:
    def __init__(self, api_key: str):
        self.client = AsyncAnthropic(api_key=api_key)

    def _build_system_prompt(self, facts: list[str]) -> str:
        if not facts:
            return BASE_SYSTEM_PROMPT
        facts_block = "\n".join(f"- {f}" for f in facts)
        return f"{BASE_SYSTEM_PROMPT}\n\nВідомі факти про користувача:\n{facts_block}"

    async def reply(self, history: list[dict], facts: list[str]) -> str:
        system_prompt = self._build_system_prompt(facts)
        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=history,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
        )
        text_parts = [block.text for block in response.content if block.type == "text"]
        return "\n".join(text_parts).strip()
