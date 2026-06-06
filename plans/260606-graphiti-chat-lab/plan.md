  # Graphiti Chat Lab

  ## Summary

  Build a standalone Python FastAPI web chat app to test Graphiti memory retrieval with Neo4j and Gemini.

  Goal:

  Browser chat
  → Graphiti search
  → Gemini response
  → Graphiti episode storage
  → visible retrieved facts

  ## Stack

  Python
  FastAPI
  Graphiti
  Neo4j
  Gemini through existing OpenAI-compatible cli proxy

  Embedding:

  Use proxy embeddings if /v1/embeddings exists.
  Otherwise use Graphiti Gemini embedder.

  ## Project Structure

  graphiti-chat-lab/
    pyproject.toml
    .env.example
    app/
      main.py
      graphiti_client.py
      llm_client.py
      schemas.py
      templates/
        index.html

  ## Environment

  NEO4J_URI=bolt://localhost:7687
  NEO4J_USER=neo4j
  NEO4J_PASSWORD=password

  LLM_BASE_URL=http://127.0.0.1:<proxy-port>/v1
  LLM_API_KEY=dummy
  LLM_MODEL=gemini-2.5-flash
  LLM_SMALL_MODEL=gemini-2.5-flash

  EMBEDDING_MODE=proxy
  EMBEDDING_MODEL=<embedding-model-if-proxy-supports-it>
  GOOGLE_API_KEY=

  ## API

  GET /

  Serve browser chat UI.

  POST /api/chat

  Request:

  {
    "message": "string"
  }

  Response:

  {
    "reply": "string",
    "retrieved_facts": [
      {
        "fact": "string",
        "valid_at": "string|null",
        "invalid_at": "string|null",
        "score": "number|null"
      }
    ]
  }

  ## Runtime Flow

  Startup:

  initialize Graphiti
  connect to Neo4j
  build indices and constraints

  Chat request:

  receive message
  search Graphiti with message
  format retrieved facts as context
  call Gemini through cli proxy
  store message as Graphiti episode
  store assistant reply as Graphiti episode
  return reply and retrieved facts

  The UI must show retrieved facts separately from the assistant reply.

  Check chat endpoint:

  curl http://127.0.0.1:<proxy-port>/v1/chat/completions

  Check embedding endpoint:

  curl http://127.0.0.1:<proxy-port>/v1/embeddings

  If embeddings are unavailable through the proxy, configure Gemini embedding directly.

  ## Manual Eval Cases

  Seed:

  Minh nợ tao 60k
  Tao nợ Nam 30k
  Có lịch chơi game với anh Tú lúc 3h chiều mai
  Tao thích quán cà phê yên tĩnh để làm việc

  Ask:

  Ai nợ tao tiền?
  Tao nợ ai?
  Mai tao có gì?
  Tao thích kiểu quán nào?

  Pass criteria:

  retrieved_facts contains the relevant fact/event
  retrieved_facts does not contain contradictory wrong-direction facts
  assistant answer is grounded in retrieved_facts

  Fail criteria:

  retrieved_facts is empty for recall questions
  retrieved_facts contains the wrong-direction debt
  assistant answer is plausible but not grounded in retrieved_facts

  ## Decision Point

  If the lab retrieves Vietnamese facts/events reliably, proceed with deeper Graphiti experiments.

  If retrieval is poor, tune provider config, embedding model, custom entities, and extraction behavior before building on it.