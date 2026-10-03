# Dhaga MVP: returns insights

Turns raw return data (incl. messy Hinglish "Other" comments) into ranked, evidence-backed investigation briefs for a human reviewer.
Deterministic code does everything it can; LLMs (via LangChain, Anthropic and OpenAI supported) only handle language and judgment.

**Docs:** [0. Discovery note](docs/00-discovery-note.md) | [1. Problem](docs/01-problem.md) | [2. Architecture](docs/02-architecture.md) | [3. LLM usage and cost](docs/03-llm-usage-and-cost.md) | [4. Database](docs/04-database.md) | [5. Frontend and deploy](docs/05-frontend-and-deploy.md)

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add OPENROUTER_API_KEY (default provider; not needed for mock mode)
pytest -q                   # 28 tests, no API key needed
```

## The app (start here)
```bash
streamlit run app.py     # pick "Offline demo" first, then "Live models (OpenRouter)"
```
Deploy to Hugging Face Spaces: [docs/05-frontend-and-deploy.md](docs/05-frontend-and-deploy.md)

## Stage 1: no AI
```bash
python scripts/generate_demo_data.py   # (re)generate demo CSVs
python -m backend.pipeline             # validate -> normalize -> aggregate -> candidate insights
```

## Stage 2: AI
```bash
python -m ai.estimate --weekly                          # cost at Dhaga volume, arithmetic shown
python -m ai.run --fast mock:mock --strong mock:mock --eval   # offline dry run, no keys
python -m ai.run --limit 30 --eval                      # small first real run (OpenRouter by default)
python -m ai.run --provider anthropic                   # opt-in: other providers (needs their own key)
python -m ai.run                                        # full run
```
Outputs in `data/processed/`: `returns_classified.csv`, `ai_insights.json`, `ai_run_report.json` (tokens, USD, accuracy).

## Database (optional, recommended once deployed)
```bash
python -m db.cli init && python -m db.cli status       # SQLite by default; set DATABASE_URL for Supabase/Postgres
python -m ai.run --db --fast mock:mock --strong mock:mock
```
Setup for Supabase (which connection string to use, RLS, secrets): [docs/04-database.md](docs/04-database.md).

## API
`uvicorn backend.main:app --reload` then open http://127.0.0.1:8000/docs
(`/api/insights` = rule-based, `/api/ai/insights` and `/api/ai/report` = after `python -m ai.run`).
