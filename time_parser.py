# encoding:utf-8

import re
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

_WEEKDAY_MAP = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}

_TIME_DEFAULTS = {
    "上午": 9,
    "中午": 12,
    "下午": 15,
    "晚上": 20,
    "今晚": 20,
    "今夜": 20,
}

_PATTERNS = [
    (
        "monthday",
        re.compile(
            r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日(?P<before>前|之前)?(?P<tod>中午|下午|晚上|上午)?(?P<time>(\d{1,2}[:：]\d{2}|\d{1,2}点半|\d{1,2}点)?)"
        ),
    ),
    (
        "weekday",
        re.compile(
            r"周(?P<weekday>[一二三四五六日天])(?P<before>前|之前)?(?P<tod>中午|下午|晚上|上午)?(?P<time>(\d{1,2}[:：]\d{2}|\d{1,2}点半|\d{1,2}点)?)"
        ),
    ),
    (
        "relative_day",
        re.compile(
            r"(?P<day>今天|明天|后天)(?P<before>前|之前)?(?P<tod>中午|下午|晚上|上午)?(?P<time>(\d{1,2}[:：]\d{2}|\d{1,2}点半|\d{1,2}点)?)"
        ),
    ),
    (
        "tonight",
        re.compile(r"(今晚|今夜)"),
    ),
    (
        "tod_only",
        re.compile(r"(?P<tod>中午|下午|晚上|上午)(?P<time>(\d{1,2}[:：]\d{2}|\d{1,2}点半|\d{1,2}点)?)"),
    ),
    (
        "time_only",
        re.compile(r"(?P<time>\d{1,2}[:：]\d{2}|\d{1,2}点半|\d{1,2}点)"),
    ),
]


def parse_due_text(text: str, tz_name: str = "Asia/Shanghai", now: datetime = None):
    if not text:
        return None, None, None, None

    tz = _get_timezone(tz_name)
    now = now or datetime.now(tz)

    matched = _find_match(text)
    if not matched:
        return None, None, None, None

    kind, match = matched
    due_text = match.group(0)
    start, end = match.span()

    info = _build_info(kind, match)
    due_at = _build_due_datetime(info, now, tz)
    due_at_iso = due_at.isoformat() if due_at else None

    return due_text, due_at_iso, start, end


def _get_timezone(tz_name: str):
    if ZoneInfo:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    return datetime.now().astimezone().tzinfo


def _find_match(text: str):
    candidates = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            if not match.group(0).strip():
                continue
            candidates.append((match.start(), -len(match.group(0)), kind, match))

    if not candidates:
        return None

    candidates.sort()
    _, _, kind, match = candidates[0]
    return kind, match


def _build_info(kind: str, match: re.Match):
    info = {
        "kind": kind,
        "day": match.groupdict().get("day"),
        "weekday": match.groupdict().get("weekday"),
        "month": match.groupdict().get("month"),
        "date_day": match.groupdict().get("day") if kind == "monthday" else None,
        "before": match.groupdict().get("before"),
        "tod": match.groupdict().get("tod"),
        "time": match.groupdict().get("time"),
    }
    if kind == "tonight":
        info["tod"] = "晚上"
    return info


def _build_due_datetime(info: dict, now: datetime, tz):
    base_date = None
    adjust_next_day = False

    if info["kind"] == "relative_day":
        offset = 0
        if info["day"] == "明天":
            offset = 1
        elif info["day"] == "后天":
            offset = 2
        base_date = now.date() + timedelta(days=offset)
    elif info["kind"] == "weekday":
        weekday_key = info.get("weekday")
        if weekday_key in _WEEKDAY_MAP:
            target = _WEEKDAY_MAP[weekday_key]
            delta = (target - now.weekday()) % 7
            base_date = now.date() + timedelta(days=delta)
    elif info["kind"] == "monthday":
        try:
            month = int(info.get("month"))
            day = int(info.get("date_day"))
        except Exception:
            month, day = None, None
        if month and day:
            year = now.year
            try_date = datetime(year, month, day, tzinfo=tz).date()
            if try_date < now.date():
                year += 1
            base_date = datetime(year, month, day, tzinfo=tz).date()
    elif info["kind"] == "tonight":
        base_date = now.date()
    elif info["kind"] in ("tod_only", "time_only"):
        base_date = now.date()
        adjust_next_day = True

    hour, minute = _parse_time(info.get("time"), info.get("tod"))

    if base_date is None:
        return None

    if hour is None:
        if info.get("tod") in _TIME_DEFAULTS:
            hour = _TIME_DEFAULTS[info.get("tod")]
            minute = 0
        else:
            hour = 23
            minute = 59

    due_at = datetime(
        base_date.year,
        base_date.month,
        base_date.day,
        hour,
        minute,
        tzinfo=tz,
    )

    if adjust_next_day and due_at <= now:
        due_at = due_at + timedelta(days=1)

    return due_at


def _parse_time(time_text: str, tod: str):
    if not time_text:
        return None, None

    text = time_text.replace("：", ":")
    hour = None
    minute = 0

    if ":" in text:
        try:
            parts = text.split(":", 1)
            hour = int(parts[0])
            minute = int(parts[1])
        except Exception:
            return None, None
    elif text.endswith("点半"):
        try:
            hour = int(text.replace("点半", ""))
            minute = 30
        except Exception:
            return None, None
    elif text.endswith("点"):
        try:
            hour = int(text.replace("点", ""))
            minute = 0
        except Exception:
            return None, None

    if hour is None:
        return None, None

    if tod in ("下午", "晚上") and hour < 12:
        hour += 12
    if tod == "中午" and hour < 12:
        hour += 12

    return hour, minute
