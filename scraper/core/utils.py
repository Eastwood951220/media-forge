import re
from typing import Any


def clean_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def parse_size(text: str) -> float:
    if not text:
        return 0.0

    match = re.search(r"([\d.]+)\s*(GB|MB|KB)", text, re.IGNORECASE)
    if not match:
        return 0.0

    value, unit = float(match.group(1)), match.group(2).upper()
    return {"GB": value * 1024, "MB": value, "KB": value / 1024}.get(unit, 0.0)
