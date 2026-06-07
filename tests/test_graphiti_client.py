import asyncio
from datetime import timezone
from types import SimpleNamespace
from typing import Any

from app.graphiti_client import GraphitiMemory


class FakeDriver:
    def __init__(self):
        self.queries: list[tuple[str, dict[str, Any]]] = []

    async def execute_query(self, query: str, **params: Any):
        self.queries.append((query, params))
        return []


class FakeGraphitiClient:
    def __init__(self):
        self.driver = FakeDriver()
        self.episodes: list[dict[str, Any]] = []

    async def add_episode(self, **kwargs: Any) -> None:
        self.episodes.append(kwargs)


def test_add_memory_fact_writes_companion_memory_and_utc_episode() -> None:
    memory = object.__new__(GraphitiMemory)
    memory.settings = SimpleNamespace(group_id="test-group", retrieval_limit=6)
    memory.client = FakeGraphitiClient()

    asyncio.run(memory.add_memory_fact("Người dùng thích cà phê đen."))

    companion_params = memory.client.driver.queries[0][1]
    assert companion_params["group_id"] == "test-group"
    assert companion_params["text"] == "Người dùng thích cà phê đen."
    assert companion_params["kind"] == "preference"
    assert companion_params["pinned"] is False
    assert "COMPANION_MEMORY" in memory.client.driver.queries[0][0]

    reference_time = memory.client.episodes[0]["reference_time"]
    assert reference_time.tzinfo == timezone.utc
    assert reference_time.utcoffset().total_seconds() == 0
