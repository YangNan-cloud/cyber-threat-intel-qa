# AGENTS.md

Chinese-language team project "网络开源威胁情报智能问答系统". This repo holds **one member's slice** (兰书阳's QA backend) plus a dataset folder — not the whole system.

## Repo layout (what actually lives here)

- `lan_shuyang_qa/` — the only runnable code: a FastAPI multi-agent QA service (问答后端).
- `dataset/` — **output artifacts only**: `cti_200_dataset.jsonl` (raw), `annotated_dataset.jsonl`, `kg_nodes.csv`, `kg_edges.csv`. The annotation scripts (`annotate.py`, `climb.py`) referenced in `dataset/README.md` are **not tracked in git**.
- Root `README.md` is a stub (技术栈/运行方式 sections are empty). The per-directory READMEs are the real docs.

Components owned by other members (retrieval service, data collection, eval reports, Streamlit UI) live in **other repos** and are absent here.

## Commands (run from `lan_shuyang_qa/`)

`app` is a plain package with **no install step** (`from app...` imports need cwd = `lan_shuyang_qa/`). No setup.py / pyproject / pytest.ini. Tests use `unittest`, not pytest.

```bash
cd lan_shuyang_qa
cp .env.example .env          # then set DEEPSEEK_API_KEY
pip install -r requirements.txt
python run.py                 # uvicorn, reload=True, default 127.0.0.1:8000
```

- Health check: `GET http://127.0.0.1:8000/health`; main endpoint: `POST /api/chat`.
- Test: `python -m unittest discover -s tests` — NOT `python -m unittest tests.test_safety` (the `tests/` dir has no `__init__.py`, so the dotted path fails).
- Local retrieval stub for contract testing: `python tests/mock_retrieval_service.py` (serves `127.0.0.1:8001`).
- Eval (stdlib-only): `python eval/evaluate_qa.py <file.jsonl>` and `python eval/evaluate_retrieval.py <file.jsonl> --k 5`.

## Config quirks

- **No `python-dotenv`.** `app/config.py` has a hand-rolled loader that reads `lan_shuyang_qa/.env` (NOT repo root) and uses `os.environ.setdefault` — real environment variables take precedence over `.env`.
- `run.py` imports `app.config` on line 1 specifically so `.env` is loaded before other modules; keep that ordering.
- `.env` is gitignored; `.env.example` is the template. Keys: `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`, `RETRIEVAL_URL`, `CONFIDENCE_THRESHOLD`, `HOST`, `PORT`.

## Runtime behavior / external dependency

- `/api/chat` depends on an **external retrieval service** at `RETRIEVAL_URL` (default `http://127.0.0.1:8001/search`), which is NOT in this repo. `RetrievalAgent` swallows HTTP errors and returns `[]` → `SafetyAgent` then returns `refusal=true`, so without the retrieval service the endpoint always refuses.
- `DEEPSEEK_API_KEY` is optional. If unset or the call fails, `AnswerAgent` returns a degraded evidence-excerpt answer instead of an LLM answer.

## Architecture (multi-agent pipeline)

`app/orchestrator.py` `ThreatQAOrchestrator.chat()` wires four agents in order:
`RetrievalAgent` (fetch) → `AttributionAgent` (conservative actor attribution, needs ≥2 corroborating sources + graph paths) → `SafetyAgent` (confidence score + refusal gate) → `AnswerAgent` (LLM or fallback).

The retrieval-service contract and `/api/chat` response shape are documented in `lan_shuyang_qa/README.md` — read that before changing schemas (`app/schemas.py`) or agent behavior.

## Conventions

- **Language**: code comments, docstrings, READMEs, and all client-facing answers/refusal text are Chinese. Match it.
- No CI, linter, formatter, or typecheck config exists. Only stdlib + the 5 deps in `requirements.txt` (fastapi, uvicorn, httpx, pydantic, python-multipart).
