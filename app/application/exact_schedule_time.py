"""App-local dispatch times, never remote scheduling or a publishing grant."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def timing(due_at, timezone_name, *, now):
    if due_at is None or not timezone_name or due_at.tzinfo is None:
        raise ValueError('يلزم موعد صريح ومنطقة زمنية صالحة.')
    try:zone = ZoneInfo(timezone_name)
    except (KeyError,ValueError):raise ValueError('منطقة زمنية غير صالحة.') from None
    due = due_at.astimezone(timezone.utc)
    if due <= now or due > now + timedelta(days=7):
        raise ValueError('اختر موعداً مستقبلياً خلال سبعة أيام.')
    return dict(due_at=due.isoformat(), timezone=timezone_name,
                local_time=due.astimezone(zone).isoformat())
