import asyncio
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from os import getenv
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder import EmbedderClient, OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.llm_client import LLMConfig, OpenAIClient
from graphiti_core.nodes import EpisodeType

from app.fact_filter import LOCAL_TZ, should_cancel_fact
from app.schemas import RetrievedFact

EXTRACTION_INSTRUCTIONS = """
Extract durable user facts and scheduled events. Preserve Vietnamese names and wording.
For debts, preserve direction exactly and include debtor, creditor, and amount in the fact.
Examples:
- "Minh no tao 60k" means Minh owes user 60k.
- "Tao no Nam 30k" means user owes Nam 30k.
Do not extract only the amount as a standalone debt fact.
For scheduled events, include the activity, participants, and time.
Example: "Co lich choi game voi anh Tu luc 3h chieu mai" means user has a game session
with anh Tu at 3pm tomorrow.
Do not extract facts from questions.
"""

QWEN_QUERY_PROMPT = (
    "Instruct: Given a chat memory search query, retrieve relevant stored personal facts "
    "and events that answer the query\nQuery: "
)


@dataclass(frozen=True)
class GraphitiSettings:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_small_model: str
    embedding_mode: str
    embedding_model: str
    embedding_dim: int
    embedding_preload: bool
    google_api_key: str | None
    group_id: str
    retrieval_limit: int
    memory_ingest_background: bool
    memory_write_mode: str
    agent_max_tool_iterations: int

    @classmethod
    def from_env(cls) -> "GraphitiSettings":
        memory_write_mode = getenv("MEMORY_WRITE_MODE", "both").strip().lower()
        if memory_write_mode not in {"exact", "model", "both"}:
            raise ValueError("MEMORY_WRITE_MODE must be 'exact', 'model', or 'both'")

        return cls(
            neo4j_uri=getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=getenv("NEO4J_USER", "neo4j"),
            neo4j_password=getenv("NEO4J_PASSWORD", "password"),
            llm_base_url=getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1"),
            llm_api_key=getenv("LLM_API_KEY", "dummy"),
            llm_model=getenv("LLM_MODEL", "gemini-2.5-flash"),
            llm_small_model=getenv(
                "LLM_SMALL_MODEL", getenv("LLM_MODEL", "gemini-2.5-flash")
            ),
            embedding_mode=getenv("EMBEDDING_MODE", "proxy").lower(),
            embedding_model=getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_dim=int(getenv("EMBEDDING_DIM", "1024")),
            embedding_preload=_env_bool("EMBEDDING_PRELOAD", True),
            google_api_key=getenv("GOOGLE_API_KEY") or None,
            group_id=getenv("GRAPHITI_GROUP_ID", "chat-lab"),
            retrieval_limit=int(getenv("RETRIEVAL_LIMIT", "6")),
            memory_ingest_background=_env_bool("MEMORY_INGEST_BACKGROUND", True),
            memory_write_mode=memory_write_mode,
            agent_max_tool_iterations=int(getenv("AGENT_MAX_TOOL_ITERATIONS", "6")),
        )


