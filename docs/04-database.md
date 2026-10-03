# 4. Database (Supabase / Postgres)

## Why the MVP needs one
- **Hugging Face Spaces (and most free hosts) have an ephemeral disk.** A local SQLite cache or a JSON file is wiped on restart, so
  classifications would be re-bought and the reviewer's decisions would be lost.
- **The review step has to persist** (approve / dismiss / follow up, who, when, why). That is the human-in-the-loop control the brief asks for.
- **Cost and audit:** every run's models, token usage, USD and report are kept, so "what did that cost?" is answerable later.
- **One shared LLM cache** across the laptop, the deployed app and teammates.

Inputs stay **CSV uploads** (a realistic stand-in for an export from their read replica; the brief says no integration with real Dhaga systems is expected).
The database stores *our* state and outputs, not a copy of their warehouse.

## Tables (`db/models.py`, the single source of truth)
| Table | Purpose | Key |
|---|---|---|
| `runs` | One row per run: models, estimated USD, calls, full JSON report | `run_id` |
| `returns` | Latest cleaned + classified state of each return (label, confidence, source) | `return_id` |
| `insights` | Candidate insight + evidence + generated brief + **human review fields** | `(run_id, insight_id)` |
| `llm_cache` | Comment classification cache (key = prompt version + model + normalized comment) | `key` |

Customer ids are not stored. Comments are stored as free text, so treat the database as sensitive.

## How it connects
Plain SQLAlchemy 2 + psycopg 3, no Supabase SDK, so any Postgres works and SQLite is the zero-setup default.
`DATABASE_URL` unset -> `data/processed/dhaga.db`. Set -> Postgres. `postgres://` strings are accepted as Supabase shows them.

```python
from db import store
eng = store.get_engine(); store.init_schema(eng)
store.list_insights(eng)                                   # latest run, ordered by lift
store.set_review(eng, run_id, insight_id, "approved", reviewer="neha", note="check M/L shoulder width")
```
`python -m ai.run --db` persists a run and uses the shared cache. Re-saving a run never overwrites a human review decision.

## Supabase setup (about 10 minutes)
1. Create a project; save the database password.
2. Click **Connect** in the dashboard and copy a Postgres connection string. **Which one matters:**
   - *Direct connection* (port 5432) is **IPv6-only by default**; many hosts (and some home networks) are IPv4-only, so it may fail with "could not translate host name".
   - **Session pooler** (port 5432, `...pooler.supabase.com`) supports IPv4 and IPv6 and suits a long-running app. **Use this one by default.**
   - *Transaction pooler* (port 6543) suits serverless/short-lived connections. It does not support prepared statements; the code already disables them (`prepare_threshold=None`), so it works too.
3. Put it in `.env` as `DATABASE_URL=...` (locally) and as a **secret** in the hosting platform (e.g. the HF Space's secrets). Never commit it or ship it to the browser.
4. Create the tables: paste `db/schema.sql` into the Supabase **SQL editor**, or run `python -m db.cli init`.
5. Check: `python -m db.cli status` shows the dialect, host and row counts. Then `python -m ai.run --db --fast mock:mock --strong mock:mock` as a dry run.

## Security
`schema.sql` enables **row-level security with no policies** on every table, so Supabase's auto-generated public REST API (anon key) cannot read them.
Our server connects as the database role through `DATABASE_URL`. In Supabase the `postgres` role normally bypasses RLS, which is why this works; confirm on your project.
If you later query from the browser with the Supabase JS client, you would need explicit policies and auth. We deliberately do not.

## Failure behaviour
- `python -m ai.run` without `--db` never touches the database.
- With `--db`, an unreachable database fails at start with the driver's error, before any model spend. The frontend must show "storage unavailable" visibly rather than silently show stale data.
- Check the free plan's current limits (for example, projects pausing after inactivity) and wake the project before a demo.

## What was tested
Persistence, review workflow, upsert-without-clobbering-reviews and the shared cache pass on SQLite **and a real local Postgres**; `db/schema.sql` applies cleanly to Postgres.
It has **not** been run against a Supabase project itself; do `python -m db.cli status` first and tell us what it prints if anything differs.
Set `TEST_DATABASE_URL` to run the same tests against your Supabase database (use a scratch project, the tests write data).
