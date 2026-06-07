import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.fact_filter import (
    LOCAL_TZ,
    filter_active_facts,
    filter_active_facts_for_date,
)
from app.schemas import RetrievedFact, ToolTrace


AGENT_SYSTEM_PROMPT = """You are a concise, natural chat assistant with memory tools.
Use tools before answering when the user asks about remembered information, schedules,
debts, plans, cancellations, or updates.

Rules:
- For memory recall questions, call search_memory before answering.
- For scheduled-event questions with relative dates like "tomorrow" or "ngay mai",
  pass the absolute local date as YYYY-MM-DD.
- For durable user statements or scheduled events, call an available remember tool
  before the final reply.
- For cancellations or changes, call cancel_matching_facts for the old memory first.
- Do not invent memory. Only save information grounded in the current user message.
- Preserve debt direction exactly: "A owes B" is different from "B owes A".
- The user may write in Vietnamese; answer in the same language as the user.
"""


@dataclass
class AgentResult:
    reply: str
    retrieved_facts: list[RetrievedFact]
    tool_trace: list[ToolTrace]


@dataclass
class ToolOutcome:
    response: dict[str, Any]
    summary: str


class AssistantClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        memory_write_mode: str = "both",
        max_tool_iterations: int = 6,
        transport: httpx.AsyncBaseTransport | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.memory_write_mode = memory_write_mode
        self.max_tool_iterations = max_tool_iterations
        self.transport = transport
        self.now_factory = now_factory or (lambda: datetime.now(LOCAL_TZ))

    async def reply(self, message: str, memory: Any) -> AgentResult:
        now = self._local_now()
        pinned_facts = await _load_pinned_facts(memory)
        toolbox = MemoryToolbox(
            memory=memory,
            user_message=message,
            write_mode=self.memory_write_mode,
            now=now,
        )
        pinned_context = _pinned_context_text(pinned_facts)
        contents: list[dict[str, Any]] = [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"Current local datetime: {now.isoformat()}\n"
                            f"Current local date: {now.date().isoformat()}\n\n"
                            f"{pinned_context}"
                            f"User message:\n{message}"
                        )
                    }
                ],
            }
        ]
        tool_declarations = build_tool_declarations(self.memory_write_mode)
        trace: list[ToolTrace] = []

        for _ in range(self.max_tool_iterations):
            payload = await self._generate(contents, tool_declarations)
            content = _first_content(payload)
            function_calls = _extract_function_calls(content)
            if not function_calls:
                return AgentResult(
                    reply=_content_text(content),
                    retrieved_facts=toolbox.retrieved_facts,
                    tool_trace=trace,
                )

            contents.append(content)
            response_parts: list[dict[str, Any]] = []
            for function_call in function_calls:
                name = str(function_call.get("name", ""))
                arguments = _function_arguments(function_call)
                outcome = await toolbox.call(name, arguments)
                trace.append(
                    ToolTrace(
                        name=name,
                        arguments=arguments,
                        result=outcome.summary,
                    )
                )
                function_response: dict[str, Any] = {
                    "name": name,
                    "response": outcome.response,
                }
                call_id = function_call.get("id")
                if call_id is not None:
                    function_response["id"] = call_id
                response_parts.append({"functionResponse": function_response})

            contents.append({"role": "user", "parts": response_parts})

        contents.append(
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Tool iteration limit reached. Provide the final "
                            "user-facing answer from the tool results so far. "
                            "Do not call more tools."
                        )
                    }
                ],
            }
        )
        payload = await self._generate(contents, [])
        content = _first_content(payload)
        return AgentResult(
            reply=_content_text(content),
            retrieved_facts=toolbox.retrieved_facts,
            tool_trace=trace,
        )

    def _local_now(self) -> datetime:
        now = self.now_factory()
        if now.tzinfo is None:
            now = now.replace(tzinfo=LOCAL_TZ)
        return now.astimezone(LOCAL_TZ)

    async def _generate(
        self, contents: list[dict[str, Any]], tool_declarations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096,
                "thinkingConfig": {"thinkingBudget": 0},
            },
            "systemInstruction": {"parts": [{"text": AGENT_SYSTEM_PROMPT}]},
        }
        if tool_declarations:
            body["tools"] = [{"functionDeclarations": tool_declarations}]
            body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}

        async with httpx.AsyncClient(
            timeout=120,
            transport=self.transport,
        ) as client:
            response = await client.post(
                _gemini_generate_content_url(self.base_url, self.model),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
        return response.json()


class MemoryToolbox:
    def __init__(
        self, memory: Any, user_message: str, write_mode: str, now: datetime
    ):
        self.memory = memory
        self.user_message = user_message
        self.write_mode = write_mode
        self.now = now
        self.retrieved_facts: list[RetrievedFact] = []
        self._saved_current_message = False

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        if name not in self.allowed_tool_names:
            return ToolOutcome(
                response={"status": "error", "message": f"Tool {name} is not allowed"},
                summary=f"{name} is not allowed",
            )

        if name == "search_memory":
            return await self._search_memory(arguments)
        if name == "remember_current_message":
            return await self._remember_current_message()
        if name == "remember_fact":
            return await self._remember_fact(arguments)
        if name == "cancel_matching_facts":
            return await self._cancel_matching_facts(arguments)

        return ToolOutcome(
            response={"status": "error", "message": f"Unknown tool {name}"},
            summary=f"unknown tool {name}",
        )

    @property
    def allowed_tool_names(self) -> set[str]:
        names = {"search_memory", "cancel_matching_facts"}
        if self.write_mode in {"exact", "both"}:
            names.add("remember_current_message")
        if self.write_mode in {"model", "both"}:
            names.add("remember_fact")
        return names

    async def _search_memory(self, arguments: dict[str, Any]) -> ToolOutcome:
        query = _string_arg(arguments, "query") or self.user_message
        date_value = _string_arg(arguments, "date")
        if date_value and hasattr(self.memory, "manual_facts_for_date"):
            manual_facts = await self.memory.manual_facts_for_date(date_value)
            self._add_retrieved_facts(manual_facts)
            return ToolOutcome(
                response={
                    "status": "ok",
                    "count": len(manual_facts),
                    "facts": _facts_to_dicts(manual_facts),
                },
                summary=f"retrieved {len(manual_facts)} active fact(s)",
            )

        edges = await self._search_edges(query, date_value)
        facts = self.memory.edges_to_facts(edges)
        if date_value:
            facts = filter_active_facts_for_date(facts, date_value, self.now)
            if hasattr(self.memory, "manual_facts_for_date"):
                facts.extend(await self.memory.manual_facts_for_date(date_value))
        else:
            facts.extend(await self._search_companion_memories(query, broad=False))
            facts = filter_active_facts(facts, self.now)
        facts = _dedupe_facts(facts)

        if (
            not facts
            and not date_value
            and _looks_like_memory_question(f"{self.user_message} {query}")
        ):
            edges = await self._search_edges(query, date_value, broad=True)
            facts = self.memory.edges_to_facts(edges)
            facts.extend(await self._search_companion_memories(query, broad=True))
            facts = _dedupe_facts(filter_active_facts(facts, self.now))

        self._add_retrieved_facts(facts)
        return ToolOutcome(
            response={
                "status": "ok",
                "count": len(facts),
                "facts": _facts_to_dicts(facts),
            },
            summary=f"retrieved {len(facts)} active fact(s)",
        )

    async def _remember_current_message(self) -> ToolOutcome:
        if self._saved_current_message:
            return ToolOutcome(
                response={"status": "ok", "saved": False, "reason": "already_saved"},
                summary="current message was already saved",
            )

        saved_manually = await self._save_temporal_manual_fact(self.user_message)
        if saved_manually:
            self._saved_current_message = True
            return ToolOutcome(
                response={
                    "status": "ok",
                    "saved": True,
                    "saved_as": "manual_temporal_fact",
                },
                summary="saved manual temporal memory",
            )

        await self.memory.add_user_message(self._current_message_for_memory())
        self._saved_current_message = True
        return ToolOutcome(
            response={"status": "ok", "saved": True},
            summary="saved current user message",
        )

    async def _remember_fact(self, arguments: dict[str, Any]) -> ToolOutcome:
        memory_text = _string_arg(arguments, "memory_text")
        if not memory_text:
            return ToolOutcome(
                response={"status": "error", "message": "memory_text is required"},
                summary="memory_text is required",
            )

        if self.write_mode == "both" and _looks_temporal_memory(
            f"{self.user_message} {memory_text}"
        ):
            await self._save_temporal_manual_fact(memory_text)
            self._saved_current_message = True
            return ToolOutcome(
                response={
                    "status": "ok",
                    "saved": True,
                    "saved_as": "manual_temporal_fact",
                },
                summary="saved manual temporal memory",
            )

        await self.memory.add_memory_fact(memory_text)
        return ToolOutcome(
            response={"status": "ok", "saved": True},
            summary="saved model-authored memory",
        )

    async def _cancel_matching_facts(self, arguments: dict[str, Any]) -> ToolOutcome:
        query = _string_arg(arguments, "query") or self.user_message
        date_value = _string_arg(arguments, "date")
        cancel_text = f"{self.user_message} {query}".strip()
        manual_invalidated = 0
        if date_value and hasattr(self.memory, "invalidate_matching_manual_facts"):
            manual_invalidated = await self.memory.invalidate_matching_manual_facts(
                cancel_text,
                date_value,
            )
            return ToolOutcome(
                response={
                    "status": "ok",
                    "matched_count": manual_invalidated,
                    "invalidated_count": manual_invalidated,
                    "matched_facts": [],
                },
                summary=f"invalidated {manual_invalidated} matching fact(s)",
            )

        edges = await self._search_edges(query, date_value)
        facts = self.memory.edges_to_facts(edges)
        selected_edges = []
        selected_facts = []
        for edge, fact in zip(edges, facts, strict=False):
            if _fact_matches_tool_date(fact, date_value, self.now):
                selected_edges.append(edge)
                selected_facts.append(fact)

        invalidated = await self.memory.invalidate_matching_facts(
            cancel_text, selected_edges
        )
        invalidated += manual_invalidated
        if not date_value and hasattr(
            self.memory, "invalidate_matching_companion_memories"
        ):
            companion_facts = await self._search_companion_memories(query, broad=False)
            invalidated += await self.memory.invalidate_matching_companion_memories(
                cancel_text,
                companion_facts,
            )
        return ToolOutcome(
            response={
                "status": "ok",
                "matched_count": len(selected_facts),
                "invalidated_count": invalidated,
                "matched_facts": _facts_to_dicts(selected_facts),
            },
            summary=f"invalidated {invalidated} matching fact(s)",
        )

    async def _search_edges(
        self, query: str, date_value: str, *, broad: bool = False
    ) -> list[Any]:
        edges_by_key: dict[Any, Any] = {}
        for search_query in _search_queries(
            query, date_value, self.user_message, broad=broad
        ):
            for edge in await self.memory.search_edges(search_query):
                edges_by_key.setdefault(_edge_key(edge), edge)
        return list(edges_by_key.values())

    async def _search_companion_memories(
        self, query: str, *, broad: bool
    ) -> list[RetrievedFact]:
        if not hasattr(self.memory, "search_companion_memories"):
            return []

        facts_by_key: dict[tuple[str, str | None, str | None], RetrievedFact] = {}
        for search_query in _search_queries(
            query, "", self.user_message, broad=broad
        ):
            for fact in await self.memory.search_companion_memories(search_query):
                facts_by_key.setdefault(
                    (fact.fact, fact.valid_at, fact.invalid_at),
                    fact,
                )
        return list(facts_by_key.values())

    def _current_message_for_memory(self) -> str:
        if self.write_mode == "both" and _looks_temporal_memory(self.user_message):
            return _normalize_relative_dates(self.user_message, self.now)
        return self.user_message

    async def _save_temporal_manual_fact(self, fact_text: str) -> bool:
        if self.write_mode != "both" or not hasattr(self.memory, "add_manual_fact"):
            return False
        if not _looks_temporal_memory(fact_text):
            return False

        normalized = _normalize_relative_dates(fact_text, self.now)
        valid_at = _extract_memory_datetime(normalized, self.now)
        if valid_at is None:
            return False

        await self.memory.add_manual_fact(normalized, valid_at)
        return True

    def _add_retrieved_facts(self, facts: list[RetrievedFact]) -> None:
        existing = {
            (fact.fact, fact.valid_at, fact.invalid_at) for fact in self.retrieved_facts
        }
        for fact in facts:
            key = (fact.fact, fact.valid_at, fact.invalid_at)
            if key not in existing:
                self.retrieved_facts.append(fact)
                existing.add(key)


def build_tool_declarations(memory_write_mode: str) -> list[dict[str, Any]]:
    declarations = [
        {
            "name": "search_memory",
            "description": (
                "Search Graphiti memory for relevant active personal facts, debts, "
                "or scheduled events before answering memory questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query in the user's language.",
                    },
                    "date": {
                        "type": "string",
                        "description": (
                            "Optional local date filter in YYYY-MM-DD. Use for "
                            "schedule questions like tomorrow."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "cancel_matching_facts",
            "description": (
                "Invalidate active memory facts or events that the current user "
                "message cancels or replaces."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms for the memory to cancel.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Optional local date filter in YYYY-MM-DD.",
                    },
                },
                "required": ["query"],
            },
        },
    ]

    if memory_write_mode in {"exact", "both"}:
        declarations.append(
            {
                "name": "remember_current_message",
                "description": (
                    "Store the exact current user message as a Graphiti episode. "
                    "Use for durable facts or scheduled events stated by the user."
                ),
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        )

    if memory_write_mode in {"model", "both"}:
        declarations.append(
            {
                "name": "remember_fact",
                "description": (
                    "Store a concise memory fact or event derived only from the "
                    "current user message."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "memory_text": {
                            "type": "string",
                            "description": (
                                "The fact/event to store, preserving names, "
                                "amounts, dates, times, and debt direction."
                            ),
                        }
                    },
                    "required": ["memory_text"],
                },
            }
        )

    return declarations


def _first_content(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        return {"role": "model", "parts": []}
    return candidates[0].get("content") or {"role": "model", "parts": []}


def _extract_function_calls(content: dict[str, Any]) -> list[dict[str, Any]]:
    calls = []
    for part in content.get("parts") or []:
        function_call = part.get("functionCall") or part.get("function_call")
        if isinstance(function_call, dict):
            calls.append(function_call)
    return calls


def _function_arguments(function_call: dict[str, Any]) -> dict[str, Any]:
    arguments = function_call.get("args", function_call.get("arguments", {}))
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _content_text(content: dict[str, Any]) -> str:
    lines = []
    for part in content.get("parts") or []:
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            lines.append(text.strip())
    return "\n".join(lines)


def _string_arg(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    return value.strip() if isinstance(value, str) else ""


def _fact_matches_tool_date(
    fact: RetrievedFact, date_value: str, now: datetime
) -> bool:
    if date_value:
        return bool(filter_active_facts_for_date([fact], date_value, now))
    return bool(filter_active_facts([fact], now))


def _search_queries(
    query: str, date_value: str, user_message: str, *, broad: bool = False
) -> list[str]:
    queries = [query]
    if date_value:
        queries.extend(
            [
                f"{query} {date_value}",
                f"{user_message} {date_value}",
                f"lịch trình sự kiện kế hoạch ngày {date_value}",
            ]
        )
    elif broad:
        queries.extend(
            [
                user_message,
                "sở thích của user",
                "điều user không thích",
                "thói quen của user",
                "bối cảnh cá nhân của user",
                "mục tiêu hiện tại của user",
                "người liên quan với user",
                "cảm xúc gần đây của user",
                "áp lực stress buồn mệt lo lắng cảm xúc",
                "cách hỗ trợ user",
                "cách xưng hô với user",
                "phong cách trả lời user muốn",
                "ăn uống món ăn đồ uống cà phê rau mùi không thích dị ứng",
                "so thich khong thich thoi quen ca phe rau mui di ung",
                "ap luc stress buon met lo lang cam xuc ho tro",
                "muc tieu du dinh dang co gang",
                "anh chi ban nguoi yeu dong nghiep nguoi lien quan",
                "user personal preferences dislikes goals relationships emotions",
            ]
        )

    deduped = []
    seen = set()
    for item in queries:
        normalized = item.strip()
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped


def _looks_temporal_memory(text: str) -> bool:
    normalized = text.lower()
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", normalized):
        return True
    markers = (
        "ngày mai",
        "mai",
        "hôm nay",
        "hôm qua",
        "sáng",
        "chiều",
        "tối",
        "giờ",
        "lúc",
        "tomorrow",
        "today",
        "yesterday",
    )
    return any(marker in normalized for marker in markers)


def _looks_like_memory_question(text: str) -> bool:
    normalized = text.lower()
    markers = (
        "tôi",
        "toi",
        "tui",
        "tao",
        "mình",
        "minh",
        "sở thích",
        "so thich",
        "thích",
        "thich",
        "không thích",
        "khong thich",
        "ghét",
        "ghet",
        "nhớ",
        "nho",
        "memory",
        "cảm xúc",
        "cam xuc",
        "buồn",
        "buon",
        "áp lực",
        "ap luc",
        "stress",
        "mục tiêu",
        "muc tieu",
        "bạn tôi",
        "ban toi",
        "người yêu",
        "nguoi yeu",
        "xưng hô",
        "xung ho",
        "gọi",
        "goi",
    )
    return any(marker in normalized for marker in markers)


async def _load_pinned_facts(memory: Any) -> list[RetrievedFact]:
    if not hasattr(memory, "pinned_memories"):
        return []
    return await memory.pinned_memories()


def _pinned_context_text(facts: list[RetrievedFact]) -> str:
    if not facts:
        return ""
    lines = "\n".join(f"- {fact.fact}" for fact in facts)
    return f"Always relevant user memory:\n{lines}\n\n"


def _normalize_relative_dates(text: str, now: datetime) -> str:
    tomorrow = (now.date()).toordinal() + 1
    tomorrow_text = datetime.fromordinal(tomorrow).date().isoformat()
    normalized = re.sub(
        r"\bngày\s+mai\b",
        f"ngày {tomorrow_text}",
        text,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\bngay\s+mai\b",
        f"ngay {tomorrow_text}",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"(?<!ngày\s)(?<!ngay\s)\bmai\b",
        f"ngày {tomorrow_text}",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized


def _edge_key(edge: Any) -> Any:
    return getattr(edge, "uuid", None) or (
        getattr(edge, "fact", None),
        getattr(edge, "valid_at", None),
        getattr(edge, "invalid_at", None),
    )


def _facts_to_dicts(facts: list[RetrievedFact]) -> list[dict[str, Any]]:
    return [fact.model_dump() for fact in facts]


def _dedupe_facts(facts: list[RetrievedFact]) -> list[RetrievedFact]:
    deduped = []
    seen = set()
    for fact in facts:
        key = (fact.fact, fact.valid_at, fact.invalid_at)
        if key in seen:
            continue
        deduped.append(fact)
        seen.add(key)
    return deduped


def _extract_memory_datetime(text: str, now: datetime) -> datetime | None:
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if not date_match:
        return None

    hour = 0
    minute = 0
    time_match = re.search(
        r"\b(\d{1,2})(?::(\d{1,2})|\s*(?:giờ|gio|h)\b)",
        text,
        flags=re.IGNORECASE,
    )
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)

    lowered = text.lower()
    if hour < 12 and any(
        marker in lowered for marker in ("chiều", "chieu", "tối", "toi", "pm")
    ):
        hour += 12

    parsed = datetime.fromisoformat(
        f"{date_match.group(1)}T{hour:02d}:{minute:02d}:00"
    )
    return parsed.replace(tzinfo=now.tzinfo or LOCAL_TZ)


def _gemini_generate_content_url(base_url: str | None, model: str) -> str:
    root = (base_url or "http://127.0.0.1:8317/v1").rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return f"{root}/v1beta/models/{model}:generateContent"
