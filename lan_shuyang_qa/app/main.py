"""HTTP API owned by the QA-agent component; presentation/UI is external."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.orchestrator import ThreatQAOrchestrator
from app.schemas import ChatResponse, SearchRequest

app = FastAPI(title="CTI Multi-Agent QA", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # UI integration member should restrict this for production.
    allow_methods=["*"],
    allow_headers=["*"],
)
orchestrator = ThreatQAOrchestrator()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "lan_shuyang_qa"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: SearchRequest) -> ChatResponse:
    return await orchestrator.chat(request)
