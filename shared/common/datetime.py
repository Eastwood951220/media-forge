from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")


def now() -> datetime:
    """Return current datetime in Asia/Shanghai timezone."""
    return datetime.now(tz=TZ)
