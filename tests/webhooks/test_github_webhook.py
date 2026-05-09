from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json

import app.config as config_module
import app.webhooks.github as webhook_module
from app.indexing.repo_indexer import repo_indexer
from app.models.file_schema import ScanStatus
from app.sessions.session_manager import session_manager
from tests.intelligence.conftest import python_fastapi_scan


def _enable_webhooks(monkeypatch, secret: str = ""):
    scanner = dataclasses.replace(
        config_module.config.scanner,
        github_webhook_enabled=True,
        github_webhook_secret=secret,
    )
    patched = dataclasses.replace(config_module.config, scanner=scanner)
    monkeypatch.setattr(config_module, "config", patched)
    monkeypatch.setattr(webhook_module, "config", patched)


def _disable_webhooks(monkeypatch):
    scanner = dataclasses.replace(config_module.config.scanner, github_webhook_enabled=False, github_webhook_secret="")
    patched = dataclasses.replace(config_module.config, scanner=scanner)
    monkeypatch.setattr(config_module, "config", patched)
    monkeypatch.setattr(webhook_module, "config", patched)


def _repo_index():
    sid = session_manager.create_session(session_type="repo", source_name="https://github.com/example/repo")
    scan = python_fastapi_scan()
    scan.session_id = sid
    scan.status = ScanStatus.COMPLETED
    session_manager.set_result(sid, scan)
    info = session_manager.get_info(sid)
    return sid, repo_indexer.create_index(sid, info, scan)


def _signature(secret: str, payload: dict) -> str:
    raw = json.dumps(payload).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return "sha256=" + digest


def test_disabled_webhook_rejected(client, monkeypatch):
    _disable_webhooks(monkeypatch)
    response = client.post("/webhooks/github", headers={"X-GitHub-Event": "ping"}, json={"zen": "hello"})
    assert response.status_code == 404


def test_ping_works_when_enabled(client, monkeypatch):
    _enable_webhooks(monkeypatch)
    response = client.post("/webhooks/github", headers={"X-GitHub-Event": "ping"}, json={"zen": "hello", "repository": {"html_url": "https://github.com/example/repo"}})
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_signature_verification_passes_and_invalid_signature_rejected(client, monkeypatch):
    secret = "webhook-secret"
    _enable_webhooks(monkeypatch, secret=secret)
    payload = {"repository": {"html_url": "https://github.com/example/repo"}}
    ok = client.post(
        "/webhooks/github",
        headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": _signature(secret, payload)},
        content=json.dumps(payload),
    )
    assert ok.status_code == 200
    bad = client.post(
        "/webhooks/github",
        headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": "sha256=bad"},
        content=json.dumps(payload),
    )
    assert bad.status_code == 401


def test_push_event_without_index_accepted_with_warning(client, monkeypatch):
    _enable_webhooks(monkeypatch)
    payload = {
        "ref": "refs/heads/main",
        "repository": {"html_url": "https://github.com/missing/repo"},
        "commits": [{"added": ["app/new.py"], "modified": [], "removed": []}],
    }
    response = client.post("/webhooks/github", headers={"X-GitHub-Event": "push"}, json=payload)
    assert response.status_code == 200
    assert "No repo index found" in response.json()["warnings"][0]


def test_push_event_with_index_triggers_delta_scan(client, monkeypatch):
    _enable_webhooks(monkeypatch)
    sid, index = _repo_index()
    payload = {
        "ref": "refs/heads/main",
        "repository": {"html_url": index.repo_url, "private": True},
        "commits": [{"added": ["app/new.py"], "modified": ["app/api/routes.py"], "removed": []}],
    }
    response = client.post("/webhooks/github", headers={"X-GitHub-Event": "push"}, json=payload)
    assert response.status_code == 200
    assert response.json()["triggered"]["delta_scan"] is True
    assert client.get(f"/analyze/status/{sid}").json()["repo_visibility"] == "private"
    timeline = client.get(f"/analyze/timeline/{sid}").json()
    stages = [event["stage"] for event in timeline["events"]]
    assert "webhook_delta_scan_started" in stages
    assert "webhook_delta_scan_completed" in stages


def test_pull_request_event_creates_pr_analysis_when_enough_data_exists(client, monkeypatch):
    _enable_webhooks(monkeypatch)
    sid, index = _repo_index()
    payload = {
        "action": "opened",
        "number": 12,
        "repository": {"html_url": index.repo_url},
        "pull_request": {
            "title": "Change users endpoint",
            "body": "Updates API contract",
            "base": {"ref": "main"},
            "head": {"ref": "feature/users"},
            "changed_files": [{"path": "app/api/routes.py", "status": "modified", "before": '@router.get("/users")', "after": '@router.post("/users")'}],
        },
    }
    response = client.post("/webhooks/github", headers={"X-GitHub-Event": "pull_request"}, json=payload)
    assert response.status_code == 200
    assert response.json()["triggered"]["pr_analysis"] is True
    timeline = client.get(f"/analyze/timeline/{sid}").json()
    stages = [event["stage"] for event in timeline["events"]]
    assert "webhook_pr_analysis_started" in stages
    assert "webhook_pr_analysis_completed" in stages


def test_malformed_payload_returns_400(client, monkeypatch):
    _enable_webhooks(monkeypatch)
    response = client.post("/webhooks/github", headers={"X-GitHub-Event": "push"}, content="{bad json")
    assert response.status_code == 400


def test_payload_output_does_not_leak_secrets(client, monkeypatch):
    _enable_webhooks(monkeypatch)
    payload = {
        "repository": {"html_url": "https://github.com/example/repo"},
        "secret": "abc",
        "token": "xyz",
    }
    response = client.post("/webhooks/github", headers={"X-GitHub-Event": "ping"}, json=payload)
    text = response.text.lower()
    assert "abc" not in text
    assert "xyz" not in text