class GraphitiMemory:
    def __init__(self, settings: GraphitiSettings):
        self.settings = settings
        llm_client = ChatCompletionsGraphitiClient(
            config=LLMConfig(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model=settings.llm_model,
                small_model=settings.llm_small_model,
                temperature=0.2,
            )
        )
        self.client = Graphiti(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            llm_client=llm_client,
            embedder=_build_embedder(settings),
            cross_encoder=PassthroughReranker(),
        )

    async def initialize(self) -> None:
        await self.client.build_indices_and_constraints()
        if self.settings.embedding_preload and isinstance(
            self.client.embedder, LocalQwenEmbedder
        ):
            await self.client.embedder.load_model()

    async def close(self) -> None:
        await self.client.close()

    async def search(self, message: str) -> list[RetrievedFact]:
        return self.edges_to_facts(await self.search_edges(message))

    async def search_edges(self, message: str):
        return await self.client.search(
            message,
            group_ids=[self.settings.group_id],
            num_results=self.settings.retrieval_limit,
        )

    async def invalidate_matching_facts(self, message: str, edges: list[Any]) -> int:
        invalid_at = datetime.now(timezone.utc)
        invalidated = 0
        for edge in edges:
            fact = RetrievedFact(
                fact=edge.fact,
                valid_at=_iso_or_none(edge.valid_at),
                invalid_at=_iso_or_none(edge.invalid_at),
                score=None,
            )
            if not should_cancel_fact(message, fact):
                continue
            await self.client.driver.execute_query(
                """
                MATCH ()-[e:RELATES_TO {uuid: $uuid}]-()
                SET e.invalid_at = $invalid_at
                RETURN e.uuid AS uuid
                """,
                uuid=edge.uuid,
                invalid_at=invalid_at,
            )
            invalidated += 1
        return invalidated

    async def add_manual_fact(self, fact: str, valid_at: datetime | None) -> None:
        await self.client.driver.execute_query(
            """
            MERGE (source:ManualMemory {group_id: $group_id, name: 'user'})
            MERGE (target:ManualMemory {group_id: $group_id, name: 'memory'})
            CREATE (source)-[:MANUAL_FACT {
                uuid: $uuid,
                group_id: $group_id,
                fact: $fact,
                valid_at: $valid_at,
                valid_date: $valid_date,
                invalid_at: null,
                created_at: $created_at
            }]->(target)
            """,
            group_id=self.settings.group_id,
            uuid=str(uuid4()),
            fact=fact,
            valid_at=valid_at.isoformat() if valid_at else None,
            valid_date=valid_at.astimezone(LOCAL_TZ).date().isoformat()
            if valid_at
            else None,
            created_at=datetime.now(LOCAL_TZ).isoformat(),
        )

    async def manual_facts_for_date(self, target_date: str | date) -> list[RetrievedFact]:
        date_text = (
            target_date.isoformat() if isinstance(target_date, date) else target_date
        )
        result = await self.client.driver.execute_query(
            """
            MATCH ()-[e:MANUAL_FACT {group_id: $group_id, valid_date: $valid_date}]->()
            WHERE e.invalid_at IS NULL
            RETURN e.fact AS fact, e.valid_at AS valid_at, e.invalid_at AS invalid_at
            ORDER BY e.created_at DESC
            LIMIT $limit
            """,
            group_id=self.settings.group_id,
            valid_date=date_text,
            limit=self.settings.retrieval_limit,
        )
        records = _records(result)
        return [
            RetrievedFact(
                fact=record["fact"],
                valid_at=_iso_or_none(record["valid_at"]),
                invalid_at=_iso_or_none(record["invalid_at"]),
                score=None,
            )
            for record in records
        ]

    async def invalidate_matching_manual_facts(
        self, message: str, target_date: str | date | None
    ) -> int:
        date_text = (
            target_date.isoformat()
            if isinstance(target_date, date)
            else target_date
        )
        if not date_text:
            return 0

        facts = await self.manual_facts_for_date(date_text)
        invalidated_facts = [
            fact for fact in facts if should_cancel_fact(message, fact)
        ]
        if not invalidated_facts:
            return 0

        invalid_at = datetime.now(timezone.utc).isoformat()
        for fact in invalidated_facts:
            await self.client.driver.execute_query(
                """
                MATCH ()-[e:MANUAL_FACT {
                    group_id: $group_id,
                    valid_date: $valid_date,
                    fact: $fact
                }]->()
                SET e.invalid_at = $invalid_at
                """,
                group_id=self.settings.group_id,
                valid_date=date_text,
                fact=fact.fact,
                invalid_at=invalid_at,
            )
        return len(invalidated_facts)

    def edges_to_facts(self, edges: list[Any]) -> list[RetrievedFact]:
        return [
            RetrievedFact(
                fact=edge.fact,
                valid_at=_iso_or_none(edge.valid_at),
                invalid_at=_iso_or_none(edge.invalid_at),
                score=None,
            )
            for edge in edges
        ]

    async def add_user_message(self, message: str) -> None:
        await self._add_episode("user", message)

    async def add_memory_fact(self, memory_text: str) -> None:
        await self._add_episode("memory", memory_text)

    async def add_assistant_reply(self, reply: str) -> None:
        return None

    async def _add_episode(self, speaker: str, content: str) -> None:
        now = datetime.now(LOCAL_TZ)
        await self.client.add_episode(
            name=f"{speaker}-{now.isoformat()}",
            episode_body=f"{speaker}: {content}",
            source_description=f"chat message from {speaker}",
            reference_time=now,
            source=EpisodeType.message,
            group_id=self.settings.group_id,
            custom_extraction_instructions=EXTRACTION_INSTRUCTIONS,
        )


