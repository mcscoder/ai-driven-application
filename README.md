# Graphiti Chat Lab

Standalone FastAPI chat app for testing a Vietnamese companion assistant with
durable local memory.

The active runtime uses SQLite plus local sentence-transformer embeddings. The
old Graphiti/Neo4j path is no longer used by `/api/chat`.

Runtime memory has only two types:

- `pin`: always included in answer context.
- `long_term`: retrieved semantically when relevant.

## Setup

```sh
cp .env.example .env
UV_CACHE_DIR=.uv-cache uv sync
```

## App Configuration

Edit `.env` for your LLM proxy. `LLM_BASE_URL` must include `/v1`.

Memory defaults:

```sh
MEMORY_DB_PATH=.data/memory.sqlite
MEMORY_GROUP_ID=chat-lab
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
EMBEDDING_DIM=1024
EMBEDDING_PRELOAD=true
```

If `MEMORY_GROUP_ID` is absent, the app falls back to `GRAPHITI_GROUP_ID`, then
`chat-lab`, so older eval scripts can still isolate runs.

The first local embedding run downloads model files into
`.hf-cache/sentence-transformers/`. Set `EMBEDDING_PRELOAD=false` to skip startup
loading and lazy-load the model on the first memory operation.

## Run

```sh
./run.sh
```

Open http://127.0.0.1:8000.

## API

```sh
curl -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Tối nay code thì nên uống gì?"}'
```

The response keeps the public shape:

- `reply`: assistant answer.
- `retrieved_facts`: selected memories used as grounding context.
- `tool_trace`: planner/search/selector/curator pipeline trace.
