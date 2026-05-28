import logging
from datetime import datetime, timezone, timedelta

EST = timezone(timedelta(hours=-5))
logger = logging.getLogger(__name__)


def now_est() -> datetime:
    return datetime.now(EST)


def format_est(dt: datetime = None) -> str:
    if dt is None:
        dt = now_est()
    return dt.strftime("%Y-%m-%d %I:%M %p EST")
