# Memory Runtime Rebuild Plan

This document is the source of truth for the next implementation pass. It
supersedes the older recommendation in `docs/memory_eval_handoff.md` that said
to keep Graphiti and add a companion layer.

## Why This Rebuild Exists

The current implementation is not acceptable as an AI agent driven memory
system.

It improved eval numbers by adding keyword-heavy fallback logic, but that is
the wrong direction for the product. The problematic runtime patterns include:

- hardcoded broad queries such as `sở thích của user`, `rau mùi`, `cà phê`,
  `cảm xúc`, `người liên quan`;
- memory-question detection by Vietnamese keyword tuples;
- companion memory search using token `CONTAINS` instead of semantic retrieval;
- marker-based memory classification and pinning;
- tests that assert those hardcoded fallback strings instead of validating
  agent reasoning.

The result is a patched keyword memory system wrapped in an agent loop. It is
not a real agent-driven memory runtime and should not be extended.

## Product Direction

Build a natural Vietnamese companion-style assistant with durable memory. The
assistant should remember facts, preferences, corrections, relationships,
project context, and support style from normal conversation, then recall them
when semantically relevant.

The system should be debuggable through traces, but it must not encode product
semantics in backend keyword lists. The LLM should make semantic decisions. Code
should handle deterministic storage, retrieval mechanics, schemas, and trace
recording.

Do not optimize the rebuild to pass the old keyword-patched eval style. Cases
should look like real conversations and should not encode backend keyword
expectations as product truth.

## Keep

- Keep the public API shape:
  - `POST /api/chat`
  - response fields: `reply`, `retrieved_facts`, `tool_trace`
- Keep FastAPI and the existing HTML UI unless the implementation truly needs
  a small UI trace adjustment.
- Keep `uv` as the only Python environment/dependency command.
- Keep local embedding support through `sentence-transformers`.
- Keep generated eval reports ignored.

## Remove From Runtime

Remove these from the active runtime path:

- Graphiti runtime dependency and Neo4j-backed memory path.
- `GraphitiMemory` as the memory implementation used by `app.main`.
- Graphiti-specific settings as required startup config.
- hardcoded broad query expansion;
- `_looks_like_memory_question`;
- companion memory token `CONTAINS` search;
- marker-based `_classify_companion_memory`;
- tests whose purpose is to preserve hardcoded query strings.

It is acceptable to leave old files temporarily if import paths are no longer
used and tests no longer depend on them. Prefer deleting dead runtime code once
the new path is stable.

## New Architecture

### Memory Store

Implement a local SQLite memory store. Default path:

```sh
MEMORY_DB_PATH=.data/memory.sqlite
```

Use `MEMORY_GROUP_ID` for namespace. For compatibility, if it is absent, fall
back to `GRAPHITI_GROUP_ID`, then `chat-lab`.

Minimum tables:

```text
memory_items
- id TEXT primary key
- group_id TEXT not null
- text TEXT not null
- memory_type TEXT not null
- status TEXT not null
- source_message TEXT
- created_at TEXT not null
- updated_at TEXT not null
- valid_at TEXT
- invalid_at TEXT
- embedding BLOB not null

conversation_turns
- id TEXT primary key
- group_id TEXT not null
- role TEXT not null
- content TEXT not null
- created_at TEXT not null
```

Allowed values:

```text
memory_type:
- pin
- long_term

status:
- active
- superseded
- deleted
```

There are only two memory types. `pin` is always injected into answer context.
`long_term` is retrieved by semantic search and selected by the LLM.

### Embeddings

Use local embeddings by default:

```sh
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
EMBEDDING_DIM=1024
EMBEDDING_PRELOAD=true
```

Store normalized float32 vectors as SQLite BLOBs. For v1, vector search can be
done in Python by loading active rows for the group and computing dot product.
This is acceptable for personal memory scale and much easier to debug than
introducing another vector database.

### LLM Runtime Pipeline

Each `/api/chat` request should run this pipeline:

1. Load recent conversation turns and active `memory_type=pin` memories.
2. Ask the LLM planner for a structured memory plan:
   - whether memory is needed;
   - one to three semantic search queries if needed;
   - a short reason.
3. If memory is needed, embed the planner queries and retrieve candidate
   memories by vector similarity.
4. Ask the LLM selector to choose only memories that directly help answer the
   current user message.
5. Generate the final answer using:
   - current user message;
   - recent turns;
   - pinned memories;
   - selected memories.
