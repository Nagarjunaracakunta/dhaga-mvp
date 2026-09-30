"""Dhaga & Co. MVP - Streamlit entry point.

Day-1 version: proves the deployment works end to end.
Replace the body with the real workflow once the discovery note is agreed.
"""
import os

import streamlit as st

st.set_page_config(page_title="Dhaga & Co. MVP", page_icon="🧵", layout="wide")

st.title("🧵 Dhaga & Co. MVP")
st.caption("FDE Academy - Mini Project 1")

st.success("Deployment is live. If you can see this on the Space URL, the pipeline works.")

# Show which secrets are configured (never print the values)
with st.expander("Environment check"):
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        st.write(f"{key}: {'✅ set' if os.getenv(key) else '❌ not set'}")

text = st.text_area("Try some input (Hinglish is fine)", "size chota hai, photo mein alag colour tha")
if st.button("Run"):
    st.info(f"Received {len(text)} characters. The real workflow will plug in here.")
