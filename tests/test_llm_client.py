import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from app.llm_client import AssistantClient
from app.memory_store import ConversationTurn, MemoryRecord


@dataclass
class FakeMemory:
    pins: list[MemoryRecord] = field(default_factory=list)
    turns: list[ConversationTurn] = field(default_factory=list)
    candidates: list[MemoryRecord] = field(default_factory=list)
    added_memories: list[dict[str, Any]] = field(default_factory=list)
    superseded: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    added_turns: list[tuple[str, str]] = field(default_factory=list)
    searches: list[list[str]] = field(default_factory=list)

    async def pin_memories(self) -> list[MemoryRecord]:
        return self.pins

    async def recent_turns(self) -> list[ConversationTurn]:
        return self.turns

    async def search(self, queries: list[str]) -> list[MemoryRecord]:
        self.searches.append(queries)
        return self.candidates

    async def add_memory(self, **kwargs) -> MemoryRecord:
        self.added_memories.append(kwargs)
        return _memory(
            "new-memory",
            kwargs["text"],
            memory_type=kwargs["memory_type"],
        )

    async def supersede_memory(self, memory_id: str, **kwargs) -> MemoryRecord | None:
        if memory_id == "missing":
            return None
        self.superseded.append((memory_id, kwargs))
        return _memory(
            "replacement",
            kwargs["replacement_text"],
            memory_type=kwargs["memory_type"],
        )

    async def delete_memory(self, memory_id: str) -> bool:
        if memory_id == "missing":
            return False
        self.deleted.append(memory_id)
        return True

    async def add_turn(self, role: str, content: str) -> None:
        self.added_turns.append((role, content))


def test_no_memory_plan_skips_search_and_persists_turns() -> None:
    client, requests = _client_for_responses(
        [
            _gemini_json({"needs_memory": False, "queries": [], "reason": "general"}),
            _gemini_text("2 + 2 = 4."),
            _gemini_json({"operations": []}),
        ]
    )
    memory = FakeMemory()

    result = asyncio.run(client.reply("2 + 2 bằng mấy?", memory))  # type: ignore[arg-type]

    assert result.reply == "2 + 2 = 4."
    assert result.retrieved_facts == []
    assert memory.searches == []
    assert memory.added_turns == [
        ("user", "2 + 2 bằng mấy?"),
        ("assistant", "2 + 2 = 4."),
    ]
    assert [trace.name for trace in result.tool_trace] == [
        "memory_planner",
        "memory_search",
        "memory_selector",
        "memory_curator",
    ]
    assert "responseSchema" in requests[0]["generationConfig"]
    assert "responseSchema" not in requests[1]["generationConfig"]


def test_memory_pipeline_searches_selects_and_answers_from_selected_memory() -> None:
    client, _ = _client_for_responses(
        [
            _gemini_json(
                {
                    "needs_memory": True,
                    "queries": ["gu uống cà phê khi code"],
                    "reason": "asks remembered preference",
                }
            ),
            _gemini_json(
                {
                    "selected_ids": ["mem-1"],
                    "rejected_ids": ["mem-2"],
                    "reason": "mem-1 answers the drink preference",
                }
            ),
            _gemini_text("Ông hợp cà phê đen không đường hơn."),
            _gemini_json({"operations": []}),
        ]
    )
    memory = FakeMemory(
        candidates=[
            _memory("mem-1", "Người dùng thường uống cà phê đen không đường."),
            _memory("mem-2", "Người dùng thích quán yên tĩnh."),
        ]
    )

    result = asyncio.run(client.reply("lúc code thì mua nước gì hợp gu tôi?", memory))  # type: ignore[arg-type]

    assert memory.searches == [["gu uống cà phê khi code"]]
    assert [fact.fact for fact in result.retrieved_facts] == [
        "Người dùng thường uống cà phê đen không đường."
    ]
    assert result.tool_trace[2].arguments["selected_count"] == 1
    assert result.tool_trace[2].arguments["rejected_count"] == 1
    assert result.tool_trace[2].arguments["selected_ids"] == ["mem-1"]
    assert result.tool_trace[2].arguments["rejected_ids"] == ["mem-2"]


def test_pin_memories_are_supplied_without_keyword_pinning() -> None:
    client, requests = _client_for_responses(
        [
            _gemini_json({"needs_memory": False, "queries": [], "reason": "current turn"}),
            _gemini_text("Ok ông, tôi sẽ nói ngắn."),
            _gemini_json({"operations": []}),
        ]
    )
    memory = FakeMemory(
        pins=[
            _memory(
                "style-1",
                "Người dùng muốn được gọi là ông và muốn câu trả lời ngắn.",
                memory_type="pin",
            )
        ]
    )

    result = asyncio.run(client.reply("nhắc tôi đang hỏi gì", memory))  # type: ignore[arg-type]

    prompt = requests[1]["contents"][0]["parts"][0]["text"]
    assert "Pinned memories:" in prompt
    assert "Người dùng muốn được gọi là ông" in prompt
    assert result.reply == "Ok ông, tôi sẽ nói ngắn."