6. Ask the LLM curator for memory write operations grounded only in the current
   user message and the selected/recent context.
7. Persist conversation turn and memory operations before returning.

### LLM Contracts

Use structured JSON responses for planner, selector, and curator. Validate them
with Pydantic models.

Planner output:

```json
{
  "needs_memory": true,
  "queries": ["semantic query 1", "semantic query 2"],
  "reason": "short reason"
}
```

Selector output:

```json
{
  "selected_ids": ["memory-id-1"],
  "rejected_ids": ["memory-id-2"],
  "reason": "short reason"
}
```

Curator output:

```json
{
  "operations": [
    {
      "op": "create",
      "text": "durable memory text",
      "memory_type": "long_term",
      "replaces_id": null
    }
  ]
}
```

Allowed curator ops:

```text
create
supersede
delete
ignore
```

Rules:

- The curator must not save facts inferred only from the assistant reply.
- A supersede/delete operation must reference an existing memory id.
- The backend must ignore invalid operations instead of inventing missing ids.
- Final answers must not use rejected candidate memories.

### Tool Trace

Keep `tool_trace`, but use it for pipeline trace instead of Graphiti tool calls.
At minimum include:

- planner decision and query count;
- search candidate count;
- selector selected/rejected count;
- curator operation count;
- any skipped invalid operation.

The trace should make a failed answer diagnosable without reading server logs.

## Hard Rules For The Rebuild

- Do not add semantic keyword lists to decide whether something is a memory
  question.
- Do not add broad fallback strings for specific eval topics.
- Do not use token `CONTAINS` as the main memory retrieval path.
- Do not preserve Graphiti/Neo4j just because it exists.
- Do not let the legacy eval dictate unnatural product behavior.
- Do not silently hide planner/search/selector failures from `tool_trace`.

Small deterministic checks are fine when they are infrastructure-level, such as
schema validation, SQLite status filtering, vector dimension checks, and
timestamp parsing.

## Implementation Order

1. Add the SQLite memory store and local embedder wrapper.
2. Add structured LLM helper functions for planner, selector, curator, and final
   answer generation.
3. Replace `app.main` startup to initialize the new memory runtime instead of
   Graphiti.
4. Replace the old `AssistantClient` behavior with the pipeline above.
5. Rewrite unit tests around the new contracts.
6. Remove the old eval suite and add natural-conversation target and smoke
   suites.
7. Run tests and a small smoke run before any full LLM-judged eval.

## Test Plan

Required unit tests:

- SQLite initializes tables and stores conversation turns.
- Memory create stores text, metadata, and embedding.
- Vector search retrieves a paraphrased relevant memory.
- Planner says no memory needed, so no vector search runs.
- Planner says memory needed, candidates are retrieved and selector filters
  them before answer.
- Pin memories are included every turn without keyword pinning.
- Curator creates a new memory from a durable user statement.
- Curator supersedes an existing memory by id.
- Invalid curator ops are ignored and traced.
- No runtime test asserts hardcoded broad query strings.

Required non-network checks:

```sh
UV_CACHE_DIR=.uv-cache uv run pytest
UV_CACHE_DIR=.uv-cache uv run python evals/run_live_eval.py --dry-run
```

Recommended smoke checks when quota is available:

- User states a preference, then asks a paraphrased follow-up.
- User corrects an old preference, then asks again.
- User asks a general coding/translation/math question and memory is not used.
- User states conversational style preference and the assistant applies it later.
- Trace shows planner, search, selector, and curator steps clearly.

## Eval Direction

Do not use the removed 70-case suite as the demo-readiness verdict.

Create a new natural smoke suite where seed and probe messages look like real
chat, not artificial exam questions. The new suite should test:

- everyday preferences;
- project context;
- social/person memory;
- emotional/support continuity;
- correction/update;
- no-memory general questions.

Judge quality by:

- whether the answer is useful in conversation;
- whether selected memories are directly relevant;
- whether irrelevant memories are rejected;
- whether corrections replace old memories;
- whether trace explains the decision path.

## Notes For Future Agents

- The user explicitly rejected the keyword-patched direction. Do not reintroduce
  it under a different name.
- The user has already committed and pushed the current work, so the old code is
  available from git history if needed.
- If implementation gets hard, reduce scope by keeping fewer memory fields or a
  smaller eval, not by re-adding hardcoded semantic fallbacks.
- Quality matters more than protecting the current Graphiti implementation.
