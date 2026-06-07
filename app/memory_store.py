import asyncio
import sqlite3
import struct
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from os import getenv
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.schemas import RetrievedFact
from app.time_utils import LOCAL_TZ


DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"


@dataclass(frozen=True)
class MemorySettings:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    group_id: str
    db_path: Path
    embedding_model: str
    embedding_dim: int
    embedding_preload: bool
    recent_turn_limit: int
    retrieval_limit: int

    @classmethod
    def from_env(cls) -> "MemorySettings":
        return cls(
            llm_base_url=getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1"),
            llm_api_key=getenv("LLM_API_KEY", "dummy"),
            llm_model=getenv("LLM_MODEL", "gemini-2.5-flash"),
            group_id=getenv("MEMORY_GROUP_ID")
            or getenv("GRAPHITI_GROUP_ID")
            or "chat-lab",
            db_path=Path(getenv("MEMORY_DB_PATH", ".data/memory.sqlite")),
            embedding_model=getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
            embedding_dim=int(getenv("EMBEDDING_DIM", "1024")),
            embedding_preload=_env_bool("EMBEDDING_PRELOAD", True),
            recent_turn_limit=int(getenv("RECENT_TURN_LIMIT", "12")),
            retrieval_limit=int(getenv("RETRIEVAL_LIMIT", "12")),
        )


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    text: str
    memory_type: str
    status: str
    source_message: str | None
    created_at: str
    updated_at: str
    valid_at: str | None
    invalid_at: str | None
    score: float | None = None

    def to_retrieved_fact(self) -> RetrievedFact:
        return RetrievedFact(
            fact=self.text,
            valid_at=self.valid_at,
            invalid_at=self.invalid_at,
            score=self.score,
        )


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    content: str
    created_at: str


class LocalEmbedder:
    def __init__(self, model_name: str, embedding_dim: int):
        self.model_name = model_name
        self.embedding_dim = embedding_dim
        self._model = None

    async def load_model(self) -> None:
        await asyncio.to_thread(self._load_model)

    async def embed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._encode_query, text)

    async def embed_document(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._encode_document, text)

    def _load_model(self) -> Any:
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
                f"Instruct: Given a chat memory search query, retrieve relevant "
                f"stored personal facts and events that answer the query\nQuery: {text}",
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        return self._validate_embedding(embedding)

    def _encode_document(self, text: str) -> list[float]:
        model = self._load_model()
        embedding = model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return self._validate_embedding(embedding)

    def _validate_embedding(self, embedding: Any) -> list[float]:
        values = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        if len(values) != self.embedding_dim:
            raise ValueError(
                f"{self.model_name} returned {len(values)} dimensions; "
                f"expected EMBEDDING_DIM={self.embedding_dim}"
            )
        return [float(value) for value in values]


