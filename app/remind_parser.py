"""
Розбір аргументів команди /remind.

Підтримує два формати:
1. Відносний: "30m текст", "2h текст", "1d текст"
   (m = хвилини, h = години, d = дні від поточного моменту)
2. Абсолютний: "17.07.2026 15:30 текст"

Повертає (unix_timestamp, текст) або None, якщо формат не розпізнано.
"""
import re
import time
from datetime import datetime

RELATIVE_RE = re.compile(r"^(\d+)([mhd])\s+(.+)$", re.DOTALL)
ABSOLUTE_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s+(.+)$", re.DOTALL)

UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}


def parse_remind(args: str) -> tuple[float, str] | None:
    args = args.strip()
    if not args:
        return None

    m = RELATIVE_RE.match(args)
    if m:
        amount, unit, text = m.groups()
        due_at = time.time() + int(amount) * UNIT_SECONDS[unit]
        return due_at, text.strip()

    m = ABSOLUTE_RE.match(args)
    if m:
        date_str, time_str, text = m.groups()
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        except ValueError:
            return None
        return dt.timestamp(), text.strip()

    return None