import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app.memory_store import ConversationTurn, MemoryRecord, MemoryStore
from app.schemas import RetrievedFact, ToolTrace
from app.time_utils import LOCAL_TZ


MemoryType = Literal["pin", "long_term"]
MemoryOpName = Literal["create", "supersede", "delete", "ignore"]


PLANNER_SYSTEM_PROMPT = """You decide whether a Vietnamese chat assistant needs long-term memory.
Return JSON only.

Use memory when the user asks about prior preferences, prior decisions, personal context,
relationships, corrections, schedules, work/study context, or emotional/support context.
Do not use memory for general knowledge, translation, formatting, coding questions, or math
unless the user explicitly asks for remembered personal context.

If memory is needed, write one to three semantic search queries in the user's language.
Do not copy backend categories. Do not use keyword lists. Write natural queries that would
retrieve facts needed to answer the current message."""


SELECTOR_SYSTEM_PROMPT = """Select only memories that directly help answer the current user message.
Reject memories that are merely generally true, same-topic but not useful, or likely to distract.
Return JSON only. If nothing is directly relevant, select no ids."""


ANSWER_SYSTEM_PROMPT = """You are a concise, natural Vietnamese companion assistant.
Answer in the user's language and style.

Use only the current message, recent conversation, pinned memories, and selected
memories supplied in the prompt. Do not invent remembered facts. If selected memory is empty
and the user asks for remembered context, say you do not have enough remembered information.
Keep the answer useful and direct."""


CURATOR_SYSTEM_PROMPT = """You maintain durable long-term memory for a Vietnamese companion assistant.
Return JSON only.

Create memory only for durable user-grounded facts, preferences, relationships, work or study context,
support style, schedules, debts, or corrections from the current user message.
Do not store generic questions, one-off small talk, assistant claims, or facts inferred only from
the assistant reply.

Use memory_type=pin only for global interaction preferences that should affect every turn, such
as how to address the user, answer length, uncertainty handling, or support style. Everything
else is memory_type=long_term.

For corrections, supersede or delete existing memory by id when the prompt provides an existing
memory that is being replaced. Preserve debt direction exactly."""


@dataclass
class AgentResult:
    reply: str
    retrieved_facts: list[RetrievedFact]
    tool_trace: list[ToolTrace]


class MemoryPlan(BaseModel):
    needs_memory: bool
    queries: list[str] = Field(default_factory=list, max_length=3)
    reason: str = ""


class MemorySelection(BaseModel):
    selected_ids: list[str] = Field(default_factory=list)
    rejected_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class MemoryOperation(BaseModel):
    op: MemoryOpName
    text: str = ""
    memory_type: MemoryType = "long_term"
    replaces_id: str | None = None


class MemoryCuration(BaseModel):
    operations: list[MemoryOperation] = Field(default_factory=list, max_length=6)


class AssistantClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
        now_factory: Any | None = None,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.transport = transport
        self.now_factory = now_factory or (lambda: datetime.now(LOCAL_TZ))

    async def reply(self, message: str, memory: MemoryStore) -> AgentResult:
        now = self._local_now()
        recent_turns = await memory.recent_turns()
        pin_memories = await memory.pin_memories()
        trace: list[ToolTrace] = []

        plan = await self._plan_memory(message, recent_turns, pin_memories, now)
        queries = _clean_queries(plan)
        trace.append(
            ToolTrace(
                name="memory_planner",
                arguments={
                    "needs_memory": plan.needs_memory,
                    "query_count": len(queries),
                    "queries": queries,
                },
                result=plan.reason or "planned memory use",
            )
        )

        candidates: list[MemoryRecord] = []
        selected: list[MemoryRecord] = []
        if plan.needs_memory and queries:
            candidates = await memory.search(queries)
            trace.append(
                ToolTrace(
                    name="memory_search",
                    arguments={"queries": queries, "candidate_count": len(candidates)},
                    result=f"retrieved {len(candidates)} candidate memory item(s)",
                )
            )
            selection = await self._select_memories(
                message,
                recent_turns,
                pin_memories,
                candidates,
                now,
            )
            selected_ids = set(selection.selected_ids)
            selected = [item for item in candidates if item.id in selected_ids]
            trace.append(
                ToolTrace(
                    name="memory_selector",
                    arguments={
                        "selected_count": len(selected),
                        "rejected_count": len(selection.rejected_ids),
                        "selected_ids": selection.selected_ids,
                        "rejected_ids": selection.rejected_ids,
                    },
                    result=selection.reason
                    or f"selected {len(selected)} memory item(s)",
                )
            )
        else:
            trace.append(
                ToolTrace(
                    name="memory_search",
                    arguments={"queries": [], "candidate_count": 0},
                    result="skipped memory search",
                )
            )
            trace.append(
                ToolTrace(
                    name="memory_selector",
                    arguments={
                        "selected_count": 0,
                        "rejected_count": 0,
                        "selected_ids": [],
                        "rejected_ids": [],
                    },
                    result="skipped memory selector",
                )
            )

        try:
            reply = await self._answer(
                message,
                recent_turns,
                pin_memories,
                selected,
                plan,
                now,
            )
        except httpx.HTTPError as error:
            reply = "Tôi chưa gọi được mô hình trả lời lúc này. Ông thử lại sau một chút."
            trace.append(
                ToolTrace(
                    name="answer_generation",
                    arguments={"error_type": type(error).__name__},
                    result="failed to generate answer",
                )
            )

        curation = await self._curate_memory(
            message,
            reply,
            recent_turns,
            [*pin_memories, *candidates],
            now,
        )
        applied, skipped = await _apply_curation(memory, message, curation)
        trace.append(
            ToolTrace(
                name="memory_curator",
                arguments={
                    "operation_count": len(curation.operations),
                    "operations": [op.model_dump() for op in curation.operations],
                },
                result=f"applied {applied} operation(s), skipped {skipped}",
            )
        )

        await memory.add_turn("user", message)
        await memory.add_turn("assistant", reply)

        return AgentResult(
            reply=reply,
            retrieved_facts=[item.to_retrieved_fact() for item in selected],
            tool_trace=trace,
        )

    async def _plan_memory(
        self,
        message: str,
        recent_turns: list[ConversationTurn],
        pin_memories: list[MemoryRecord],
        now: datetime,
    ) -> MemoryPlan:
        prompt = _context_prompt(
            message=message,
            now=now,
            recent_turns=recent_turns,
            pin_memories=pin_memories,
            selected_memories=[],
        )
        return await self._structured(
            PLANNER_SYSTEM_PROMPT,
            prompt,
            MemoryPlan,
            fallback=MemoryPlan(needs_memory=False, queries=[], reason="planner fallback"),
        )

    async def _select_memories(
        self,
        message: str,
        recent_turns: list[ConversationTurn],
        pin_memories: list[MemoryRecord],
        candidates: list[MemoryRecord],
        now: datetime,
    ) -> MemorySelection:
        prompt = (
            _context_prompt(
                message=message,
                now=now,
                recent_turns=recent_turns,
                pin_memories=pin_memories,
                selected_memories=[],
            )
            + "\nCandidate memories:\n"
            + _memory_lines(candidates, include_ids=True)
        )
        return await self._structured(
            SELECTOR_SYSTEM_PROMPT,
            prompt,
            MemorySelection,
            fallback=MemorySelection(
                selected_ids=[],
                rejected_ids=[item.id for item in candidates],
                reason="selector fallback",
            ),
        )

    async def _answer(
        self,
        message: str,
        recent_turns: list[ConversationTurn],
        pin_memories: list[MemoryRecord],
        selected: list[MemoryRecord],
        plan: MemoryPlan,
        now: datetime,
    ) -> str:
        prompt = (
            _context_prompt(
                message=message,
                now=now,
                recent_turns=recent_turns,
                pin_memories=pin_memories,
                selected_memories=selected,
            )
            + f"\nMemory needed: {plan.needs_memory}\n"
            + f"Memory plan reason: {plan.reason}\n"
        )
        payload = await self._generate_text(ANSWER_SYSTEM_PROMPT, prompt)
        text = _content_text(_first_content(payload)).strip()
        return text or "Tôi chưa có đủ thông tin để trả lời chắc."

    async def _curate_memory(
        self,
        message: str,
        reply: str,
        recent_turns: list[ConversationTurn],
        known_memories: list[MemoryRecord],
        now: datetime,
    ) -> MemoryCuration:
        prompt = (
            f"Current local datetime: {now.isoformat()}\n"
            f"Current user message:\n{message}\n\n"
            f"Assistant reply:\n{reply}\n\n"
            f"Recent conversation:\n{_turn_lines(recent_turns)}\n\n"
            f"Existing memories that may be updated:\n"
            f"{_memory_lines(known_memories, include_ids=True)}"
        )
        return await self._structured(
            CURATOR_SYSTEM_PROMPT,
            prompt,
            MemoryCuration,
            fallback=MemoryCuration(operations=[]),
        )

    async def _structured[T: BaseModel](
        self,
        system_prompt: str,
        prompt: str,
        response_model: type[T],
        *,
        fallback: T,
    ) -> T:
        try:
            payload = await self._generate_text(
                system_prompt,
                prompt,
                response_model=response_model,
            )
            text = _content_text(_first_content(payload))
            return response_model.model_validate_json(text)
        except (httpx.HTTPError, ValueError, json.JSONDecodeError):
            return fallback

    async def _generate_text(
        self,
        system_prompt: str,
        prompt: str,
        response_model: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096,
                "thinkingConfig": {"thinkingBudget": 0},
            },
            "systemInstruction": {"parts": [{"text": system_prompt}]},
        }
        if response_model is not None:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = _gemini_response_schema(
                response_model
            )

        async with httpx.AsyncClient(timeout=120, transport=self.transport) as client:
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

    def _local_now(self) -> datetime:
        now = self.now_factory()
        if now.tzinfo is None:
            now = now.replace(tzinfo=LOCAL_TZ)
        return now.astimezone(LOCAL_TZ)


