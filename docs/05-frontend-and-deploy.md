# 5. Frontend and deployment

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py          # opens http://localhost:8501
```
Pick **Offline demo** first (free, rule-based) to see every screen, then **Live models (OpenRouter)** with `OPENROUTER_API_KEY` set.
A first live run is capped (60 distinct comments, $0.50) from the sidebar; raise the caps once the report looks right.

## Screens
| Tab | What the reviewer does |
|---|---|
| Briefs for review | Reads ranked briefs (explanation, numbers, example comments), then Approve / Needs follow-up / Dismiss. Saved with name and note |
| Return rates | Sees return rate by product and size |
| What it could not do | Rejected rows, unknown sizes/colours, UNCLEAR comments, budget-skipped comments, briefs that failed the fact check |
| Try a comment | Types any comment and sees how it is read; vague ones are shown as "too uncertain, not counted" (the on-purpose failure case for the demo) |
| Run & cost | Calls, USD, cache hits, accuracy on demo data, and the weekly cost at Dhaga's volume with the arithmetic |

## Deploy on Hugging Face Spaces (Streamlit)
1. Create a Space, SDK **Streamlit**. Do this early and deploy something trivial first.
2. Put this block at the very top of the repo's `README.md` (Spaces read it; the repo needs `requirements.txt` at the root, which it has):
   ```yaml
   ---
   title: Dhaga Returns Insights
   sdk: streamlit
   app_file: app.py
   python_version: "3.11"
   ---
   ```
   Check Hugging Face's "Spaces Config Reference" for the current options before relying on this.
3. Space **Settings -> Secrets**: add `OPENROUTER_API_KEY` and `DATABASE_URL` (Supabase *session pooler* string, see doc 4). Secrets are available to the app as environment variables.
4. Push the repo (without `.env`). Open the URL on a phone and on a laptop you have never used.
5. **Use Supabase for the database.** A Space's local disk is ephemeral, so with SQLite the saved reviews and cache vanish on restart; the sidebar shows which storage is active.

## Before the demo
- Run once on the deployed URL so a result already exists when the room opens it (it is read back from the database).
- Wake the Supabase project if it was idle, and open the app cold once.
- Have the failure case ready: "Try a comment" with `ok ok`, and the "What it could not do" tab.
