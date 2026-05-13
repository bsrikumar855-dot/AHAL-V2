from app.chat.chat_engine import ChatEngine
from app.chat.llm.gemini_chat_client import GeminiChatClient
from app.graph.graph_engine import KnowledgeGraphEngine
from app.intelligence.intelligence_engine import IntelligenceEngine
from tests.intelligence.conftest import make_scan_result


def test_chat_does_not_claim_repo_intelligence_from_analyze_alone():
    scan = make_scan_result(
        files=[{"path": "main.py", "extension": ".py"}],
        contents={"main.py": 'from fastapi import FastAPI\napp = FastAPI()\n@app.post("/analyze")\ndef analyze(): pass\n'},
    )
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    answer = ChatEngine(llm_client=GeminiChatClient(enabled=False)).answer("What does this project do?", scan, intelligence, graph)
    text = answer.answer.lower()
    assert "repository intelligence platform" not in text
    assert "repository intelligence" not in text
    assert "codebase intelligence" not in text
    assert "prd generation" not in text
    assert "architecture diff" not in text
    assert "core workflow" in text or "backend service" in text


def test_chat_classifies_hallucination_detector_when_evidence_exists():
    scan = make_scan_result(
        files=[
            {"path": "README.md", "extension": ".md"},
            {"path": "app/main.py", "extension": ".py"},
            {"path": "requirements.txt", "extension": ".txt"},
        ],
        contents={
            "README.md": "# FactShield\n\nAI hallucination detection and fact-check backend for claim verification.\n",
            "app/main.py": 'from fastapi import FastAPI\napp = FastAPI()\n@app.post("/verify")\ndef verify_claim(): pass\n',
            "requirements.txt": "fastapi\nbeautifulsoup4\nrequests\n",
        },
    )
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    answer = ChatEngine(llm_client=GeminiChatClient(enabled=False)).answer("What does this project do?", scan, intelligence, graph)
    assert "fact-checking backend" in answer.answer.lower() or "hallucination detection" in answer.answer.lower()
    assert "[E1]" in answer.answer


def test_chat_includes_uncertainty_when_confidence_low():
    scan = make_scan_result(
        files=[{"path": "server.py", "extension": ".py"}],
        contents={"server.py": "from fastapi import FastAPI\napp = FastAPI()\n"},
    )
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    answer = ChatEngine(llm_client=GeminiChatClient(enabled=False)).answer("What is the goal of this project?", scan, intelligence, graph)
    assert "detailed but conservative summary" in answer.answer.lower()


def test_react_vite_frontend_chat_not_repo_intelligence():
    scan = make_scan_result(
        files=[
            {"path": "package.json", "extension": ".json"},
            {"path": "src/pages/DashboardPage.tsx", "extension": ".tsx"},
            {"path": "src/pages/GeneratorPage.tsx", "extension": ".tsx"},
            {"path": "src/pages/HistoryPage.tsx", "extension": ".tsx"},
            {"path": "src/pages/SettingsPage.tsx", "extension": ".tsx"},
            {"path": "src/services/api.ts", "extension": ".ts"},
        ],
        contents={
            "package.json": '{"name":"nisf-frontend","dependencies":{"react":"18.2.0","vite":"5.0.0"}}',
            "src/pages/DashboardPage.tsx": "export default function DashboardPage() { return null }",
            "src/pages/GeneratorPage.tsx": "export default function GeneratorPage() { return null }",
            "src/pages/HistoryPage.tsx": "export default function HistoryPage() { return null }",
            "src/pages/SettingsPage.tsx": "export default function SettingsPage() { return null }",
            "src/services/api.ts": "export const api = {}",
        },
    )
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    answer = ChatEngine(llm_client=GeminiChatClient(enabled=False)).answer("What does this project do?", scan, intelligence, graph)
    text = answer.answer.lower()
    assert "repository intelligence" not in text
    assert "frontend application" in text
    assert "react" in text
    assert "vite" in text
    assert "core workflow" in text or "maintainable structure" in text or "maintainable workflow" in text


def test_ahal_ai_high_confidence_repo_answer_does_not_require_uncertainty():
    scan = make_scan_result(
        files=[
            {"path": "README.md", "extension": ".md"},
            {"path": "app/main.py", "extension": ".py"},
            {"path": "app/prd_engine.py", "extension": ".py"},
            {"path": "app/mcp/server.py", "extension": ".py"},
        ],
        contents={
            "README.md": "# AHAL AI\n\nRepository intelligence platform for codebase analysis, repo chat, PRD generation, and onboarding reports.\n",
            "app/main.py": 'from fastapi import FastAPI\napp = FastAPI()\n@app.post("/analyze-repository")\ndef analyze_repo(): pass\n@app.post("/repo-chat")\ndef repo_chat(): pass\n',
            "app/prd_engine.py": "class PRDEngine: pass\n",
            "app/mcp/server.py": "def mcp_tools(): pass\n",
        },
    )
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)
    answer = ChatEngine(llm_client=GeminiChatClient(enabled=False)).answer("What does this project do?", scan, intelligence, graph)
    text = answer.answer.lower()
    assert "code intelligence platform" in text or "codebase analysis" in text
    assert "core workflow" not in text or "codebase analysis" in text