def test_curator_create_and_invalid_operations_are_traced() -> None:
    client, _ = _client_for_responses(
        [
            _gemini_json({"needs_memory": False, "queries": [], "reason": "new durable fact"}),
            _gemini_text("Tôi nhớ rồi."),
            _gemini_json(
                {
                    "operations": [
                        {
                            "op": "create",
                            "text": "Người dùng không thích bị khen sáo rỗng.",
                            "memory_type": "long_term",
                            "replaces_id": None,
                        },
                        {
                            "op": "delete",
                            "text": "",
                            "memory_type": "long_term",
                            "replaces_id": "missing",
                        },
                    ]
                }
            ),
        ]
    )
    memory = FakeMemory()

    result = asyncio.run(client.reply("Tui không thích bị khen sáo rỗng.", memory))  # type: ignore[arg-type]

    assert memory.added_memories[0]["text"] == "Người dùng không thích bị khen sáo rỗng."
    assert result.tool_trace[-1].result == "applied 1 operation(s), skipped 1"


def test_curator_supersedes_existing_memory_by_id() -> None:
    client, _ = _client_for_responses(
        [
            _gemini_json(
                {
                    "needs_memory": True,
                    "queries": ["sở thích đồ uống hiện tại"],
                    "reason": "possible correction",
                }
            ),
            _gemini_json(
                {
                    "selected_ids": ["drink-1"],
                    "rejected_ids": [],
                    "reason": "old drink preference may be corrected",
                }
            ),
            _gemini_text("Đã cập nhật."),
            _gemini_json(
                {
                    "operations": [
                        {
                            "op": "supersede",
                            "text": "Người dùng giờ thích uống trà nóng khi code.",
                            "memory_type": "long_term",
                            "replaces_id": "drink-1",
                        }
                    ]
                }
            ),
        ]
    )
    memory = FakeMemory(
        candidates=[_memory("drink-1", "Người dùng thích cà phê đen khi code.")]
    )

    asyncio.run(client.reply("Giờ lúc code tui đổi sang uống trà nóng.", memory))  # type: ignore[arg-type]

    assert memory.superseded == [
        (
            "drink-1",
            {
                "replacement_text": "Người dùng giờ thích uống trà nóng khi code.",
                "memory_type": "long_term",
                "source_message": "Giờ lúc code tui đổi sang uống trà nóng.",
            },
        )
    ]


def test_answer_generation_failure_returns_safe_reply_and_trace() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "responseSchema" in body["generationConfig"]:
            return httpx.Response(
                200,
                json=_gemini_json(
                    {"needs_memory": False, "queries": [], "reason": "general"}
                ),
            )
        return httpx.Response(429, json={"error": "rate limited"})

    client = AssistantClient(
        base_url="http://testserver/v1",
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
        now_factory=lambda: datetime.fromisoformat("2026-06-06T12:00:00+07:00"),
    )
    memory = FakeMemory()

    result = asyncio.run(client.reply("2 + 2 bằng mấy?", memory))  # type: ignore[arg-type]

    assert "chưa gọi được mô hình" in result.reply
    assert result.tool_trace[-2].name == "answer_generation"
    assert memory.added_turns == [
        ("user", "2 + 2 bằng mấy?"),
        ("assistant", result.reply),
    ]


def test_runtime_no_longer_contains_legacy_broad_query_strings() -> None:
    from pathlib import Path

    source = Path("app/llm_client.py").read_text(encoding="utf-8")
    forbidden = [
        "điều user không thích",
        "ăn uống món ăn đồ uống cà phê rau mùi",
        "MemoryKind",
        "project_context",
        "apply_scope",
        "_looks_like_memory_question",
        "search_companion_memories",
    ]

    for text in forbidden:
        assert text not in source


def _client_for_responses(
    responses: list[dict[str, Any]],
) -> tuple[AssistantClient, list[dict[str, Any]]]:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=responses.pop(0))

    client = AssistantClient(
        base_url="http://testserver/v1",
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
        now_factory=lambda: datetime.fromisoformat("2026-06-06T12:00:00+07:00"),
    )
    return client, requests


def _memory(
    memory_id: str,
    text: str,
    *,
    memory_type: str = "long_term",
    score: float | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        id=memory_id,
        text=text,
        memory_type=memory_type,
        status="active",
        source_message=None,
        created_at="2026-06-06T12:00:00+07:00",
        updated_at="2026-06-06T12:00:00+07:00",
        valid_at=None,
        invalid_at=None,
        score=score,
    )


def _gemini_json(value: dict[str, Any]) -> dict[str, Any]:
    return _gemini_text(json.dumps(value, ensure_ascii=False))


def _gemini_text(text: str) -> dict[str, Any]:
    return {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": text}]}}
        ]
    }
