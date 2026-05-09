from app.intelligence.intelligence_engine import IntelligenceEngine
from app.intelligence.product_identity import ProductIdentityResolver
from tests.intelligence.conftest import make_scan_result


def _identity(scan):
    return ProductIdentityResolver().resolve(scan_result=scan, intelligence_result=IntelligenceEngine().analyze(scan))


def test_analyze_alone_does_not_imply_repository_intelligence():
    scan = make_scan_result(
        files=[{"path": "main.py", "extension": ".py"}],
        contents={"main.py": 'from fastapi import FastAPI\napp = FastAPI()\n@app.post("/analyze")\ndef analyze(): pass\n'},
    )
    identity = _identity(scan)
    assert identity.domain != "repository_intelligence"
    assert "coherent workflow" in identity.purpose_summary.lower()


def test_fastapi_mongodb_analyze_falls_back_to_backend_api():
    scan = make_scan_result(
        files=[{"path": "main.py", "extension": ".py"}, {"path": "requirements.txt", "extension": ".txt"}],
        contents={
            "main.py": 'from fastapi import FastAPI\napp = FastAPI()\n@app.post("/analyze")\ndef analyze(): pass\n',
            "requirements.txt": "fastapi\nmotor\npymongo\n",
        },
    )
    identity = _identity(scan)
    assert identity.domain in {"generic_backend", "unknown"}
    assert "backend api service" in identity.purpose_summary.lower()
    assert "coherent workflow" in identity.purpose_summary.lower()


def test_hallucination_detector_classified_from_claim_and_scraper_signals():
    scan = make_scan_result(
        files=[
            {"path": "README.md", "extension": ".md"},
            {"path": "app/api.py", "extension": ".py"},
            {"path": "app/fact_checker.py", "extension": ".py"},
            {"path": "requirements.txt", "extension": ".txt"},
        ],
        contents={
            "README.md": "# FactShield\n\nAI hallucination detection and fact-check backend for claim verification.\n",
            "app/api.py": '@app.post("/verify")\ndef verify_claim(): pass\n@app.post("/sources")\ndef sources(): pass\n',
            "app/fact_checker.py": "class ClaimVerificationService: pass\nclass WebScraper: pass\n",
            "requirements.txt": "fastapi\nrequests\nbeautifulsoup4\n",
        },
    )
    identity = _identity(scan)
    assert identity.domain == "ai_hallucination_detection"
    assert identity.domain_confidence in {"high", "medium"}


def test_repo_intelligence_requires_repo_codebase_evidence():
    scan = make_scan_result(
        files=[{"path": "README.md", "extension": ".md"}, {"path": "main.py", "extension": ".py"}],
        contents={
            "README.md": "# AHAL AI\n\nRepository intelligence and codebase analysis platform for repo chat and PRD generation.\n",
            "main.py": '@app.post("/analyze-repository")\ndef analyze_repo(): pass\n@app.post("/report/prd")\ndef prd(): pass\n',
        },
    )
    identity = _identity(scan)
    assert identity.domain == "repository_intelligence"


def test_healthcare_fixture_remains_medical_safe():
    scan = make_scan_result(
        files=[{"path": "README.md", "extension": ".md"}, {"path": "main.py", "extension": ".py"}],
        contents={
            "README.md": "# Kannadi Med\n\nAI-assisted diagnosis support tool for medical query workflows.\n",
            "main.py": '@app.post("/diagnose")\ndef diagnose(): pass\n@app.post("/search")\ndef search(): pass\n',
        },
    )
    identity = _identity(scan)
    assert identity.domain == "healthcare"
    assert "clinically validated" not in identity.purpose_summary.lower()
    assert "replaces doctors" not in identity.purpose_summary.lower()


def test_unknown_project_does_not_hallucinate_domain():
    scan = make_scan_result(
        files=[{"path": "server.py", "extension": ".py"}],
        contents={"server.py": "from fastapi import FastAPI\napp = FastAPI()\n"},
    )
    identity = _identity(scan)
    assert identity.domain in {"generic_backend", "unknown"}


def test_react_vite_frontend_not_repo_intelligence():
    scan = make_scan_result(
        files=[
            {"path": "package.json", "extension": ".json"},
            {"path": "src/pages/DashboardPage.tsx", "extension": ".tsx"},
            {"path": "src/pages/GeneratorPage.tsx", "extension": ".tsx"},
            {"path": "src/pages/HistoryPage.tsx", "extension": ".tsx"},
            {"path": "src/pages/SettingsPage.tsx", "extension": ".tsx"},
            {"path": "src/layout/AppLayout.tsx", "extension": ".tsx"},
            {"path": "src/services/api.ts", "extension": ".ts"},
        ],
        contents={
            "package.json": '{"name":"nisf-frontend","dependencies":{"react":"18.2.0","vite":"5.0.0"}}',
            "src/pages/DashboardPage.tsx": "export default function DashboardPage() { return null }",
            "src/pages/GeneratorPage.tsx": "export default function GeneratorPage() { return null }",
            "src/pages/HistoryPage.tsx": "export default function HistoryPage() { return null }",
            "src/pages/SettingsPage.tsx": "export default function SettingsPage() { return null }",
            "src/layout/AppLayout.tsx": "export default function AppLayout() { return null }",
            "src/services/api.ts": "export const api = {}",
        },
    )
    identity = _identity(scan)
    text = identity.purpose_summary.lower()
    assert identity.domain != "repository_intelligence"
    for bad in ["repository intelligence", "codebase", "prd", "architecture diff", "repo chat", "test gap", "mcp"]:
        assert bad not in text
    assert "frontend application" in text
    assert "react" in text
    assert "vite" in text
    assert "maintainable workflow" in text


def test_ahal_ai_still_repo_intelligence():
    scan = make_scan_result(
        files=[
            {"path": "README.md", "extension": ".md"},
            {"path": "app/api/repository.py", "extension": ".py"},
            {"path": "app/mcp/tools.py", "extension": ".py"},
            {"path": "app/docs/prd_engine.py", "extension": ".py"},
            {"path": "app/testing/test_gap_detector.py", "extension": ".py"},
        ],
        contents={
            "README.md": "# AHAL AI\n\nRepository intelligence and codebase documentation platform with repo chat, PRD generation, onboarding report, test gap detection, and MCP tools.\n",
            "app/api/repository.py": '@app.post("/analyze-repository")\ndef analyze_repository(): pass\n',
            "app/mcp/tools.py": "class MCPToolRegistry: pass\n",
            "app/docs/prd_engine.py": "class PRDEngine: pass\n",
            "app/testing/test_gap_detector.py": "class TestGapDetector: pass\n",
        },
    )
    identity = _identity(scan)
    assert identity.domain == "repository_intelligence"
    assert identity.repo_intelligence_score >= 2
