"""Automated tests for Phase 6 (LLM adapter). No real network calls are made."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from llm import client as llm_client


@pytest.fixture(autouse=True)
def default_config(monkeypatch):
    monkeypatch.setattr(llm_client.config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(llm_client.config, "GEMINI_API_KEY", "fake-key-for-tests")
    monkeypatch.setattr(llm_client.config, "GEMINI_MODEL", "gemini-test-model")


def test_complete_dispatches_to_gemini(monkeypatch):
    monkeypatch.setattr(llm_client, "_call_gemini", lambda *a, **k: "hello from gemini")
    result = llm_client.get_llm_client().complete("hi")
    assert result.provider == "gemini"
    assert result.model == "gemini-test-model"
    assert result.output == "hello from gemini"
    assert result.elapsed_ms >= 0


def test_complete_dispatches_to_ollama(monkeypatch):
    monkeypatch.setattr(llm_client.config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(llm_client.config, "OLLAMA_MODEL", "test-model")
    monkeypatch.setattr(llm_client, "_call_ollama", lambda *a, **k: "hello from ollama")
    result = llm_client.get_llm_client().complete("hi")
    assert result.provider == "ollama"
    assert result.output == "hello from ollama"


def test_unknown_provider_raises():
    with pytest.raises(llm_client.LLMError):
        llm_client.get_llm_client(provider="magic")


def test_missing_gemini_key_raises(monkeypatch):
    monkeypatch.setattr(llm_client.config, "GEMINI_API_KEY", "")
    with pytest.raises(llm_client.LLMError, match="GEMINI_API_KEY"):
        llm_client.get_llm_client().complete("hi")


def test_complete_json_parses_clean_json(monkeypatch):
    monkeypatch.setattr(llm_client, "_call_gemini", lambda *a, **k: '{"a": 1, "b": "two"}')
    data = llm_client.get_llm_client().complete_json("give me json")
    assert data == {"a": 1, "b": "two"}


def test_complete_json_strips_markdown_fences(monkeypatch):
    monkeypatch.setattr(llm_client, "_call_gemini", lambda *a, **k: '```json\n{"ok": true}\n```')
    data = llm_client.get_llm_client().complete_json("give me json")
    assert data == {"ok": True}


def test_complete_json_raises_on_invalid_json(monkeypatch):
    monkeypatch.setattr(llm_client, "_call_gemini", lambda *a, **k: "not json at all")
    with pytest.raises(llm_client.LLMError, match="did not return valid JSON"):
        llm_client.get_llm_client().complete_json("give me json")


def test_llm_test_endpoint_success(monkeypatch):
    monkeypatch.setattr(llm_client, "_call_gemini", lambda *a, **k: "OK")
    client = TestClient(app)
    response = client.post("/llm/test", json={"prompt": "say ok"})
    assert response.status_code == 200
    body = response.json()
    assert body["output"] == "OK"
    assert body["provider"] == "gemini"


def test_llm_test_endpoint_failure_returns_502(monkeypatch):
    def boom(*a, **k):
        raise llm_client.LLMError("simulated failure")
    monkeypatch.setattr(llm_client, "_call_gemini", boom)
    client = TestClient(app)
    response = client.post("/llm/test", json={"prompt": "say ok"})
    assert response.status_code == 502
    assert "simulated failure" in response.json()["detail"]


def test_llm_test_endpoint_default_prompt(monkeypatch):
    monkeypatch.setattr(llm_client, "_call_gemini", lambda prompt, *a, **k: f"echo:{prompt}")
    client = TestClient(app)
    response = client.post("/llm/test", json={})
    assert response.status_code == 200
    assert "OK" in response.json()["output"]