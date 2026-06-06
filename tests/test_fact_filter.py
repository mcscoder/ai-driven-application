from datetime import datetime

from app.fact_filter import filter_facts_for_message
from app.schemas import RetrievedFact


def test_tomorrow_filter_keeps_only_target_date() -> None:
    facts = [
        RetrievedFact(
            fact="user có lịch chơi game với anh Tú lúc 3h chiều ngày 2026-06-07",
            valid_at="2026-06-07T15:00:00+00:00",
        ),
        RetrievedFact(
            fact="user có lịch thi môn toán lúc 7 giờ sáng",
            valid_at="2026-06-08T07:00:00+00:00",
        ),
    ]

    filtered = filter_facts_for_message(
        "ngày mai tôi có lịch gì không?",
        facts,
        now=datetime.fromisoformat("2026-06-06T12:00:00+07:00"),
    )

    assert [fact.fact for fact in filtered] == [
        "user có lịch chơi game với anh Tú lúc 3h chiều ngày 2026-06-07"
    ]


def test_tomorrow_filter_removes_canceled_schedule() -> None:
    facts = [
        RetrievedFact(
            fact="user có lịch chơi game với anh Tú lúc 3h chiều ngày 2026-06-07",
            valid_at="2026-06-07T15:00:00+00:00",
        ),
        RetrievedFact(
            fact="user không đi chơi game với anh Tú",
            invalid_at="2026-06-07T00:00:00+00:00",
        ),
    ]

    filtered = filter_facts_for_message(
        "ngày mai tôi có lịch gì không?",
        facts,
        now=datetime.fromisoformat("2026-06-06T12:00:00+07:00"),
    )

    assert filtered == []


def test_tomorrow_filter_hides_invalidated_schedule() -> None:
    facts = [
        RetrievedFact(
            fact="user có lịch chơi game với anh Tú lúc 3h chiều ngày 2026-06-07",
            valid_at="2026-06-07T15:00:00+00:00",
            invalid_at="2026-06-06T04:00:00+00:00",
        )
    ]

    filtered = filter_facts_for_message(
        "ngày mai tôi có lịch gì không?",
        facts,
        now=datetime.fromisoformat("2026-06-06T12:00:00+07:00"),
    )

    assert filtered == []


def test_tomorrow_filter_keeps_schedule_with_future_expiry() -> None:
    facts = [
        RetrievedFact(
            fact="user có lịch chơi game với anh Tú lúc 3h chiều ngày 2026-06-07",
            valid_at="2026-06-07T15:00:00+00:00",
            invalid_at="2026-06-07T16:00:00+00:00",
        )
    ]

    filtered = filter_facts_for_message(
        "ngày mai tôi có lịch gì không?",
        facts,
        now=datetime.fromisoformat("2026-06-06T12:00:00+07:00"),
    )

    assert [fact.fact for fact in filtered] == [
        "user có lịch chơi game với anh Tú lúc 3h chiều ngày 2026-06-07"
    ]
