import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    return AppTest.from_file("app.py", default_timeout=60)


def test_empty_state_then_offline_run(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch).run()
    assert not at.exception and any("No analysis yet" in i.value for i in at.info)
    next(b for b in at.sidebar.button if b.label == "Run analysis").click()
    at.run()
    assert not at.exception
    assert any(e.label.startswith(("🕓", "✅")) for e in at.expander)           # briefs are listed
    assert at.metric[0].label == "Returns analysed"
    save = next(b for b in at.button if b.label == "Save decision")
    save.click(); at.run()
    assert not at.exception


def test_live_mode_without_key_fails_visibly(tmp_path, monkeypatch):
    for k in ("LLM_PROVIDER", "LLM_FAST", "LLM_STRONG"):
        monkeypatch.delenv(k, raising=False)
    at = _app(tmp_path, monkeypatch).run()
    at.sidebar.radio[0].set_value("Live models (OpenRouter)").run()
    next(b for b in at.sidebar.button if b.label == "Run analysis").click()
    at.run()
    assert not at.exception and any("OPENROUTER_API_KEY" in e.value for e in at.error)
