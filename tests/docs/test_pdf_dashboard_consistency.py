from __future__ import annotations

from app.docs.exporters.markdown_exporter import MarkdownExporter
from app.docs.exporters.pdf_exporter import PDFExporter
from app.docs.prd_engine import PRDEngine
from app.graph.graph_engine import KnowledgeGraphEngine
from app.intelligence.intelligence_engine import IntelligenceEngine
from app.models.file_schema import ScanStatus
from app.sessions.session_manager import session_manager
from tests.intelligence.test_canonical_presenter import _contextbridge_scan
from tests.intelligence.test_product_identity_noise_filter import noisy_fullstack_scan


def test_pdf_uses_canonical_summary():
    scan = _contextbridge_scan()
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    prd = PRDEngine().generate(scan, intelligence, graph, session_id="session-1")

    assert prd.canonical_intelligence is not None
    assert prd.overview.content == prd.canonical_intelligence.product_summary
    assert prd.project_brief is not None
    assert prd.project_brief.goal.content == prd.canonical_intelligence.product_summary


def test_project_brief_what_uses_canonical():
    scan = _contextbridge_scan()
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    prd = PRDEngine().generate(scan, intelligence, graph, session_id="session-1")

    assert prd.canonical_intelligence is not None
    assert prd.project_brief is not None
    assert prd.project_brief.what.content == prd.canonical_intelligence.what


def test_project_brief_what_exactly_equals_canonical():
    scan = _contextbridge_scan()
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    prd = PRDEngine().generate(scan, intelligence, graph, session_id="session-1")

    assert prd.canonical_intelligence is not None
    assert prd.project_brief is not None
    assert prd.project_brief.what.content == prd.canonical_intelligence.what


def test_pdf_what_does_not_leak_cms():
    scan = _contextbridge_scan()
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    prd = PRDEngine().generate(scan, intelligence, graph, session_id="session-1")

    markdown = MarkdownExporter().export(prd).lower()
    pdf_text = PDFExporter().export(prd).decode("latin-1", errors="ignore").lower()

    assert "content management application" not in markdown
    assert "content management application" not in pdf_text
    assert "ai-powered developer tool" in markdown
    assert "ai-powered developer tool" in pdf_text


def test_pdf_text_has_zero_cms_matches():
    scan = _contextbridge_scan()
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    prd = PRDEngine().generate(scan, intelligence, graph, session_id="session-1")

    markdown = MarkdownExporter().export(prd).lower()
    pdf_text = PDFExporter().export(prd).decode("latin-1", errors="ignore").lower()

    assert "content management application" not in markdown
    assert "content management application" not in pdf_text


def test_dashboard_payload_has_canonical_intelligence(client):
    sid = session_manager.create_session(session_type="folder", source_name="contextbridge.zip")
    scan = _contextbridge_scan()
    scan.session_id = sid
    scan.status = ScanStatus.COMPLETED
    session_manager.set_result(sid, scan)

    response = client.get(f"/analyze/intelligence/{sid}")
    assert response.status_code == 200
    data = response.json()
    assert "canonical_intelligence" in data
    assert data["canonical_intelligence"]["product_summary"]
    assert data["summary"]["what"] == data["canonical_intelligence"]["what"]
    assert data["project_goal"] == data["canonical_intelligence"]["project_goal"]


def test_intelligence_api_summary_what_matches_canonical(client):
    sid = session_manager.create_session(session_type="folder", source_name="contextbridge.zip")
    scan = _contextbridge_scan()
    scan.session_id = sid
    scan.status = ScanStatus.COMPLETED
    session_manager.set_result(sid, scan)

    response = client.get(f"/analyze/intelligence/{sid}")
    assert response.status_code == 200
    data = response.json()
    assert data["canonical_intelligence"]["what"] == data["summary"]["what"]


def test_dashboard_why_matches_canonical(client):
    sid = session_manager.create_session(session_type="folder", source_name="contextbridge.zip")
    scan = _contextbridge_scan()
    scan.session_id = sid
    scan.status = ScanStatus.COMPLETED
    session_manager.set_result(sid, scan)

    response = client.get(f"/analyze/intelligence/{sid}")
    assert response.status_code == 200
    data = response.json()
    assert data["canonical_intelligence"]["why"] == data["summary"]["why"]
    assert data["canonical_intelligence"]["why"] == data["project_brief"]["why"]


def test_dashboard_payload_no_html_markup(client):
    sid = session_manager.create_session(session_type="folder", source_name="noise.zip")
    scan = noisy_fullstack_scan()
    scan.session_id = sid
    scan.status = ScanStatus.COMPLETED
    session_manager.set_result(sid, scan)

    response = client.get(f"/analyze/intelligence/{sid}")
    assert response.status_code == 200
    data = response.json()
    rendered = " ".join(
        [
            data.get("project_goal", ""),
            data.get("summary", {}).get("what", ""),
            data.get("summary", {}).get("why", ""),
            data.get("canonical_intelligence", {}).get("product_summary", ""),
            data.get("canonical_intelligence", {}).get("what", ""),
        ]
    ).lower()

    for token in ("<p", "<img", "src=", "alt=", "width=", "logo-chatgpt-transparent"):
        assert token not in rendered


def test_pdf_no_html_markup():
    scan = noisy_fullstack_scan()
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    prd = PRDEngine().generate(scan, intelligence, graph, session_id="noise-session")

    markdown = MarkdownExporter().export(prd).lower()
    pdf_text = PDFExporter().export(prd).decode("latin-1", errors="ignore").lower()
    rendered = f"{markdown} {pdf_text}"

    for token in ("<p", "<img", "src=", "alt=", "width=", "logo-chatgpt-transparent"):
        assert token not in rendered
