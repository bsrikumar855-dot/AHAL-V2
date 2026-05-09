from unittest.mock import MagicMock

from app.docs.exporters.pdf_exporter import PDFExporter
from app.docs.prd_engine import PRDEngine
from app.graph.graph_engine import KnowledgeGraphEngine
from app.intelligence.intelligence_engine import IntelligenceEngine
from tests.intelligence.conftest import make_scan_result


def _weak_backend_intel():
    mock_api = MagicMock(); mock_api.path = "/analyze"
    mock_fw = MagicMock(); mock_fw.name = "FastAPI"
    mock_db = MagicMock(); mock_db.name = "MongoDB"
    mock_intel = MagicMock()
    mock_intel.api_endpoints = [mock_api]
    mock_intel.modules = []
    mock_intel.frameworks = [mock_fw]
    mock_intel.architecture = "Backend"
    mock_intel.dependencies = []
    mock_intel.databases = [mock_db]
    return mock_intel


def test_prd_overview_uses_conservative_fallback_for_weak_evidence():
    engine = PRDEngine()
    mock_scan = MagicMock()
    mock_scan.contents = {"main.py": b"from fastapi import FastAPI\napp = FastAPI()\n"}
    prd = engine.generate(mock_scan, _weak_backend_intel(), MagicMock())
    assert "backend service" in prd.overview.content.lower()
    assert "maintainable structure" in prd.overview.content.lower()
    assert "repository intelligence" not in prd.overview.content.lower()


def test_project_brief_goal_is_not_built_from_wrong_overview():
    engine = PRDEngine()
    mock_scan = MagicMock()
    mock_scan.contents = {"main.py": b"from fastapi import FastAPI\napp = FastAPI()\n"}
    prd = engine.generate(mock_scan, _weak_backend_intel(), MagicMock())
    assert prd.project_brief is not None
    assert "repository intelligence platform" not in prd.project_brief.goal.content.lower()


def test_pdf_does_not_expose_env_paths_or_generation_failed():
    engine = PRDEngine()
    mock_scan = MagicMock()
    mock_scan.contents = {
        "README.md": b"# FactShield\n\nAI hallucination detection and fact-check backend.\n",
        ".env": b"OPENAI_API_KEY=secret",
    }
    dep = MagicMock(); dep.name = "requests"
    mock_api = MagicMock(); mock_api.path = "/verify"
    mock_fw = MagicMock(); mock_fw.name = "FastAPI"
    mock_intel = MagicMock()
    mock_intel.api_endpoints = [mock_api]
    mock_intel.modules = []
    mock_intel.frameworks = [mock_fw]
    mock_intel.architecture = "Backend"
    mock_intel.dependencies = [dep]
    mock_intel.databases = []
    prd = engine.generate(mock_scan, mock_intel, MagicMock())
    pdf = PDFExporter().export(prd)
    assert b".env" not in pdf
    assert b"Generation failed" not in pdf


def test_no_ahal_self_identity_leakage():
    engine = PRDEngine()
    mock_scan = MagicMock()
    mock_scan.contents = {
        "package.json": b'{"name":"nisf-frontend","dependencies":{"react":"18.2.0","vite":"5.0.0"}}',
        "src/pages/DashboardPage.tsx": b"export default function DashboardPage() { return null }",
        "src/pages/GeneratorPage.tsx": b"export default function GeneratorPage() { return null }",
        "src/pages/HistoryPage.tsx": b"export default function HistoryPage() { return null }",
        "src/pages/SettingsPage.tsx": b"export default function SettingsPage() { return null }",
        "src/services/api.ts": b"export const api = {}",
    }
    mock_fw_1 = MagicMock(); mock_fw_1.name = "React"
    mock_fw_2 = MagicMock(); mock_fw_2.name = "Vite"
    mock_intel = MagicMock()
    mock_intel.api_endpoints = []
    mock_intel.modules = []
    mock_intel.frameworks = [mock_fw_1, mock_fw_2]
    mock_intel.architecture = "Frontend"
    mock_intel.dependencies = []
    mock_intel.databases = []
    prd = engine.generate(mock_scan, mock_intel, MagicMock())
    text = prd.overview.content.lower()
    assert "helps users analyze, understand, question, and document software projects" not in text
    assert "frontend application" in text


def test_prd_no_test_contradiction():
    engine = PRDEngine()
    mock_scan = MagicMock()
    mock_scan.contents = {"main.py": b"from fastapi import FastAPI\napp = FastAPI()\n"}
    prd = engine.generate(mock_scan, _weak_backend_intel(), MagicMock())
    completed_titles = " ".join(item.title.lower() for item in (prd.project_brief.completed if prd.project_brief else []))
    risk_titles = " ".join(item.title.lower() for item in prd.risks)
    assert "testing" not in completed_titles
    assert "no tests detected" in risk_titles


def test_prd_no_setup_contradiction():
    engine = PRDEngine()
    mock_scan = MagicMock()
    mock_scan.contents = {"main.py": b"from fastapi import FastAPI\napp = FastAPI()\n"}
    prd = engine.generate(mock_scan, _weak_backend_intel(), MagicMock())
    completed_titles = " ".join(item.title.lower() for item in (prd.project_brief.completed if prd.project_brief else []))
    assert "setup configuration" not in completed_titles or "insufficient evidence" not in prd.setup_notes.content.lower()


def test_backend_fixture_never_leaks_ahal_repo_identity():
    scan = make_scan_result(
        files=[
            {"path": "Frontend/Backend/main.py", "extension": ".py"},
            {"path": "Frontend/Backend/db.py", "extension": ".py"},
            {"path": "Frontend/Backend/agents/answer_agent.py", "extension": ".py"},
            {"path": "Frontend/Backend/.env", "extension": ""},
        ],
        contents={
            "Frontend/Backend/main.py": 'from fastapi import FastAPI\napp = FastAPI()\n@app.post("/analyze")\ndef analyze(): pass\n',
            "Frontend/Backend/db.py": 'from pymongo import MongoClient\nclient = MongoClient("mongodb://localhost/test")\n',
            "Frontend/Backend/agents/answer_agent.py": "class AnswerAgent: pass\n",
            "Frontend/Backend/.env": "OPENAI_API_KEY=secret",
        },
    )
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    prd = PRDEngine().generate(scan, intelligence, graph)
    pdf = PDFExporter().export(prd)
    overview = prd.overview.content.lower()
    assert "ai-powered repository intelligence platform" not in overview
    assert "repository intelligence" not in overview
    assert "understand unfamiliar codebases" not in overview
    assert "backend service" in overview
    assert "maintainable structure" in overview
    assert "core workflow" in overview
    assert b".env" not in pdf
    built_summary = " ".join(item.title.lower() for item in (prd.project_brief.completed if prd.project_brief else []))
    if not prd.modules:
        assert "core modules" not in built_summary
    if "insufficient" in prd.setup_notes.content.lower():
        assert "setup configuration" not in built_summary
    assert b"Client / API Consumer" in pdf
