from __future__ import annotations

from app.models.file_schema import ScanStatus
from app.sessions.session_manager import session_manager
from tests.intelligence.conftest import empty_scan_result, python_fastapi_scan


def test_folder_intelligence_schema(client):
    sid = session_manager.create_session(session_type="folder", source_name="project.zip")
    scan = python_fastapi_scan()
    scan.session_id = sid
    scan.status = ScanStatus.COMPLETED
    session_manager.set_result(sid, scan)

    response = client.get(f"/analyze/intelligence/{sid}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_type"] == "folder"
    assert "summary" in data
    assert "technical" in data
    assert data["repo_visibility"] == "unknown"
    assert data["hallucination_risk"] in {"medium", "high"}
    assert any("Hallucination guard" in warning for warning in data["warnings"])


def test_repo_intelligence_schema(client):
    sid = session_manager.create_session(session_type="repo", source_name="https://github.com/example/repo")
    scan = python_fastapi_scan()
    scan.session_id = sid
    scan.status = ScanStatus.COMPLETED
    session_manager.set_result(sid, scan)

    response = client.get(f"/analyze/intelligence/{sid}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_type"] == "repo"
    assert data["repo_visibility"] == "unknown"


def test_intelligence_schema_flags_hallucination_risk_when_evidence_is_sparse(client):
    sid = session_manager.create_session(session_type="folder", source_name="empty.zip")
    scan = empty_scan_result()
    scan.session_id = sid
    session_manager.set_result(sid, scan)
    data = client.get(f"/analyze/intelligence/{sid}").json()
    assert data["hallucination_risk"] == "high"
    assert any("Hallucination guard" in warning for warning in data["warnings"])


def test_code_intelligence_schema(client):
    response = client.post("/analyze/code", json={"code": "def run():\n    return 1\n"})
    sid = response.json()["session_id"]
    schema = client.get(f"/analyze/intelligence/{sid}")
    assert schema.status_code == 200
    data = schema.json()
    assert data["session_type"] == "code"
    assert data["technical"]["tech_stack"]


def test_schema_has_required_keys(client):
    sid = session_manager.create_session(session_type="folder", source_name="project.zip")
    scan = python_fastapi_scan()
    scan.session_id = sid
    session_manager.set_result(sid, scan)
    data = client.get(f"/analyze/intelligence/{sid}").json()
    required = {
        "session_id",
        "session_type",
        "status",
        "project_name",
        "project_goal",
        "architecture_style",
        "key_modules",
        "core_features",
        "risks",
        "summary",
        "technical",
        "evidence",
        "warnings",
        "confidence",
    }
    assert required.issubset(data.keys())


def test_schema_no_raw_repr(client):
    sid = session_manager.create_session(session_type="folder", source_name="project.zip")
    scan = python_fastapi_scan()
    scan.session_id = sid
    session_manager.set_result(sid, scan)
    payload = client.get(f"/analyze/intelligence/{sid}").text.lower()
    assert "magicmock" not in payload
    assert "type='" not in payload


def test_schema_empty_fields_safe(client):
    sid = session_manager.create_session(session_type="folder", source_name="empty.zip")
    scan = empty_scan_result()
    scan.session_id = sid
    session_manager.set_result(sid, scan)
    data = client.get(f"/analyze/intelligence/{sid}").json()
    assert data["project_goal"]
    assert isinstance(data["key_modules"], list)


def test_schema_falls_back_when_prd_generation_fails(client, monkeypatch):
    sid = session_manager.create_session(session_type="folder", source_name="project.zip")
    scan = python_fastapi_scan()
    scan.session_id = sid
    session_manager.set_result(sid, scan)

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.api.intelligence_schema.PRDEngine.generate", explode)

    response = client.get(f"/analyze/intelligence/{sid}")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == 2
    assert data["project_goal"]
    assert data["summary"]["what"]
    assert data["summary"]["why"]
    assert "service boundary" in data["summary"]["why"].lower() or "centralize" in data["summary"]["why"].lower()
