from __future__ import annotations

from app.sessions.session_manager import session_manager


def test_python_code_analysis(client):
    response = client.post(
        "/analyze/code",
        json={
            "filename": "app.py",
            "code": "import os\n\ndef greet(name):\n    return f'hi {name}'\n\nclass Service:\n    pass\n",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_type"] == "code"
    sid = data["session_id"]

    status = client.get(f"/analyze/status/{sid}")
    assert status.status_code == 200
    assert status.json()["session_type"] == "code"
    assert status.json()["status"] == "completed"


def test_javascript_code_analysis(client):
    response = client.post(
        "/analyze/code",
        json={
            "filename": "server.js",
            "code": "const express = require('express');\nfunction start() { return true; }\nclass App {}\n",
        },
    )
    assert response.status_code == 200
    sid = response.json()["session_id"]
    intelligence = client.get(f"/analyze/intelligence/{sid}")
    assert intelligence.status_code == 200
    data = intelligence.json()
    assert data["session_type"] == "code"
    assert "javascript" in " ".join(data["technical"]["tech_stack"]).lower()


def test_code_session_empty_rejected(client):
    response = client.post("/analyze/code", json={"code": "   "})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"


def test_code_session_oversized_rejected(client, monkeypatch):
    from app.config import config

    original = config.scanner.code_max_chars
    object.__setattr__(config.scanner, "code_max_chars", 10)
    try:
        response = client.post("/analyze/code", json={"code": "x" * 50})
        assert response.status_code == 400
    finally:
        object.__setattr__(config.scanner, "code_max_chars", original)


def test_code_chat_works(client):
    response = client.post(
        "/analyze/code",
        json={"filename": "sample.py", "code": "def add(a, b):\n    return a + b\n"},
    )
    sid = response.json()["session_id"]
    answer = client.post(
        f"/analyze/chat/{sid}",
        json={"question": "What does this function do?", "include_history": True, "max_context_items": 5},
    )
    assert answer.status_code == 200
    data = answer.json()
    assert "answer" in data
    assert "[E1]" in data["answer"]
    assert data["answer"].startswith("In short:")
    assert any(section["title"] == "What I can confirm" for section in data.get("sections", []))


def test_code_analysis_no_llm_required(client, monkeypatch):
    from app.config import config

    original = config.scanner.llm_enabled
    object.__setattr__(config.scanner, "llm_enabled", False)
    try:
        response = client.post("/analyze/code", json={"code": "def run():\n    return 1\n"})
        assert response.status_code == 200
        sid = response.json()["session_id"]
        result = session_manager.get_artifact(sid, "code_result")
        assert result is not None
    finally:
        object.__setattr__(config.scanner, "llm_enabled", original)
