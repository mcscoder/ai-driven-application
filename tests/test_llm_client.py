import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.llm_client import AssistantClient, build_tool_declarations
from app.schemas import RetrievedFact


@dataclass
class FakeEdge:
    uuid: str
    fact: str
    valid_at: str | None = None
    invalid_at: str | None = None


class FakeMemory:
    def __getattribute__(self, name: str) -> Any:
        manual_methods = {
            "add_manual_fact",
            "manual_facts_for_date",
            "invalidate_matching_manual_facts",
        }
        if name in manual_methods and not object.__getattribute__(
            self, "enable_manual"
        ):
            raise AttributeError(name)
        return object.__getattribute__(self, name)

    def __init__(
        self,
        edges: list[FakeEdge] | None = None,
        edges_by_query: dict[str, list[FakeEdge]] | None = None,
        companion_by_query: dict[str, list[RetrievedFact]] | None = None,
        pinned_facts: list[RetrievedFact] | None = None,
        enable_manual: bool = True,
    ):
        self.edges = edges or []
        self.edges_by_query = edges_by_query or {}
        self.companion_by_query = companion_by_query or {}
        self.pinned_facts = pinned_facts or []
        self.enable_manual = enable_manual
        self.searches: list[str] = []
        self.companion_searches: list[str] = []
        self.user_messages: list[str] = []
        self.memory_facts: list[str] = []
        self.manual_facts: list[tuple[str, datetime | None]] = []
        self.invalidations: list[tuple[str, list[FakeEdge]]] = []
        self.manual_invalidations: list[tuple[str, str | None]] = []

    async def search_edges(self, message: str) -> list[FakeEdge]:
        self.searches.append(message)
        if self.edges_by_query:
            return self.edges_by_query.get(message, [])
        return self.edges

    def edges_to_facts(self, edges: list[FakeEdge]) -> list[RetrievedFact]:
        return [
            RetrievedFact(
                fact=edge.fact,
                valid_at=edge.valid_at,
                invalid_at=edge.invalid_at,
            )
            for edge in edges
        ]

    async def add_user_message(self, message: str) -> None:
        self.user_messages.append(message)

    async def add_memory_fact(self, memory_text: str) -> None:
        self.memory_facts.append(memory_text)

    async def pinned_memories(self) -> list[RetrievedFact]:
        return self.pinned_facts

    async def search_companion_memories(
        self, query: str
    ) -> list[RetrievedFact]:
        self.companion_searches.append(query)
        return self.companion_by_query.get(query, [])

    async def add_manual_fact(
        self, fact: str, valid_at: datetime | None
    ) -> None:
        self.manual_facts.append((fact, valid_at))

    async def manual_facts_for_date(self, target_date: str) -> list[RetrievedFact]:
        facts = []
        for fact, valid_at in self.manual_facts:
            if valid_at and valid_at.date().isoformat() == target_date:
                facts.append(
                    RetrievedFact(
                        fact=fact,
                        valid_at=valid_at.isoformat(),
                    )
                )
        return facts

    async def invalidate_matching_facts(
        self, message: str, edges: list[FakeEdge]
    ) -> int:
        self.invalidations.append((message, edges))
        return len(edges)

    async def invalidate_matching_manual_facts(
        self, message: str, target_date: str | None
    ) -> int:
        self.manual_invalidations.append((message, target_date))
        return 0


def test_write_mode_controls_available_write_tools() -> None:
    assert _tool_names("exact") == {
        "search_memory",
        "cancel_matching_facts",
        "remember_current_message",
    }
    assert _tool_names("model") == {
        "search_memory",
        "cancel_matching_facts",
        "remember_fact",
    }
    assert _tool_names("both") == {
        "search_memory",
        "cancel_matching_facts",
        "remember_current_message",
        "remember_fact",
    }


def test_exact_write_tool_saves_current_message_before_reply() -> None:
    message = "xin chao, chieu 2 gio ngay mai toi di choi game voi anh Tu"
    client, requests = _client_for_responses(
        [
            _gemini_call("remember_current_message", {}),
            _gemini_text("Da luu lich choi game cua ban."),
        ],
        memory_write_mode="exact",
    )
    memory = FakeMemory()

    result = asyncio.run(client.reply(message, memory))

    assert memory.user_messages == [message]
    assert result.reply == "Da luu lich choi game cua ban."
    assert [(item.name, item.result) for item in result.tool_trace] == [
        ("remember_current_message", "saved current user message")
    ]
    function_response = requests[1]["contents"][-1]["parts"][0]["functionResponse"]
    assert function_response["name"] == "remember_current_message"
    assert function_response["response"]["saved"] is True