class ChatCompletionsGraphitiClient(OpenAIClient):
    async def _create_structured_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None,
        max_tokens: int,
        response_model: type[Any],
        reasoning: str | None = None,
        verbosity: str | None = None,
    ):
        body = _build_gemini_structured_body(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_model=response_model,
        )
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                _gemini_generate_content_url(self.config.base_url, model),
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
        payload = response.json()
        content = payload["candidates"][0]["content"]["parts"][0]["text"]
        validated = response_model.model_validate_json(content)
        usage = payload.get("usageMetadata", {})
        return SimpleNamespace(
            output_text=validated.model_dump_json(),
            usage=SimpleNamespace(
                input_tokens=usage.get("promptTokenCount", 0),
                output_tokens=usage.get("candidatesTokenCount", 0),
            ),
        )


class PassthroughReranker(CrossEncoderClient):
    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        return [(passage, 1.0) for passage in passages]


class LocalQwenEmbedder(EmbedderClient):
    def __init__(self, model_name: str, embedding_dim: int):
        self.model_name = model_name
        self.embedding_dim = embedding_dim
        self._model = None

    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        text = _single_text(input_data)
        return await asyncio.to_thread(self._encode_query, text)

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        if not input_data_list:
            return []
        return await asyncio.to_thread(self._encode_documents, input_data_list)

    async def load_model(self) -> None:
        await asyncio.to_thread(self._load_model)

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self.model_name,
                cache_folder=getenv(
                    "SENTENCE_TRANSFORMERS_HOME",
                    ".hf-cache/sentence-transformers",
                ),
            )
        return self._model

    def _encode_query(self, text: str) -> list[float]:
        model = self._load_model()
        try:
            embedding = model.encode(
                text,
                prompt_name="query",
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        except ValueError:
            embedding = model.encode(
                text,
                prompt=QWEN_QUERY_PROMPT,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        return self._validate_embedding(embedding)

    def _encode_documents(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [self._validate_embedding(embedding) for embedding in embeddings]

    def _validate_embedding(self, embedding: Any) -> list[float]:
        values = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        if len(values) != self.embedding_dim:
            raise ValueError(
                f"{self.model_name} returned {len(values)} dimensions; "
                f"expected EMBEDDING_DIM={self.embedding_dim}"
            )
        return [float(value) for value in values]


def _build_embedder(settings: GraphitiSettings):
    if settings.embedding_mode == "local":
        return LocalQwenEmbedder(settings.embedding_model, settings.embedding_dim)

    if settings.embedding_mode == "gemini":
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when EMBEDDING_MODE=gemini")
        return GeminiEmbedder(
            config=GeminiEmbedderConfig(
                api_key=settings.google_api_key,
                embedding_model=settings.embedding_model,
                embedding_dim=settings.embedding_dim,
            )
        )

    if settings.embedding_mode != "proxy":
        raise ValueError("EMBEDDING_MODE must be 'local', 'proxy', or 'gemini'")

    return OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
        )
    )


def _single_text(
    input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
) -> str:
    if isinstance(input_data, str):
        return input_data
    if isinstance(input_data, list) and input_data and isinstance(input_data[0], str):
        return input_data[0]
    raise TypeError("Local embeddings require text input")


def _env_bool(name: str, default: bool) -> bool:
    value = getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _records(result: Any) -> list[Any]:
    if hasattr(result, "records"):
        return result.records
    return result[0]


def _build_gemini_structured_body(
    messages: list[dict[str, Any]],
    temperature: float | None,
    max_tokens: int,
    response_model: type[Any],
) -> dict[str, Any]:
    system_parts: list[dict[str, str]] = []
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role", "user")
        text = str(message.get("content", ""))
        if role == "system":
            system_parts.append({"text": text})
        else:
            contents.append(
                {
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": text}],
                }
            )

    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature or 0,
            "maxOutputTokens": max(max_tokens, 4096),
            "thinkingConfig": {"thinkingBudget": 0},
            "responseMimeType": "application/json",
            "responseSchema": _gemini_response_schema(response_model),
        },
    }
    if system_parts:
        body["systemInstruction"] = {"parts": system_parts}
    return body


def _gemini_generate_content_url(base_url: str | None, model: str) -> str:
    root = (base_url or "http://127.0.0.1:8317/v1").rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return f"{root}/v1beta/models/{model}:generateContent"


def _gemini_response_schema(response_model: type[Any]) -> dict[str, Any]:
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


def _iso_or_none(value: datetime | str | None) -> str | None:
    if isinstance(value, str):
        return value
    return value.isoformat() if value else None
