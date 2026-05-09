from app.docs.models import PRDResult, PRDSection, ProjectBrief, ProjectStatusItem
from app.intelligence.consistency_validator import OutputConsistencyValidator
from app.intelligence.product_identity import ProductIdentity


def test_setup_built_removed_when_setup_evidence_insufficient():
    prd = PRDResult(
        title="PRD",
        project_type="backend",
        overview=PRDSection(title="Overview", content="Overview", confidence="medium"),
        architecture=PRDSection(title="Architecture", content="Architecture", confidence="medium"),
        tech_stack=PRDSection(title="Tech", content="Tech", confidence="medium"),
        databases=PRDSection(title="DB", content="DB", confidence="low"),
        setup_notes=PRDSection(title="Setup", content="Insufficient evidence from codebase.", confidence="low"),
        project_brief=ProjectBrief(
            goal=PRDSection(title="Goal", content="Goal", confidence="medium"),
            what=PRDSection(title="What", content="What", confidence="medium"),
            why=PRDSection(title="Why", content="Why", confidence="medium"),
            completed=[ProjectStatusItem(title="Setup Configuration", status="built", description="Setup exists.", confidence="high")],
            remaining=[],
            issues=[],
            next_steps=[],
            confidence="medium",
        ),
        confidence="medium",
    )
    validated = OutputConsistencyValidator().validate_prd(prd, ProductIdentity(purpose_summary="Fallback summary"))
    assert all("setup" not in item.title.lower() for item in validated.project_brief.completed)


def test_generation_failed_rewritten_to_conservative_fallback():
    prd = PRDResult(
        title="PRD",
        project_type="backend",
        overview=PRDSection(title="Overview", content="Generation failed.", confidence="low"),
        architecture=PRDSection(title="Architecture", content="Architecture", confidence="medium"),
        tech_stack=PRDSection(title="Tech", content="Tech", confidence="medium"),
        databases=PRDSection(title="DB", content="DB", confidence="low"),
        setup_notes=PRDSection(title="Setup", content="Setup", confidence="low"),
        confidence="low",
    )
    identity = ProductIdentity(purpose_summary="Product purpose evidence is partial, so the summary stays grounded in detected workflow signals.")
    validated = OutputConsistencyValidator().validate_prd(prd, identity)
    assert "generation failed" not in validated.overview.content.lower()


def test_database_missing_removed_when_database_evidence_exists():
    prd = PRDResult(
        title="PRD",
        project_type="backend",
        overview=PRDSection(title="Overview", content="Overview", confidence="medium"),
        architecture=PRDSection(title="Architecture", content="Architecture", confidence="medium"),
        tech_stack=PRDSection(title="Tech", content="Tech", confidence="medium"),
        databases=PRDSection(title="DB", content="MongoDB", confidence="high", evidence=[]),
        setup_notes=PRDSection(title="Setup", content="Setup", confidence="medium"),
        project_brief=ProjectBrief(
            goal=PRDSection(title="Goal", content="Goal", confidence="medium"),
            what=PRDSection(title="What", content="What", confidence="medium"),
            why=PRDSection(title="Why", content="Why", confidence="medium"),
            completed=[],
            remaining=[ProjectStatusItem(title="Database", status="missing", description="No DB", confidence="high")],
            issues=[],
            next_steps=[],
            confidence="medium",
        ),
        confidence="medium",
    )
    prd.databases.evidence = [type("Ev", (), {"file": "db.py", "source_id": "db.py", "source_type": "file", "reason": "db", "confidence": "high"})()]
    validated = OutputConsistencyValidator().validate_prd(prd, ProductIdentity(purpose_summary="Fallback"))
    assert all("database" not in item.title.lower() for item in validated.project_brief.remaining)