def test_model_write_tool_saves_temporal_memory_as_current_message_in_both_mode() -> None:
    message = "xin chao, chieu 2 gio ngay mai toi di choi game voi anh Tu"
    client, _ = _client_for_responses(
        [
            _gemini_call(
                "remember_fact",
                {
                    "memory_text": (
                        "Chieu 2 gio ngay 2026-06-07, toi di choi game voi anh Tu."
                    )
                },
            ),
            _gemini_text("Da luu lich choi game cua ban."),
        ],
        memory_write_mode="both",
    )
    memory = FakeMemory()

    result = asyncio.run(client.reply(message, memory))

    assert memory.user_messages == []
    assert memory.memory_facts == []
    assert memory.manual_facts == [
        (
            "Chieu 2 gio ngay 2026-06-07, toi di choi game voi anh Tu.",
            datetime.fromisoformat("2026-06-07T14:00:00+07:00"),
        )
    ]
    assert result.tool_trace[0].result == "saved manual temporal memory"


def test_search_memory_filters_active_facts_by_requested_date() -> None:
    client, _ = _client_for_responses(
        [
            _gemini_call(
                "search_memory",
                {"query": "lich ngay mai", "date": "2026-06-07"},
            ),
            _gemini_text("Chieu mai ban di choi game voi anh Tu luc 2 gio."),
        ]
    )
    target_edge = FakeEdge(
        uuid="edge-1",
        fact="user co lich choi game voi anh Tu luc 2 gio chieu",
        valid_at="2026-06-07T07:00:00+00:00",
    )
    memory = FakeMemory(
        enable_manual=False,
        edges_by_query={
            "lich ngay mai 2026-06-07": [
                target_edge,
                FakeEdge(
                    uuid="edge-2",
                    fact="user co lich thi mon toan",
                    valid_at="2026-06-08T00:00:00+00:00",
                ),
                FakeEdge(
                    uuid="edge-3",
                    fact="user co lich an toi",
                    valid_at="2026-06-07T12:00:00+00:00",
                    invalid_at="2026-06-06T04:00:00+00:00",
                ),
            ],
            "ngay mai toi co can lam gi khong? 2026-06-07": [target_edge],
        }
    )

    result = asyncio.run(client.reply("ngay mai toi co can lam gi khong?", memory))

    assert memory.searches == [
        "lich ngay mai",
        "lich ngay mai 2026-06-07",
        "ngay mai toi co can lam gi khong? 2026-06-07",
        "lịch trình sự kiện kế hoạch ngày 2026-06-07",
    ]
    assert [fact.fact for fact in result.retrieved_facts] == [
        "user co lich choi game voi anh Tu luc 2 gio chieu"
    ]
    assert result.tool_trace[0].result == "retrieved 1 active fact(s)"


def test_search_memory_uses_manual_facts_for_dated_recall() -> None:
    client, _ = _client_for_responses(
        [
            _gemini_call(
                "search_memory",
                {"query": "lich ngay mai", "date": "2026-06-07"},
            ),
            _gemini_text("Chieu mai ban di choi game voi anh Tu luc 2 gio."),
        ]
    )
    memory = FakeMemory()
    memory.manual_facts.append(
        (
            "Chieu 2 gio ngay 2026-06-07, toi di choi game voi anh Tu.",
            datetime.fromisoformat("2026-06-07T14:00:00+07:00"),
        )
    )

    result = asyncio.run(client.reply("ngay mai toi co can lam gi khong?", memory))

    assert memory.searches == []
    assert [fact.fact for fact in result.retrieved_facts] == [
        "Chieu 2 gio ngay 2026-06-07, toi di choi game voi anh Tu."
    ]


def test_pinned_memories_are_injected_into_first_model_prompt() -> None:
    client, requests = _client_for_responses(
        [_gemini_text("Ok ông, tôi sẽ trả lời ngắn.")]
    )
    memory = FakeMemory(
        pinned_facts=[
            RetrievedFact(fact="Người dùng muốn được gọi là ông."),
            RetrievedFact(fact="Người dùng muốn câu trả lời ngắn, ý chính trước."),
        ]
    )

    result = asyncio.run(client.reply("nhắc tôi đang hỏi gì", memory))

    first_prompt = requests[0]["contents"][0]["parts"][0]["text"]
    assert "Always relevant user memory:" in first_prompt
    assert "Người dùng muốn được gọi là ông." in first_prompt
    assert "User message:\nnhắc tôi đang hỏi gì" in first_prompt
    assert result.reply == "Ok ông, tôi sẽ trả lời ngắn."


