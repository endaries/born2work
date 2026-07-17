"""
Централізована конфігурація.
Все, що читається з .env, проходить тільки через цей файл —
решта коду ніколи напряму не працює з os.environ.
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _parse_allowed_ids(raw: str) -> set[int]:
    if not raw:
        return set()
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    db_path: str = os.getenv("DB_PATH", "data/assistant.db")
    allowed_user_ids: set[int] = field(
        default_factory=lambda: _parse_allowed_ids(os.getenv("ALLOWED_USER_IDS", ""))
    )

    def validate(self) -> None:
        missing = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if missing:
            raise RuntimeError(
                f"Відсутні обов'язкові змінні оточення: {', '.join(missing)}. "
                f"Заповни .env (див. .env.example)."
            )


settings = Settings()
