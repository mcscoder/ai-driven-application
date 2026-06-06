from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.graphiti_client import GraphitiMemory, GraphitiSettings
from app.llm_client import AssistantClient
from app.schemas import ChatRequest, ChatResponse

load_dotenv()

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = GraphitiSettings.from_env()
    memory = GraphitiMemory(settings)
    await memory.initialize()

    app.state.settings = settings
    app.state.memory = memory
    app.state.assistant = AssistantClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        memory_write_mode=settings.memory_write_mode,
        max_tool_iterations=settings.agent_max_tool_iterations,
    )

    try:
        yield
    finally:
        await memory.close()


app = FastAPI(title="Graphiti Chat Lab", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    message = payload.message.strip()
    memory: GraphitiMemory = request.app.state.memory
    assistant: AssistantClient = request.app.state.assistant

    result = await assistant.reply(message, memory)
    return ChatResponse(
        reply=result.reply,
        retrieved_facts=result.retrieved_facts,
        tool_trace=result.tool_trace,
    )
