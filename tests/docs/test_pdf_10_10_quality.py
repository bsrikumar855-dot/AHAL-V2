from unittest.mock import MagicMock

from app.docs.exporters.pdf_exporter import PDFExporter
from app.docs.prd_engine import PRDEngine


def _pdf_text(prd) -> str:
    return PDFExporter().export(prd).decode("latin-1", errors="ignore")


def _frontend_prd():
    engine = PRDEngine()
    scan = MagicMock()
    scan.contents = {
        "package.json": b'{"name":"nisf-frontend","dependencies":{"react":"18.2.0","vite":"5.0.0"}}',
        "src/pages/DashboardPage.tsx": b"export default function DashboardPage() { return null }",
        "src/pages/GeneratorPage.tsx": b"export default function GeneratorPage() { return null }",
        "src/pages/HistoryPage.tsx": b"export default function HistoryPage() { return null }",
        "src/pages/SettingsPage.tsx": b"export default function SettingsPage() { return null }",
        "src/layout/AppLayout.tsx": b"export default function Layout() { return null }",
        "src/services/api.ts": b"export const api = {}",
    }
    fw1 = MagicMock(); fw1.name = "React"
    fw2 = MagicMock(); fw2.name = "Vite"
    intel = MagicMock()
    intel.api_endpoints = []
    intel.modules = []
    intel.frameworks = [fw1, fw2]
    intel.languages = []
    intel.architecture = "Frontend"
    intel.dependencies = []
    intel.databases = []
    intel.workflow = None
    return engine.generate(scan, intel, MagicMock())


def _backend_prd():
    engine = PRDEngine()
    scan = MagicMock()
    scan.contents = {
        "main.py": b'from fastapi import FastAPI\napp = FastAPI()\n@app.post("/analyze")\ndef analyze(): return {"ok": True}\n',
    }
    api = MagicMock(); api.method = "POST"; api.path = "/analyze"; api.framework = "FastAPI"; api.source_file = "main.py"
    fw = MagicMock(); fw.name = "FastAPI"
    intel = MagicMock()
    intel.api_endpoints = [api]
    intel.modules = []
    intel.frameworks = [fw]
    intel.languages = []
    intel.architecture = "Backend"
    intel.dependencies = []
    intel.databases = []
    intel.workflow = None
    return engine.generate(scan, intel, MagicMock())


def _kannadi_med_prd():
    engine = PRDEngine()
    scan = MagicMock()
    scan.contents = {
        "README.md": b"# Kannadi Med\n\nAI-assisted diagnosis support tool for medical query workflows.\n",
        "app/main.py": b'from fastapi import FastAPI\napp = FastAPI()\n@app.post("/diagnose")\ndef diagnose(): pass\n@app.post("/search")\ndef search(): pass\n',
        "requirements.txt": b"fastapi\nuvicorn\n",
    }
    api1 = MagicMock(); api1.method = "POST"; api1.path = "/diagnose"; api1.framework = "FastAPI"; api1.source_file = "app/main.py"
    api2 = MagicMock(); api2.method = "POST"; api2.path = "/search"; api2.framework = "FastAPI"; api2.source_file = "app/main.py"
    fw = MagicMock(); fw.name = "FastAPI"
    intel = MagicMock()
    intel.api_endpoints = [api1, api2]
    intel.modules = []
    intel.frameworks = [fw]
    intel.languages = []
    intel.architecture = "Backend"
    intel.dependencies = []
    intel.databases = []
    intel.workflow = None
    return engine.generate(scan, intel, MagicMock())


def test_pdf_no_repo_identity_leak_for_generic_frontend():
    text = _pdf_text(_frontend_prd()).lower()
    for bad in [
        "ai-powered repository intelligence platform",
        "repository intelligence",
        "codebase intelligence",
        "prd generation",
        "architecture diff",
        "test gap",
        "mcp tools",
    ]:
        assert bad not in text


def test_pdf_generic_frontend_summary_is_conservative():
    text = _pdf_text(_frontend_prd()).lower()
    assert "frontend application" in text
    assert "react" in text
    assert "vite" in text
    assert "frontend" in text


def test_pdf_no_test_contradiction():
    text = _pdf_text(_backend_prd()).lower()
    assert "testing: test suite is present" not in text
    assert "no tests detected" in text


def test_pdf_no_database_contradiction():
    text = _pdf_text(_backend_prd()).lower()
    assert "built components include: database integration" not in text
    assert "no database/storage layer detected" in text


def test_pdf_no_setup_contradiction():
    text = _pdf_text(_backend_prd()).lower()
    assert "setup configuration" not in text
    assert "insufficient setup evidence" in text or "insufficient evidence" in text


def test_pdf_frontend_workflow_does_not_say_server_application():
    text = _pdf_text(_frontend_prd()).lower()
    assert "server application" not in text
    assert "route handler delegates to service layer" not in text
    assert "backend returns response" not in text


def test_pdf_evidence_does_not_show_rejected_domain_candidates():
    text = _pdf_text(_frontend_prd()).lower()
    for bad in [
        "detected domain signals for repository intelligence",
        "detected domain signals for ecommerce",
        "detected domain signals for crm",
        "detected domain signals for cms",
        "detected domain signals for analytics",
        "detected domain signals for devops",
    ]:
        assert bad not in text


def test_pdf_no_env_or_secret_paths():
    prd = _backend_prd()
    text = _pdf_text(prd).lower()
    assert ".env" not in text
    assert "private_key" not in text
    assert "credentials" not in text


def test_pdf_has_truth_notice():
    text = _pdf_text(_frontend_prd())
    assert "This report is generated from static code evidence." in text


def test_pdf_shows_separate_confidences():
    text = _pdf_text(_frontend_prd())
    assert "Architecture Confidence" in text
    assert "Product Purpose Confidence" in text


def test_pdf_tables_render_cleanly():
    text = _pdf_text(_frontend_prd())
    assert "### Languages TypeScript" not in text
    assert "### Frameworks React" not in text


def test_pdf_evidence_appendix_limited():
    text = _pdf_text(_frontend_prd())
    assert "Additional evidence available in JSON export." in text


def test_pdf_language_inferred_from_python_files():
    text = _pdf_text(_backend_prd())
    assert "Languages" in text
    assert "Python" in text


def test_pdf_workflow_mentions_diagnose_and_search_when_routes_exist():
    text = _pdf_text(_kannadi_med_prd())
    assert "Diagnosis API" in text
    assert "Retrieval API" in text or "search" in text.lower()


def test_pdf_database_risk_is_contextual_not_absolute():
    text = _pdf_text(_kannadi_med_prd())
    assert "No persistent database/storage layer was detected" in text
    assert "Add persistence only if the application stores sessions, user data, retrieval indexes, or audit history." in text
    assert "If sensitive medical data is stored, document data handling and access controls." in text


def test_pdf_evidence_appendix_filters_file_extension_noise():
    text = _pdf_text(_backend_prd())
    assert "File extension maps to Python" not in text


def test_pdf_kannadi_med_report_quality():
    text = _pdf_text(_kannadi_med_prd())
    assert "Python" in text
    assert "Diagnosis API" in text
    assert "Retrieval API" in text or "search" in text.lower()
    assert "Architecture Confidence" in text
    assert "Product Purpose Confidence" in text
