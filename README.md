# Deep Research Agent

**English** · [简体中文](README.zh-CN.md)

A self-hostable **deep research assistant**: give it a question, and a single autonomous agent searches the web, fetches and summarizes sources, reads PDFs (text **and** figures), cites what it found, and can turn the result into an **interactive React visualization** — all on top of a **project-scoped memory stack** that lets each research project remember facts, conclusions, and your preferences across sessions.

Built with **FastAPI** + **[claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-python)**, powered by **Kimi** (Moonshot's Anthropic-compatible endpoint), with a **React + Vite + TypeScript** web UI.

> The agent SDK runs against an Anthropic-compatible API. This project points it at **Kimi (Moonshot)**, but any Anthropic-compatible endpoint can be configured via `.env`.

<p align="center">
  <img src="assets/screenshots/artifact.png" alt="Deep Research Agent — chat on the left, a live interactive React artifact on the right" width="100%">
  <br/>
  <em>Ask on the left; the agent researches, then renders a live, interactive React visualization on the right.</em>
</p>

---

## ✨ Features

- **Autonomous web research** — `web_search`, `web_search_and_fetch`, and Google Scholar search via [Serper](https://serper.dev); pages are extracted with readability and summarized by the model, with sources tracked and surfaced in the UI.
- **PDF reading with vision** — download a PDF, parse it to Markdown (via a [MinerU](https://github.com/opendatalab/MinerU) service), then `pdf_read` (paginated), `pdf_grep` (regex), and `pdf_vision` (ask questions about figures/charts using a multimodal model).
- **Interactive artifacts** — the agent can generate a single-file, interactive **React component** (charts via `recharts`, icons via `lucide-react`), validated with an esbuild compile loop and rendered live in the browser sandbox.
- **Project-scoped memory** — after every turn the conversation is segmented by topic, summarized (episodic memory), and mined for facts (mem0-style `ADD`/`UPDATE`/`DELETE`). Retrieval is task-aware and weighted by importance, recency decay, access frequency, category, and optional semantic similarity.
- **Folders & organization** — group projects into a hierarchical folder tree, or let the agent **suggest** a structure across all your projects and apply it in bulk.
- **Streaming UI** — chat responses, tool activity, sources, and artifacts stream over SSE in real time.

---

## 📸 Screenshots

<table>
  <tr>
    <td width="50%">
      <img src="assets/screenshots/research.png" alt="Autonomous research with a live tool trail and a sources panel"><br/>
      <sub><b>Autonomous research</b> — a live tool trail (search · fetch · PDF) while the <b>sources panel</b> fills as the agent browses.</sub>
    </td>
    <td width="50%">
      <img src="assets/screenshots/memory.png" alt="Project-scoped memory panel"><br/>
      <sub><b>Project-scoped memory</b> — semantic / episodic / procedural / preference facts, each with an importance score, editable inline.</sub>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <img src="assets/screenshots/organize.png" alt="AI-suggested folder organization modal"><br/>
      <sub><b>Folders &amp; smart organize</b> — group projects into a folder tree, or let the agent propose a structure and apply it in bulk.</sub>
    </td>
    <td width="50%">
      <img src="assets/screenshots/welcome.png" alt="Welcome screen with sidebar, folders and feature overview"><br/>
      <sub><b>At a glance</b> — a clean, streaming UI with sidebar projects, a folder tree, and a feature overview.</sub>
    </td>
  </tr>
  <tr>
    <td colspan="2">
      <img src="assets/screenshots/figures.png" alt="Answer with PDF figures rendered inline alongside the text"><br/>
      <sub><b>PDF reading with inline figures</b> — the agent reads a paper (text <b>and</b> charts via <code>pdf_vision</code>) and weaves the original figures back into its answer, interleaved with prose and captions.</sub>
    </td>
  </tr>
</table>

> Screenshots are from a self-hosted instance; sample projects are illustrative.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (React + Vite + TS)                                │
│  Chat · Artifacts (sandbox) · Memory panel · Folders · Sources│
└───────────────┬─────────────────────────────────────────────┘
                │ REST + SSE  (/api/*)
┌───────────────▼─────────────────────────────────────────────┐
│  FastAPI (main.py)                                            │
│  routes: projects · chat · artifacts · folders               │
└───────────────┬─────────────────────────────────────────────┘
                │
     ┌──────────▼──────────┐        ┌──────────────────────────┐
     │  Agent (orchestrator)│        │  Memory pipeline          │
     │  claude-agent-sdk    │◄──────►│  segment → summarize →    │
     │  + Kimi (Anthropic   │ context│  extract facts → embed →  │
     │    compatible)       │        │  schedule / decay         │
     └──────────┬───────────┘        └──────────────┬───────────┘
                │ MCP server "research-tools"        │
     ┌──────────▼───────────────────────────┐       │
     │  Tools: web · pdf · memory · artifact │       │
     └───────────────────────────────────────┘       │
                                                      │
            ┌─────────────────────────────────────────▼───────┐
            │  SQLite (SQLAlchemy async)                        │
            │  projects · folders · conversations · artifacts · │
            │  memories                                         │
            └──────────────────────────────────────────────────┘
```

- **Single-agent design.** One orchestrator (`agents/orchestrator.py`) drives the whole research loop via the Agent SDK — no sub-agent fan-out — with tools exposed through an MCP server named `research-tools`.
- **Helper LLM calls** (summaries, fact extraction, titles) use a lightweight async client (`agents/kimi_anthropic.py`), often on a faster/cheaper model than the main research model.
- **SDK isolation.** The SDK subprocess writes transcripts to a repo-local `CLAUDE_CONFIG_DIR` so it never pollutes your machine's `~/.claude`.

### Tech stack

| Layer | Stack |
|-------|-------|
| Backend | Python, FastAPI, Uvicorn, claude-agent-sdk, SQLAlchemy 2.0 (async, aiosqlite), pydantic-settings |
| Model | Kimi K2.5 / K2-turbo via Moonshot (Anthropic-compatible); embeddings via Aliyun DashScope (`text-embedding-v4`) |
| Search / fetch | Serper API, readability-lxml, markdownify; optional Firecrawl fallback |
| PDF | MinerU parse service + Kimi multimodal vision |
| Frontend | React, Vite, TypeScript, recharts, lucide-react, react-markdown, KaTeX |

---

## 📂 Project structure

```
.
├── main.py              # FastAPI entrypoint (routers, CORS, startup)
├── config.py            # Settings (pydantic-settings, reads .env)
├── agents/
│   ├── orchestrator.py  # single-agent research loop (sync + SSE stream)
│   ├── base.py          # ClaudeAgentOptions, prompt loading, time block
│   ├── kimi_anthropic.py# lightweight Kimi client for helper calls
│   ├── mcp_registry.py  # exposes the "research-tools" MCP server
│   ├── multimodal/      # PDF-image → vision message builders
│   └── tools/           # web / pdf / memory / artifact tools
├── api/routes/          # projects · chat · artifacts · folders
├── memory/              # segment · summarize · extract · embed · schedule
├── db/                  # SQLAlchemy models, crud, async engine + migrations
├── schemas/             # Pydantic request/response models
├── prompts/             # system prompts (Markdown)
├── scripts/             # verify_import.py (smoke check)
└── frontend/            # React + Vite + TypeScript UI
```

---

## 🚀 Quick start

### Prerequisites

- Python **3.10+**
- Node.js **≥ 20.19** (Vite) — [nvm](https://github.com/nvm-sh/nvm) recommended
- API keys: **Kimi/Moonshot** (required), **Serper** (required for web search), **DashScope** (optional, for semantic memory)
- *(Optional)* A **[MinerU](https://github.com/opendatalab/MinerU)** parsing service if you want PDF reading

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env: ANTHROPIC_AUTH_TOKEN, SERPER_API_KEY, EMBEDDING_MODEL_API_KEY, ...
```

See [Configuration](#-configuration) for the variables that matter most.

### 2. Backend

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
npm install                          # root esbuild — required for interactive artifacts
python scripts/verify_import.py      # should print: OK <APP_TITLE>
python main.py
```

- Listens on `API_HOST:API_PORT` (default `0.0.0.0:8808`).
- API docs: <http://127.0.0.1:8808/docs>
- The root `npm install` provides the `esbuild` used to validate generated React artifacts; skip it only if you don't need artifacts.

### 3. Frontend

```bash
cd frontend
npm ci
npm run dev
```

- Dev server port: `VITE_DEV_PORT` (default **3020**) in `frontend/.env.development`.
- `/api` is proxied to `http://127.0.0.1:<VITE_API_PORT>` — keep `VITE_API_PORT` equal to the backend `API_PORT`.

### 4. PDF parsing service — MinerU (optional)

The PDF tools (`pdf_parse` / `pdf_read` / `pdf_grep` / `pdf_vision`) call a self-hosted
**[MinerU](https://github.com/opendatalab/MinerU)** API that turns a PDF into Markdown. Deploy
MinerU's API server per its official docs, then point the backend at its `/file_parse` endpoint:

```bash
# .env
PDF_PARSE_URL=http://<mineru-host>:8000/file_parse
```

Skip this entirely if you don't need PDF reading. See the [MinerU repository](https://github.com/opendatalab/MinerU) for installation and deployment.

### Production (brief)

1. **Backend:** `uvicorn main:app --host $API_HOST --port $API_PORT` (inject the same env as `.env`). For SQLite, keep `UVICORN_WORKERS=1`; switch to PostgreSQL before scaling workers.
2. **Frontend:** `npm run build`, serve `frontend/dist/` with any static server, and reverse-proxy `/api` to the backend (equivalent to the dev-time Vite proxy).

---

## ⚙️ Configuration

All settings are read from `.env` (see [.env.example](.env.example)). Highlights:

| Variable | Purpose | Default |
|----------|---------|---------|
| `ANTHROPIC_BASE_URL` | Anthropic-compatible endpoint (Kimi) | `https://api.moonshot.ai/anthropic` |
| `ANTHROPIC_AUTH_TOKEN` | Kimi/Moonshot API key | — |
| `ANTHROPIC_MODEL` | Main research model | `kimi-k2.5` |
| `SERPER_API_KEY` | Web/Scholar search ([serper.dev](https://serper.dev)) | — |
| `EMBEDDING_MODEL_URL` / `EMBEDDING_MODEL_API_KEY` | DashScope embeddings (semantic memory; optional) | DashScope |
| `FIRECRAWL_API_KEY` | Optional JS-render fetch fallback | — |
| `PDF_PARSE_URL` | MinerU parse service for PDFs | `http://127.0.0.1:8000/file_parse` |
| `PDF_VISION_MODEL` | Multimodal model for PDF figures | (falls back to summary model) |
| `DATABASE_URL` | SQLite (use an absolute path in production) | `sqlite+aiosqlite:///./deepresearch.db` |
| `API_HOST` / `API_PORT` | Backend bind address | `0.0.0.0` / `8808` |
| `MEMORY_SUMMARY_THRESHOLD` | Turns before episodic summary | `10` |
| `CLAUDE_CONFIG_DIR` | Isolated SDK config dir (keeps transcripts out of `~/.claude`) | `./.claude-runtime` |

> Use `APP_DEBUG=true` (not the generic `DEBUG`) for development, to avoid clashing with non-boolean values like `DEBUG=release`.

**Ports cheat-sheet** (avoid conflicts by editing only these):

| Purpose | Variable / file | Default |
|---------|-----------------|---------|
| Backend port | `.env` → `API_PORT` | 8808 |
| Frontend dev port | `frontend/.env.development` → `VITE_DEV_PORT` | 3020 |
| Frontend → backend proxy | `VITE_API_PORT` (must equal `API_PORT`) | 8808 |
| Static preview | `VITE_PREVIEW_PORT` (`npm run preview`) | 3021 |

---

## 🔌 Main API

| Method | Path | Description |
|--------|------|-------------|
| `GET` / `POST` | `/api/projects` | List / create projects |
| `GET` / `PATCH` / `DELETE` | `/api/projects/{id}` | Read / update / delete a project |
| `GET` / `POST` … | `/api/projects/{id}/memory` | Memory panel + manual CRUD |
| `POST` | `/api/chat` | Non-streaming chat (`project_id`, `message`, `session_id?`) |
| `POST` | `/api/chat/stream` | SSE chat (`status`, `text`, `tool_start`, `tool_result`, `artifact`, `task_*`, `done`) |
| `GET` | `/api/chat/{project_id}/history` | Recent messages |
| `GET` | `/api/chat/{project_id}/sessions` | List sessions |
| `GET` / `POST` | `/api/artifacts` | List / fetch generated artifacts |
| `GET` / `POST` … | `/api/folders` | Folder tree CRUD, `/suggest`, `/apply`, `/assign` |

Full interactive reference at `/docs` (Swagger) and `/redoc`.

---

## 🧠 Memory system

Each project keeps four kinds of memory:

- **semantic** — facts, definitions, data points, literature conclusions, entities
- **episodic** — topic-segmented conversation summaries
- **procedural** — search strategies, verification habits, outline preferences
- **preference** — source affinity, depth/format/language preferences

After each turn, the pipeline segments the conversation by topic, writes an episodic summary, extracts/updates facts (mem0-style), and (optionally) embeds them for semantic recall. Retrieval is **task-aware** — a literature query, a synthesis request, and a fact-check weight the categories differently.

---

## 📝 License

Released under the [MIT License](LICENSE).

---

## 🙏 Acknowledgements

[claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-python) · [Kimi / Moonshot AI](https://www.moonshot.ai) · [Serper](https://serper.dev) · [MinerU](https://github.com/opendatalab/MinerU) · [FastAPI](https://fastapi.tiangolo.com) · [Vite](https://vitejs.dev)
