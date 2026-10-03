---
title: Dhaga Workbench
emoji: 🧵
colorFrom: indigo
colorTo: pink
sdk: docker
app_port: 8501
pinned: false
short_description: CX Copilot and Returns Insights for Dhaga & Co.
---

# Dhaga MVP — Workbench API

Two modules in one FastAPI app:

- **Returns Insights** (`/api/returns/*`): cleans returns data, computes return rates, flags problem segments. Rules only.
- **CX Copilot** (`/api/cx/*`): classifies a support ticket, finds the order, applies rules, drafts a reply from facts + policy, checks it, and waits for an agent to approve.

See `docs/dhaga-mvp-guide.html` for the full plan.

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                        # optional: add Supabase + Anthropic keys
pytest -q                                   # tests (no keys needed)
uvicorn backend.main:app --reload           # API docs at http://127.0.0.1:8000/docs
python -m backend.modules.returns.pipeline  # Returns console report, writes data/processed/
python scripts/generate_demo_data.py        # regenerate Returns demo CSVs (seeded)
```

## Frontend (React + Vite)

```bash
cd frontend && npm install
npm run dev        # http://localhost:5173, forwards /api to the backend on :8000
npm run build      # writes frontend/dist; the backend then serves the app at http://127.0.0.1:8000
```

Pages: Overview, CX Inbox (analyse, approve/edit/reject, Try Copilot), CX Metrics, Returns, Data Quality,
plus a 1-Click Demo that runs Copilot on the open tickets.

The Docker image builds the frontend and runs everything with uvicorn on port 8501.

## Supabase setup

Run `db/cx_tables.sql` once in the Supabase SQL editor. It creates `ai_interactions` and
`knowledge_documents` and turns on Row Level Security. `GET /api/health` lists anything still missing.

## Running without keys

| Missing | What happens |
|---|---|
| `SUPABASE_URL` / `SUPABASE_SECRET_KEY` | CX uses the demo dataset in `data/cx_demo/` (10 tickets covering every rule) |
| `ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY` | Copilot runs in fallback mode: keyword intent + template replies, marked `fallback_mode: true` |

`GET /api/health` shows which mode is active.

## Layout

```
frontend/              React app (pages/, components/, api.js)
backend/
  main.py              app + routers + /api/health + serves frontend/dist
  shared/              settings, Supabase client, Claude client, error shape
  modules/returns/     Returns pipeline + router
  modules/cx/          Copilot: repository, facts, rules, classifier, drafter, checker, fallback, workflow
```

Modules never import each other, only `backend/shared`.

## CX models

Model calls run as LangChain chains (`ChatPromptTemplate | ChatOpenAI.with_structured_output(...)`) against
OpenRouter, in `backend/shared/llm.py`. The workflow that strings the steps together is plain Python in
`backend/modules/cx/copilot.py`.


| Step | Model | Setting |
|---|---|---|
| Classify intent | `claude-haiku-4-5` | temperature 0 |
| Draft reply | `claude-opus-5-5` | effort `low` (Opus 5.5 does not accept temperature); server-side refusal fallback on |
| Check reply | `claude-haiku-4-5` | temperature 0, after a code check of every date, amount, order and tracking number |

Rows with return_reason = "Other" + a comment are flagged `needs_llm=True` (Returns stage 2 will classify them).
`data/returns_ground_truth.csv` is for evaluating that classifier later; the app never reads it.
