import os

# Tests always use the demo CSVs and never call Supabase or a paid model, whatever .env says.
os.environ["RETURNS_DATA_SOURCE"] = "csv"