class MemoryStore:
    def __init__(
        self,
        settings: MemorySettings,
        embedder: LocalEmbedder | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ):
        self.settings = settings
        self.embedder = embedder or LocalEmbedder(
            settings.embedding_model,
            settings.embedding_dim,
        )
        self.now_factory = now_factory or (lambda: datetime.now(LOCAL_TZ))
        self._connection: sqlite3.Connection | None = None

    async def initialize(self) -> None:
        self.settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.settings.db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
        if self.settings.embedding_preload:
            await self.embedder.load_model()

    async def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    async def pin_memories(self) -> list[MemoryRecord]:
        rows = self._conn().execute(
            """
            SELECT * FROM memory_items
            WHERE group_id = ? AND status = 'active' AND memory_type = 'pin'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (self.settings.group_id, self.settings.retrieval_limit),
        )
        return [_row_to_memory(row) for row in rows.fetchall()]

    async def recent_turns(self) -> list[ConversationTurn]:
        rows = self._conn().execute(
            """
            SELECT role, content, created_at FROM conversation_turns
            WHERE group_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (self.settings.group_id, self.settings.recent_turn_limit),
        )
        return [
            ConversationTurn(
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in reversed(rows.fetchall())
        ]

    async def search(self, queries: list[str], limit: int | None = None) -> list[MemoryRecord]:
        clean_queries = [query.strip() for query in queries if query.strip()]
        if not clean_queries:
            return []

        query_vectors = [await self.embedder.embed_query(query) for query in clean_queries]
        rows = self._conn().execute(
            """
            SELECT * FROM memory_items
            WHERE group_id = ? AND status = 'active' AND memory_type = 'long_term'
            """,
            (self.settings.group_id,),
        ).fetchall()

        scored: dict[str, MemoryRecord] = {}
        for row in rows:
            vector = _blob_to_vector(row["embedding"])
            score = max(_dot_product(query_vector, vector) for query_vector in query_vectors)
            record = _row_to_memory(row, score=score)
            existing = scored.get(record.id)
            if existing is None or (existing.score or 0) < score:
                scored[record.id] = record

        selected = sorted(
            scored.values(),
            key=lambda item: (item.score or 0, item.updated_at),
            reverse=True,
        )
        return selected[: limit or self.settings.retrieval_limit]

    async def add_memory(
        self,
        *,
        text: str,
        memory_type: str,
        source_message: str | None,
        valid_at: str | None = None,
        invalid_at: str | None = None,
    ) -> MemoryRecord:
        if memory_type not in {"pin", "long_term"}:
            raise ValueError("memory_type must be 'pin' or 'long_term'")
        now = self._now_text()
        memory_id = str(uuid4())
        embedding = await self.embedder.embed_document(text)
        self._conn().execute(
            """
            INSERT INTO memory_items (
                id, group_id, text, memory_type, status,
                source_message, created_at, updated_at, valid_at, invalid_at, embedding
            )
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                self.settings.group_id,
                text,
                memory_type,
                source_message,
                now,
                now,
                valid_at,
                invalid_at,
                _vector_to_blob(embedding),
            ),
        )
        self._conn().commit()
        return await self.get_memory(memory_id)  # type: ignore[return-value]

    async def supersede_memory(
        self,
        memory_id: str,
        *,
        replacement_text: str,
        memory_type: str,
        source_message: str | None,
    ) -> MemoryRecord | None:
        existing = await self.get_memory(memory_id)
        if existing is None or existing.status != "active":
            return None
        self._conn().execute(
            """
            UPDATE memory_items
            SET status = 'superseded', invalid_at = ?, updated_at = ?
            WHERE group_id = ? AND id = ? AND status = 'active'
            """,
            (self._now_text(), self._now_text(), self.settings.group_id, memory_id),
        )
        self._conn().commit()
        return await self.add_memory(
            text=replacement_text,
            memory_type=memory_type,
            source_message=source_message,
        )

    async def delete_memory(self, memory_id: str) -> bool:
        result = self._conn().execute(
            """
            UPDATE memory_items
            SET status = 'deleted', invalid_at = ?, updated_at = ?
            WHERE group_id = ? AND id = ? AND status = 'active'
            """,
            (self._now_text(), self._now_text(), self.settings.group_id, memory_id),
        )
        self._conn().commit()
        return result.rowcount > 0

    async def get_memory(self, memory_id: str) -> MemoryRecord | None:
        row = self._conn().execute(
            """
            SELECT * FROM memory_items
            WHERE group_id = ? AND id = ?
            """,
            (self.settings.group_id, memory_id),
        ).fetchone()
        return _row_to_memory(row) if row else None

    async def add_turn(self, role: str, content: str) -> None:
        self._conn().execute(
            """
            INSERT INTO conversation_turns (id, group_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid4()), self.settings.group_id, role, content, self._now_text()),
        )
        self._conn().commit()

    def _create_tables(self) -> None:
        self._conn().executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_items (
                id TEXT PRIMARY KEY,
                group_id TEXT NOT NULL,
                text TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                status TEXT NOT NULL,
                source_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                valid_at TEXT,
                invalid_at TEXT,
                embedding BLOB NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memory_group_status
            ON memory_items(group_id, status);

            CREATE INDEX IF NOT EXISTS idx_memory_group_type
            ON memory_items(group_id, memory_type, status);

            CREATE TABLE IF NOT EXISTS conversation_turns (
                id TEXT PRIMARY KEY,
                group_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_turns_group_created
            ON conversation_turns(group_id, created_at);
            """
        )
        self._conn().commit()

    def _conn(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("MemoryStore is not initialized")
        return self._connection

    def _now_text(self) -> str:
        now = self.now_factory()
        if now.tzinfo is None:
            now = now.replace(tzinfo=LOCAL_TZ)
        return now.astimezone(LOCAL_TZ).isoformat()


def _row_to_memory(row: sqlite3.Row, score: float | None = None) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"],
        text=row["text"],
        memory_type=row["memory_type"],
        status=row["status"],
        source_message=row["source_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        valid_at=row["valid_at"],
        invalid_at=row["invalid_at"],
        score=score,
    )


def _vector_to_blob(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _blob_to_vector(value: bytes) -> list[float]:
    return list(struct.unpack(f"{len(value) // 4}f", value))


def _dot_product(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _env_bool(name: str, default: bool) -> bool:
    value = getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
