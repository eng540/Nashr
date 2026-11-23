"""Allowlisted native Telegram content. Never accepts a method or destination."""
import math


def native_payload(value):
    if not isinstance(value, dict):
        raise ValueError("Native Telegram content must be an object.")
    kind = value.get("type")
    fields = {
        "POLL": {"type", "question", "options", "allows_multiple_answers"},
        "LOCATION": {"type", "latitude", "longitude"},
        "LIVE_LOCATION": {"type", "latitude", "longitude", "live_period"},
        "VENUE": {"type", "latitude", "longitude", "title", "address"},
        "CONTACT": {"type", "phone_number", "first_name", "last_name"},
        "DICE": {"type", "emoji"},
    }
    if not isinstance(kind, str) or kind not in fields or set(value) - fields[kind]:
        raise ValueError("Unsupported native content type or fields.")
    data = {k: v for k, v in value.items() if k != "type"}
    if kind in {"LOCATION", "LIVE_LOCATION", "VENUE"}:
        for field, limit in [("latitude", 90), ("longitude", 180)]:
            v = data.get(field)
            if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not -limit <= v <= limit:
                raise ValueError("Invalid map coordinates.")
    for key, limit in {"title": 256, "address": 256, "first_name": 64, "last_name": 64, "phone_number": 32}.items():
        required = (kind == "VENUE" and key in {"title", "address"}) or (kind == "CONTACT" and key in {"first_name", "phone_number"})
        if key in data or required:
            if not isinstance(data.get(key), str) or not data[key].strip() or len(data[key]) > limit:
                raise ValueError("Invalid native text field.")
    if kind == "LIVE_LOCATION":
        period = data.get("live_period")
        if isinstance(period, bool) or not isinstance(period, int) or not 60 <= period <= 86400:
            raise ValueError("Live location duration must be60to86400seconds.")
    if kind == "POLL":
        if not isinstance(data.get("question"), str) or not 1 <= len(data["question"]) <= 300:
            raise ValueError("Poll question must contain1to300characters.")
        options = data.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= 12 or any(not isinstance(o, str) or not 1 <= len(o) <= 100 for o in options):
            raise ValueError("Poll must have2to12text options up to100characters.")
        if "allows_multiple_answers" in data and not isinstance(data["allows_multiple_answers"], bool):
            raise ValueError("Multiple answers must be true or false.")
        data["options"] = [{"text": o} for o in options]
        data.update(type="regular", is_anonymous=True)
    if kind == "DICE" and (not isinstance(data.get("emoji", "🎲"), str) or data.get("emoji", "🎲") not in {"🎲", "🎯", "🏀", "⚽", "🎳", "🎰"}):
        raise ValueError("Unsupported dice emoji.")
    method = {"POLL": "sendPoll", "LOCATION": "sendLocation", "LIVE_LOCATION": "sendLocation", "VENUE": "sendVenue", "CONTACT": "sendContact", "DICE": "sendDice"}[kind]
    return method, data
