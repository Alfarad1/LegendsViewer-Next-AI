# LegendsViewer.AI

Python FastAPI service that answers “tell me about X” questions for Sites, Historical Figures, and Entities via LangChain tool-calling against the LegendsViewer REST API.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness + configured model name |
| `POST` | `/chat` | SSE chat stream (`token`, `status`, `done`, `error`) |

## Configuration

Copy `.env.example` to `.env` (or set compose env vars):

| Variable | Example | Notes |
|----------|---------|-------|
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Use `http://host.docker.internal:11434/v1` for Ollama |
| `OPENAI_API_KEY` | `sk-...` | Use any non-empty value for Ollama |
| `OPENAI_MODEL` | `gpt-4o-mini` | Or a local model name |
| `LV_API_BASE_URL` | `http://legendsviewer:15421` | Backend URL inside Docker |

## Local run (without Docker)

```bash
cd LegendsViewer.AI
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=...
export LV_API_BASE_URL=http://localhost:15421
uvicorn app.main:app --host 0.0.0.0 --port 15423 --reload
```

## Docker Compose

```bash
OPENAI_API_KEY=sk-... docker compose up --build
```

AI listens on **http://localhost:15423**. Frontend chat page: **/chat**.

On Linux the AI container uses `network_mode: host` so it can call a local Ollama bound to `127.0.0.1`. Put `OPENAI_BASE_URL=http://127.0.0.1:11434/v1` in `.env`.
