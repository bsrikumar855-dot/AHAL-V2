import pytest
from unittest.mock import MagicMock
from app.docs.generators.project_brief_generator import ProjectBriefGenerator
from app.docs.models import PRDSection

def test_empty_inputs_do_not_crash():
    gen = ProjectBriefGenerator()
    overview = PRDSection(title="Overview", content="None", confidence="low")
    brief = gen.generate(MagicMock(), MagicMock(), MagicMock(), overview, [])
    assert brief is not None
    assert "maintainable service layer" in brief.goal.content.lower() or "maintainable workflow" in brief.goal.content.lower()

def test_ahal_ai_project_goal():
    gen = ProjectBriefGenerator()
    scan = MagicMock()
    scan.contents = {"README.md": b"AHAL AI is a repository intelligence tool"}
    
    overview = PRDSection(
        title="Overview", 
        content="AHAL AI aims to help users analyze, understand, question, and document software repositories through AI-powered repository intelligence.", 
        confidence="high"
    )
    
    brief = gen.generate(scan, MagicMock(), MagicMock(), overview, [])
    assert "AHAL AI aims to help users analyze" in brief.goal.content

def test_ahal_ai_what_why_completed_remaining():
    gen = ProjectBriefGenerator()
    scan = MagicMock()
    scan.contents = {
        "README.md": b"AHAL AI is a repository intelligence tool",
        "tests/test_foo.py": b""
    }
    
    intel = MagicMock()
    api1 = MagicMock(); api1.path = "/analyze"
    api2 = MagicMock(); api2.path = "/ask"
    api3 = MagicMock(); api3.path = "/report"
    intel.api_endpoints = [api1, api2, api3]
    intel.frameworks = [MagicMock()]
    intel.databases = []
    
    overview = PRDSection(title="Overview", content="This is a fullstack AI-powered repository intelligence platform.", confidence="high")
    
    brief = gen.generate(scan, intel, MagicMock(), overview, [])
    combined_text = " ".join([
        brief.goal.content,
        brief.what.content,
        brief.why.content,
        " ".join(item.title for item in brief.completed),
        " ".join(item.description for item in brief.completed),
    ]).lower()
    assert "repository intelligence" in brief.what.content.lower()
    assert any(term in combined_text for term in [
        "repository",
        "repo",
        "codebase",
        "analysis",
        "prd",
        "report",
        "chat",
    ])
    
    completed_titles = [i.title for i in brief.completed]
    assert "Repository Analysis API" in completed_titles
    assert "Chat/Query API" in completed_titles
    assert "Report/PRD Generation" in completed_titles
    assert "Testing" in completed_titles
    
    remaining_titles = [i.title for i in brief.remaining]
    assert "Authentication" in remaining_titles
    assert "Deployment Configuration" in remaining_titles
    assert "Database" in remaining_titles

def test_kannadi_med_project_goal_medical_safe():
    gen = ProjectBriefGenerator()
    scan = MagicMock()
    scan.contents = {"README.md": b"Kannadi Med diagnosis"}
    
    overview = PRDSection(title="Overview", content="This is a FastAPI-based AI-assisted healthcare backend.", confidence="high")
    
    brief = gen.generate(scan, MagicMock(), MagicMock(), overview, [])
    assert "FastAPI-based AI-assisted healthcare backend" in brief.what.content
    assert "support medical query workflows" in brief.why.content

def test_remaining_does_not_claim_no_database_when_database_exists():
    gen = ProjectBriefGenerator()
    scan = MagicMock()
    intel = MagicMock()
    intel.databases = [MagicMock()]
    overview = PRDSection(title="Overview", content="test", confidence="low")
    
    brief = gen.generate(scan, intel, MagicMock(), overview, [])
    remaining_titles = [i.title for i in brief.remaining]
    assert "Database" not in remaining_titles

def test_remaining_does_not_claim_no_deployment_when_docker_exists():
    gen = ProjectBriefGenerator()
    scan = MagicMock()
    scan.contents = {"Dockerfile": b""}
    intel = MagicMock()
    overview = PRDSection(title="Overview", content="test", confidence="low")
    
    brief = gen.generate(scan, intel, MagicMock(), overview, [])
    remaining_titles = [i.title for i in brief.remaining]
    assert "Deployment Configuration" not in remaining_titles

def test_completed_items_are_evidence_backed():
    gen = ProjectBriefGenerator()
    scan = MagicMock()
    intel = MagicMock()
    fw = MagicMock(); fw.name = "FastAPI"
    intel.frameworks = [fw]
    overview = PRDSection(title="Overview", content="test", confidence="low")
    
    brief = gen.generate(scan, intel, MagicMock(), overview, [])
    fw_item = next(i for i in brief.completed if i.title == "Frameworks")
    assert len(fw_item.evidence) > 0

def test_next_steps_from_risks():
    gen = ProjectBriefGenerator()
    scan = MagicMock()
    intel = MagicMock()
    overview = PRDSection(title="Overview", content="test", confidence="low")
    
    brief = gen.generate(scan, intel, MagicMock(), overview, [])
    assert any("CI/CD" in step for step in brief.next_steps)
    assert any("tests" in step for step in brief.next_steps)
