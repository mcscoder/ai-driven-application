# Graphiti Chat Lab

Standalone FastAPI chat app for testing Graphiti memory retrieval with Neo4j and Gemini through an OpenAI-compatible `cliproxy`.

## Setup

```sh
cp .env.example .env
UV_CACHE_DIR=.uv-cache uv sync
```

## Neo4j Installation

Reference: [Neo4j Debian-based installation docs](https://neo4j.com/docs/operations-manual/current/installation/linux/debian/).

These commands install Neo4j Community Edition on Debian or Ubuntu with OpenJDK Java 21.

### Step 1: OpenJDK Java 21

Install the Java 21 JDK required by Neo4j:

```sh
sudo apt install openjdk-21-jdk
```

Select Java 21 as the default Java runtime when multiple Java versions are installed:

```sh
sudo update-alternatives --config java
```

### Step 2: Add the Neo4j Repository

Create the APT keyrings directory if it does not already exist:

```sh
sudo mkdir -p /etc/apt/keyrings
```

Download the Neo4j GPG key and store it in APT's keyring format so packages from the Neo4j repository can be verified:

```sh
wget -O - https://debian.neo4j.com/neotechnology.gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/neotechnology.gpg > /dev/null
```

Make the Neo4j GPG key readable by APT:

```sh
sudo chmod a+r /etc/apt/keyrings/neotechnology.gpg
```

Add the Neo4j APT repository as a package source:

```sh
echo 'deb [signed-by=/etc/apt/keyrings/neotechnology.gpg] https://debian.neo4j.com stable latest' | sudo tee -a /etc/apt/sources.list.d/neo4j.list > /dev/null
```

Refresh local package lists so APT can see Neo4j packages:

```sh
sudo apt-get update
```

List available Neo4j versions before installing:

```sh
apt list -a neo4j
```

### Step 3: Install Neo4j

Install Neo4j Community Edition pinned to version `2026.05.0`:

```sh
sudo apt-get install neo4j=1:2026.05.0
```

### Step 4: Validate and Configure the Service

Check the current Neo4j service state:

```sh
sudo systemctl status neo4j
```

Start the Neo4j service if inactive:

```sh
sudo systemctl start neo4j
```

Enable Neo4j to start automatically after reboot:

```sh
sudo systemctl enable neo4j
```

## App Configuration

Edit `.env` for your Neo4j and `cliproxy` ports. `LLM_BASE_URL` must include `/v1`.

Use local Qwen3 embeddings when you want Graphiti embeddings without a Google API key:

```sh
EMBEDDING_MODE=local
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
EMBEDDING_DIM=1024
EMBEDDING_PRELOAD=true
```

The first local embedding run downloads model files into `.hf-cache/`.
Set `EMBEDDING_PRELOAD=false` to skip startup loading and lazy-load the model on the first request.

The chat endpoint uses Gemini function calling to let the model decide when to
search, save, or cancel memory before answering. Memory writes triggered by the
agent are awaited before the API response is returned.

Choose which write tools the model can use:

```sh
MEMORY_WRITE_MODE=both
```

Supported values:

- `exact`: store only the exact current user message.
- `model`: store only model-authored memory facts derived from the user message.
- `both`: expose both write tools.

Cap the number of function-calling rounds per request:

```sh
AGENT_MAX_TOOL_ITERATIONS=6
```

The older background ingest setting is kept for compatibility with earlier lab
flows, but `/api/chat` now relies on synchronous agent tool writes:

```sh
MEMORY_INGEST_BACKGROUND=true
```

Use proxy embeddings when `cliproxy` supports `/v1/embeddings`:

```sh
EMBEDDING_MODE=proxy
EMBEDDING_MODEL=<proxy-embedding-model>
```

Use Gemini embeddings directly when proxy embeddings are unavailable:

```sh
EMBEDDING_MODE=gemini
EMBEDDING_MODEL=text-embedding-001
GOOGLE_API_KEY=...
```

## Run

```sh
./run.sh
```

Open http://127.0.0.1:8000.

## API

```sh
curl -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Ai no tao tien?"}'
```

The response includes the assistant reply, `retrieved_facts` used as grounding
context, and `tool_trace` showing memory tool calls made for the answer.
