# Dhaga MVP — returns insights (stage 1: no AI)

```bash
pip install -r requirements.txt
python scripts/generate_demo_data.py   # regenerates data/*.csv (seeded)
python -m backend.pipeline             # prints report, writes data/processed/
pytest -q                              # tests
uvicorn backend.main:app --reload      # API docs at http://127.0.0.1:8000/docs
```

Flow: ingest -> validate -> normalize -> aggregate -> candidate insights.
Rows with return_reason = "Other" + a comment are flagged `needs_llm=True` (stage 2 will classify them).
`data/returns_ground_truth.csv` is for evaluating the classifier later; the app never reads it.
