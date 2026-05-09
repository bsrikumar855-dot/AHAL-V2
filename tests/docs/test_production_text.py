from app.docs.utils.production_text import (
    clean_sentence,
    clean_list,
    join_capabilities,
    summarize_stack,
    safe_product_summary,
    safe_remaining_summary,
    safe_next_steps,
)

def test_clean_sentence():
    assert clean_sentence("  hello world  ") == "Hello world."
    assert clean_sentence("Already capitalized!") == "Already capitalized!"
    assert clean_sentence("<Mock id='123'>") == "Insufficient evidence from codebase."
    assert clean_sentence("MagicMock object at 0x123") == "Insufficient evidence from codebase."
    assert "node_modules" not in clean_sentence("hello from node_modules")

def test_clean_list():
    raw = ["apple", "  apple", "Banana", "MagicMock()", "", None, "<Mock>"]
    assert clean_list(raw) == ["apple", "Banana"]

def test_no_raw_repr():
    cleaned = clean_sentence("type='backend' confidence='high' hello")
    assert "type='" not in cleaned
    assert "confidence='" not in cleaned

def test_join_capabilities():
    assert join_capabilities([]) == ""
    assert join_capabilities(["a"]) == "a"
    assert join_capabilities(["a", "b"]) == "a and b"
    assert join_capabilities(["a", "b", "c"]) == "a, b, and c"

def test_capability_joining():
    assert join_capabilities(["analysis"]) == "analysis"
    assert join_capabilities(["analysis", "chat"]) == "analysis and chat"

class DummyFramework:
    def __init__(self, name):
        self.name = name

class DummyItem:
    def __init__(self, title):
        self.title = title

class DummyRisk:
    def __init__(self, recommendation):
        self.recommendation = recommendation

def test_summarize_stack():
    fws = [DummyFramework("FastAPI"), "React"]
    dbs = [DummyFramework("MongoDB")]
    assert summarize_stack(fws, dbs) == "FastAPI, React, and MongoDB"
    assert summarize_stack([], []) == ""

def test_safe_product_summary_medical():
    summary = safe_product_summary("My App", "medical/healthcare assistance", ["diagnose"], "FastAPI", "high")
    assert "healthcare backend" in summary
    assert "diagnose" in summary

def test_safe_product_summary_repo_intel():
    summary = safe_product_summary("AHAL AI", "repository intelligence platform", ["analyze", "chat"], "Next.js", "high")
    assert "repository intelligence" in summary
    assert "analyze" in summary

def test_safe_product_summary_ecommerce():
    summary = safe_product_summary("Shop", "e-commerce", ["cart"], "React", "high")
    assert "e-commerce platform" in summary
    assert "cart" in summary

def test_ecommerce_summary_from_cart_checkout_order_signals():
    summary = safe_product_summary("Shop", "e-commerce", ["cart", "checkout", "order"], "React", "high")
    assert "e-commerce platform" in summary
    assert "checkout" in summary

def test_lms_summary_from_course_student_quiz_signals():
    summary = safe_product_summary("LearnHub", "lms/education", ["course", "student", "quiz"], "Django", "high")
    assert "education platform" in summary
    assert "course" in summary

def test_safe_product_summary_generic_fullstack():
    summary = safe_product_summary("Tool", "generic fullstack", ["API workflows"], "Django, React", "high")
    assert "fullstack application built with Django, React" in summary
    assert "It coordinates API workflows across the interface, application logic, and supporting data flow." in summary

def test_generic_backend_fallback_when_no_domain():
    summary = safe_product_summary("Unknown Tool", "generic backend", [], "FastAPI", "medium")
    assert "backend API service built with FastAPI" in summary
    assert "concentrates the repository's main workflow within a maintainable service layer" in summary

def test_generic_fullstack_fallback_when_no_domain():
    summary = safe_product_summary("Unknown App", "generic fullstack", [], "React and FastAPI", "medium")
    assert "fullstack application built with React and FastAPI" in summary
    assert "coordinates the repository's main workflow across the interface, application logic, and supporting data flow" in summary

def test_unknown_project_does_not_hallucinate():
    summary = safe_product_summary("Mystery", "generic backend", [], "", "low")
    assert "revenue" not in summary.lower()
    assert "hipaa" not in summary.lower()

def test_safe_product_summary_low_confidence():
    summary = safe_product_summary("Unknown", "generic backend", [], "", "low")
    assert "backend API service" in summary
    assert "This summary is based on limited evidence" in summary

def test_product_summary_not_generic():
    summary = safe_product_summary("AHAL AI", "repository intelligence platform", ["repository analysis"], "FastAPI", "high")
    assert "appears to be" not in summary

def test_remaining_summary_limits_items():
    items = [DummyItem(f"Item {i}") for i in range(10)]
    summary = safe_remaining_summary(items)
    assert summary.count("item") <= 5

def test_next_steps_are_actionable():
    remaining = [DummyItem("Authentication"), DummyItem("CI/CD"), DummyItem("Database")]
    risks = [DummyRisk("Document the main operational runbook.")]
    steps = safe_next_steps(remaining, risks)
    assert len(steps) <= 6
    assert any("authentication" in step.lower() for step in steps)
    assert any("runbook" in step.lower() for step in steps)
