from __future__ import annotations

from app.docs.exporters.markdown_exporter import MarkdownExporter
from app.docs.prd_engine import PRDEngine
from app.graph.graph_engine import KnowledgeGraphEngine
from app.intelligence.canonical_presenter import CanonicalProjectPresenter
from app.intelligence.intelligence_engine import IntelligenceEngine
from tests.intelligence.conftest import make_scan_result


def _whatsapp_gateway_scan():
    return make_scan_result(
        files=[
            {"path": "README.md", "extension": ".md"},
            {"path": "package.json", "extension": ".json"},
            {"path": "app/main.py", "extension": ".py"},
        ],
        contents={
            "README.md": (
                "# Whatsapp Gateway\n\n"
                "Dexter - AI agent for deep financial research.\n"
                "Chat with Dexter through WhatsApp by linking your phone to the gateway.\n"
            ),
            "package.json": '{"name":"whatsapp-gateway","description":"Chat with Dexter through WhatsApp by linking your phone to the gateway."}',
            "app/main.py": (
                'from fastapi import FastAPI\napp = FastAPI()\n'
                '@app.post("/chat")\ndef chat(): pass\n'
                '@app.get("/health")\ndef health(): pass\n'
            ),
        },
    )


def test_whatsapp_gateway_why_from_explicit_description():
    scan = _whatsapp_gateway_scan()
    intelligence = IntelligenceEngine().analyze(scan)
    canonical = CanonicalProjectPresenter().build("session-why-1", scan, intelligence)

    assert "access Dexter" in canonical.why
    assert "WhatsApp" in canonical.why
    assert "linking their phone" in canonical.why
    assert "unfamiliar codebases" not in canonical.why
    assert "repository-aware questions" not in canonical.why
    assert "technical documentation" not in canonical.why


def test_developer_tool_why_is_code_specific():
    scan = make_scan_result(
        files=[
            {"path": "README.md", "extension": ".md"},
            {"path": "app/main.py", "extension": ".py"},
        ],
        contents={
            "README.md": "# ContextBridge AI\n\nAI-powered developer tool that transforms code changes into structured, queryable knowledge using Gemma models.\n",
            "app/main.py": 'from fastapi import FastAPI\napp = FastAPI()\n@app.post("/analyze")\ndef analyze(): pass\n',
        },
    )
    intelligence = IntelligenceEngine().analyze(scan)
    canonical = CanonicalProjectPresenter().build("session-why-2", scan, intelligence)

    assert "structured, queryable project knowledge" in canonical.why
    assert "cms" not in canonical.why.lower()
    assert "ecommerce" not in canonical.why.lower()


def test_portal_why_is_outcome_focused():
    scan = make_scan_result(
        files=[
            {"path": "README.md", "extension": ".md"},
            {"path": "app/main.py", "extension": ".py"},
            {"path": "package.json", "extension": ".json"},
        ],
        contents={
            "README.md": "# Clairo Frontend\n\nFullstack app for a CSE department portal.\n",
            "app/main.py": 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/health")\ndef health(): pass\n',
            "package.json": '{"name":"clairo-frontend","scripts":{"dev":"vite"}}',
        },
    )
    intelligence = IntelligenceEngine().analyze(scan)
    canonical = CanonicalProjectPresenter().build("session-why-portal", scan, intelligence)

    assert "centralize departmental notices" in canonical.why.lower()
    assert "unified portal" in canonical.why.lower()
    assert canonical.why != "It is intended to centralize the repository's core workflow within a maintainable, reviewable implementation boundary."


def test_unknown_project_why_is_conservative():
    scan = make_scan_result(
        files=[{"path": "app/main.py", "extension": ".py"}],
        contents={"app/main.py": 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/health")\ndef health(): pass\n'},
    )
    intelligence = IntelligenceEngine().analyze(scan)
    canonical = CanonicalProjectPresenter().build("session-why-3", scan, intelligence)

    assert canonical.why == "It is intended to centralize the repository's core workflow within a maintainable, reviewable implementation boundary."


def test_pdf_why_matches_canonical():
    scan = _whatsapp_gateway_scan()
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    prd = PRDEngine().generate(scan, intelligence, graph, session_id="session-why-4")

    assert prd.canonical_intelligence is not None
    assert prd.project_brief is not None
    assert prd.project_brief.why.content == prd.canonical_intelligence.why

    markdown = MarkdownExporter().export(prd)
    assert prd.canonical_intelligence.why in markdown