def test_search_memory_merges_graphiti_and_companion_results() -> None:
    client, _ = _client_for_responses(
        [
            _gemini_call("search_memory", {"query": "ca phe"}),
            _gemini_text("Bạn thích cà phê đen và quán yên tĩnh."),
        ]
    )
    memory = FakeMemory(
        edges=[FakeEdge(uuid="edge-1", fact="Người dùng thích cà phê đen.")],
        companion_by_query={
            "ca phe": [RetrievedFact(fact="Người dùng thích quán cafe yên tĩnh.")]
        },
    )

    result = asyncio.run(client.reply("tôi thích kiểu cafe nào?", memory))

    assert [fact.fact for fact in result.retrieved_facts] == [
        "Người dùng thích cà phê đen.",
        "Người dùng thích quán cafe yên tĩnh.",
    ]


def test_search_memory_broad_fallback_finds_stored_preference() -> None:
    client, _ = _client_for_responses(
        [
            _gemini_call("search_memory", {"query": "phở"}),
            _gemini_text("Nhớ dặn không rau mùi."),
        ]
    )
    memory = FakeMemory(
        companion_by_query={
            "điều user không thích": [
                RetrievedFact(fact="Người dùng không ăn rau mùi.")
            ]
        }
    )

    result = asyncio.run(client.reply("tui ăn phở thì cần nhớ gì?", memory))

    assert "điều user không thích" in memory.companion_searches
    assert [fact.fact for fact in result.retrieved_facts] == [
        "Người dùng không ăn rau mùi."
    ]


def test_non_pinned_memories_are_not_injected_without_search() -> None:
    client, requests = _client_for_responses([_gemini_text("2 + 2 = 4.")])
    memory = FakeMemory(
        companion_by_query={
            "anything": [RetrievedFact(fact="Người dùng thích cà phê đen.")]
        }
    )

    result = asyncio.run(client.reply("2 + 2 bằng mấy?", memory))

    first_prompt = requests[0]["contents"][0]["parts"][0]["text"]
    assert "Always relevant user memory:" not in first_prompt
    assert "Người dùng thích cà phê đen." not in first_prompt
    assert result.retrieved_facts == []


def test_cancel_matching_facts_invalidates_active_dated_edges() -> None:
    client, _ = _client_for_responses(
        [
            _gemini_call(
                "cancel_matching_facts",
                {"query": "choi game voi anh Tu", "date": "2026-06-07"},
            ),
            _gemini_text("Da huy lich choi game ngay mai."),
        ]
    )
    edge = FakeEdge(
        uuid="edge-1",
        fact="user co lich choi game voi anh Tu luc 2 gio chieu",
        valid_at="2026-06-07T07:00:00+00:00",
    )
    memory = FakeMemory([edge], enable_manual=False)

    result = asyncio.run(
        client.reply("huy lich choi game voi anh Tu ngay mai", memory)
    )

    assert memory.searches == [
        "choi game voi anh Tu",
        "choi game voi anh Tu 2026-06-07",
        "huy lich choi game voi anh Tu ngay mai 2026-06-07",
        "lịch trình sự kiện kế hoạch ngày 2026-06-07",
    ]
    assert memory.invalidations == [
        ("huy lich choi game voi anh Tu ngay mai choi game voi anh Tu", [edge])
    ]
    assert result.tool_trace[0].result == "invalidated 1 matching fact(s)"


def test_tool_iteration_limit_gets_final_no_tool_answer() -> None:
    client, requests = _client_for_responses(
        [
            _gemini_call("search_memory", {"query": "anything"}),
            _gemini_text("Final answer from available tool results."),
        ],
        max_tool_iterations=1,
    )

    result = asyncio.run(client.reply("question", FakeMemory()))

    assert result.reply == "Final answer from available tool results."
    assert "tools" in requests[0]
    assert "tools" not in requests[1]


def _tool_names(memory_write_mode: str) -> set[str]:
    return {tool["name"] for tool in build_tool_declarations(memory_write_mode)}


def _client_for_responses(
    responses: list[dict[str, Any]],
    memory_write_mode: str = "both",
    max_tool_iterations: int = 6,
) -> tuple[AssistantClient, list[dict[str, Any]]]:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=responses.pop(0))

    client = AssistantClient(
        base_url="http://testserver/v1",
        api_key="test-key",
        model="gemini-test",
        memory_write_mode=memory_write_mode,
        max_tool_iterations=max_tool_iterations,
        transport=httpx.MockTransport(handler),
        now_factory=lambda: datetime.fromisoformat("2026-06-06T12:00:00+07:00"),
    )
    return client, requests


def _gemini_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": name,
                                "args": args,
                                "id": f"{name}-1",
                            }
                        }
                    ],
                }
            }
        ]
    }


def _gemini_text(text: str) -> dict[str, Any]:
    return {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": text}]}}
        ]
    }
