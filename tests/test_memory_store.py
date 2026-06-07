import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from app.memory_store import MemorySettings, MemoryStore


class FakeEmbedder:
    def __init__(self):
        self.loaded = False
        self.documents: list[str] = []
        self.queries: list[str] = []

    async def load_model(self) -> None:
        self.loaded = True

    async def embed_document(self, text: str) -> list[float]:
        self.documents.append(text)
        return _vector_for(text)

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return _vector_for(text)


def test_initialize_tables_and_store_conversation_turns(tmp_path: Path) -> None:
    store = _store(tmp_path)

    async def run() -> None:
        await store.initialize()
        await store.add_turn("user", "hello")
        await store.add_turn("assistant", "hi")

        turns = await store.recent_turns()

        assert [(turn.role, turn.content) for turn in turns] == [
            ("user", "hello"),
            ("assistant", "hi"),
        ]
        assert tmp_path.joinpath("memory.sqlite").exists()
        await store.close()

    asyncio.run(run())


def test_create_memory_stores_text_metadata_and_embedding(tmp_path: Path) -> None:
    embedder = FakeEmbedder()
    store = _store(tmp_path, embedder=embedder)

    async def run() -> None:
        await store.initialize()
        record = await store.add_memory(
            text="User prefers black coffee while coding.",
            memory_type="long_term",
            source_message="I like black coffee when coding.",
        )

        saved = await store.get_memory(record.id)

        assert saved is not None
        assert saved.text == "User prefers black coffee while coding."
        assert saved.memory_type == "long_term"
        assert saved.status == "active"
        assert embedder.documents == ["User prefers black coffee while coding."]
        await store.close()

    asyncio.run(run())


def test_vector_search_retrieves_paraphrased_relevant_memory(tmp_path: Path) -> None:
    store = _store(tmp_path)

    async def run() -> None:
        await store.initialize()
        await store.add_memory(
            text="User prefers black coffee while coding.",
            memory_type="long_term",
            source_message=None,
        )
        await store.add_memory(
            text="User likes quiet rooms for deep work.",
            memory_type="long_term",
            source_message=None,
        )

        results = await store.search(["coding drink preference"], limit=1)

        assert [item.text for item in results] == [
            "User prefers black coffee while coding."
        ]
        assert results[0].score is not None
        await store.close()

    asyncio.run(run())


def test_pin_memories_are_loaded_without_search(tmp_path: Path) -> None:
    store = _store(tmp_path)

    async def run() -> None:
        await store.initialize()
        await store.add_memory(
            text="User wants concise answers.",
            memory_type="pin",
            source_message=None,
        )
        await store.add_memory(
            text="User prefers black coffee while coding.",
            memory_type="long_term",
            source_message=None,
        )

        pins = await store.pin_memories()

        assert [item.text for item in pins] == ["User wants concise answers."]
        await store.close()

    asyncio.run(run())


def test_supersede_and_delete_memory_update_status(tmp_path: Path) -> None:
    store = _store(tmp_path)

    async def run() -> None:
        await store.initialize()
        old = await store.add_memory(
            text="User prefers black coffee while coding.",
            memory_type="long_term",
            source_message=None,
        )

        replacement = await store.supersede_memory(
            old.id,
            replacement_text="User now prefers hot tea while coding.",
            memory_type="long_term",
            source_message="I switched to hot tea.",
        )

        old_after = await store.get_memory(old.id)
        assert replacement is not None
        assert replacement.memory_type == "long_term"
        assert old_after is not None
        assert old_after.status == "superseded"
        assert old_after.invalid_at is not None

        assert await store.delete_memory(replacement.id) is True
        deleted = await store.get_memory(replacement.id)
        assert deleted is not None
        assert deleted.status == "deleted"
        assert await store.delete_memory("missing") is False
        await store.close()

    asyncio.run(run())


def _store(tmp_path: Path, embedder: FakeEmbedder | None = None) -> MemoryStore:
    now_values = _clock()
    return MemoryStore(
        MemorySettings(
            llm_base_url="http://testserver/v1",
            llm_api_key="test-key",
            llm_model="gemini-test",
            group_id="test-group",
            db_path=tmp_path / "memory.sqlite",
            embedding_model="fake",
            embedding_dim=3,
            embedding_preload=True,
            recent_turn_limit=10,
            retrieval_limit=10,
        ),
        embedder=embedder or FakeEmbedder(),
        now_factory=lambda: next(now_values),
    )


def _clock():
    current = datetime.fromisoformat("2026-06-06T12:00:00+07:00")
    while True:
        yield current
        current += timedelta(seconds=1)


def _vector_for(text: str) -> list[float]:
    normalized = text.lower()
    if any(token in normalized for token in ("coffee", "drink", "coding")):
        return [1.0, 0.0, 0.0]
    if "tea" in normalized:
        return [0.0, 1.0, 0.0]
    if any(token in normalized for token in ("quiet", "room")):
        return [0.0, 0.0, 1.0]
    return [0.3, 0.3, 0.3]
