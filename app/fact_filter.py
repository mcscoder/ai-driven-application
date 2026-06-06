from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.schemas import RetrievedFact

LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def filter_facts_for_message(
    message: str, facts: list[RetrievedFact], now: datetime | None = None
) -> list[RetrievedFact]:
    target_date = _target_date(message, now)
    if target_date is None:
        return facts

    current = _local_now(now)
    dated_facts = [
        fact
        for fact in facts
        if fact.valid_at
        and _is_active_fact(fact, current)
        and _date_part(fact.valid_at) == target_date
    ]
    cancellations = [
        fact
        for fact in facts
        if fact.invalid_at
        and _date_part(fact.invalid_at) == target_date
        and _looks_like_cancellation(fact.fact)
    ]
    if not cancellations:
        return dated_facts

    return [
        fact
        for fact in dated_facts
        if not any(_cancels(cancel.fact, fact.fact) for cancel in cancellations)
    ]


def filter_active_facts(
    facts: list[RetrievedFact], now: datetime | None = None
) -> list[RetrievedFact]:
    current = _local_now(now)
    return [fact for fact in facts if _is_active_fact(fact, current)]


def filter_active_facts_for_date(
    facts: list[RetrievedFact], target_date: str | date, now: datetime | None = None
) -> list[RetrievedFact]:
    parsed_date = _parse_date(target_date)
    if parsed_date is None:
        return filter_active_facts(facts, now)

    current = _local_now(now)
    return [
        fact
        for fact in facts
        if fact.valid_at
        and _is_active_fact(fact, current)
        and _date_part(fact.valid_at) == parsed_date
    ]


def _target_date(message: str, now: datetime | None) -> date | None:
    normalized = message.lower()
    if "ngày mai" not in normalized and "mai" not in normalized:
        return None

    return (_local_now(now) + timedelta(days=1)).date()


def _local_now(now: datetime | None) -> datetime:
    current = now or datetime.now(LOCAL_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=LOCAL_TZ)
    return current.astimezone(LOCAL_TZ)


def _is_active_fact(fact: RetrievedFact, now: datetime) -> bool:
    if not fact.invalid_at:
        return True
    if _looks_like_cancellation(fact.fact):
        return False
    invalid_at = _datetime_part(fact.invalid_at)
    return bool(invalid_at and invalid_at > now)


def _parse_date(value: str | date) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _date_part(value: str) -> date | None:
    parsed = _datetime_part(value)
    return parsed.date() if parsed else None


def _datetime_part(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value).astimezone(LOCAL_TZ)
    except ValueError:
        return None


def _looks_like_cancellation(fact: str) -> bool:
    normalized = fact.lower()
    return any(marker in normalized for marker in ("không", "hủy", "huỷ", "cancel"))


def is_cancellation_message(message: str) -> bool:
    return _looks_like_cancellation(message)


def should_cancel_fact(
    message: str, fact: RetrievedFact, now: datetime | None = None
) -> bool:
    target_date = _target_date(message, now)
    if target_date is not None and (
        not fact.valid_at or _date_part(fact.valid_at) != target_date
    ):
        return False
    return _cancels(message, fact.fact)


def _cancels(cancel_fact: str, scheduled_fact: str) -> bool:
    cancel_tokens = _meaningful_tokens(cancel_fact)
    scheduled_tokens = _meaningful_tokens(scheduled_fact)
    return bool(cancel_tokens & scheduled_tokens)


def _meaningful_tokens(text: str) -> set[str]:
    stop_words = {"user", "tôi", "tao", "mình", "với", "lúc", "ngày", "mai", "không"}
    return {
        token
        for token in text.lower().replace(":", " ").replace(",", " ").split()
        if len(token) >= 3 and token not in stop_words
    }