async def _apply_curation(
    memory: MemoryStore,
    source_message: str,
    curation: MemoryCuration,
) -> tuple[int, int]:
    applied = 0
    skipped = 0
    for operation in curation.operations:
        if operation.op == "ignore":
            continue
        if operation.op == "create":
            if not operation.text.strip():
                skipped += 1
                continue
            await memory.add_memory(
                text=operation.text.strip(),
                memory_type=operation.memory_type,
                source_message=source_message,
            )
            applied += 1
            continue
        if operation.op == "supersede":
            if not operation.replaces_id or not operation.text.strip():
                skipped += 1
                continue
            replacement = await memory.supersede_memory(
                operation.replaces_id,
                replacement_text=operation.text.strip(),
                memory_type=operation.memory_type,
                source_message=source_message,
            )
            applied += 1 if replacement is not None else 0
            skipped += 0 if replacement is not None else 1
            continue
        if operation.op == "delete":
            if not operation.replaces_id:
                skipped += 1
                continue
            deleted = await memory.delete_memory(operation.replaces_id)
            applied += 1 if deleted else 0
            skipped += 0 if deleted else 1
            continue
    return applied, skipped


def _clean_queries(plan: MemoryPlan) -> list[str]:
    if not plan.needs_memory:
        return []
    queries = []
    seen = set()
    for query in plan.queries:
        normalized = query.strip()
        if normalized and normalized not in seen:
            queries.append(normalized)
            seen.add(normalized)
    return queries[:3]


def _context_prompt(
    *,
    message: str,
    now: datetime,
    recent_turns: list[ConversationTurn],
    pin_memories: list[MemoryRecord],
    selected_memories: list[MemoryRecord],
) -> str:
    return (
        f"Current local datetime: {now.isoformat()}\n"
        f"Current local date: {now.date().isoformat()}\n\n"
        f"Recent conversation:\n{_turn_lines(recent_turns)}\n\n"
        f"Pinned memories:\n{_memory_lines(pin_memories, include_ids=False)}\n\n"
        f"Selected memories:\n{_memory_lines(selected_memories, include_ids=False)}\n\n"
        f"Current user message:\n{message}"
    )


def _turn_lines(turns: list[ConversationTurn]) -> str:
    if not turns:
        return "(none)"
    return "\n".join(f"- {turn.role}: {turn.content}" for turn in turns)


def _memory_lines(memories: list[MemoryRecord], *, include_ids: bool) -> str:
    if not memories:
        return "(none)"
    lines = []
    for memory in memories:
        prefix = f"- [{memory.id}] " if include_ids else "- "
        lines.append(f"{prefix}{memory.text} (type={memory.memory_type})")
    return "\n".join(lines)


def _first_content(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        return {"role": "model", "parts": []}
    return candidates[0].get("content") or {"role": "model", "parts": []}


def _content_text(content: dict[str, Any]) -> str:
    lines = []
    for part in content.get("parts") or []:
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            lines.append(text.strip())
    return "\n".join(lines)


def _gemini_generate_content_url(base_url: str | None, model: str) -> str:
    root = (base_url or "http://127.0.0.1:8317/v1").rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return f"{root}/v1beta/models/{model}:generateContent"


def _gemini_response_schema(response_model: type[BaseModel]) -> dict[str, Any]:
    schema = deepcopy(response_model.model_json_schema())
    defs = schema.pop("$defs", {})
    _inline_schema_refs(schema, defs)
    _strip_schema_metadata(schema)
    _disallow_extra_properties(schema)
    return schema


def _inline_schema_refs(value: Any, defs: dict[str, Any]) -> None:
    if isinstance(value, list):
        for item in value:
            _inline_schema_refs(item, defs)
        return
    if not isinstance(value, dict):
        return

    ref = value.pop("$ref", None)
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        target = deepcopy(defs[ref.removeprefix("#/$defs/")])
        value.clear()
        value.update(target)

    for item in value.values():
        _inline_schema_refs(item, defs)


def _strip_schema_metadata(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _strip_schema_metadata(item)
        return
    if not isinstance(value, dict):
        return

    value.pop("title", None)
    value.pop("default", None)
    for item in value.values():
        _strip_schema_metadata(item)


def _disallow_extra_properties(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _disallow_extra_properties(item)
        return
    if not isinstance(value, dict):
        return

    if value.get("type") == "object":
        value.setdefault("additionalProperties", False)
    for item in value.values():
        _disallow_extra_properties(item)
