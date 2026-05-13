from app.chat.answer_composer_v2 import AnswerComposerV2
from app.chat.chat_engine import ChatEngine
from app.chat.models import ChatContextPack, ChatIntentEntities, ChatIntentResult, EvidenceReference
from app.chat.utils import evidence_display_label
from app.graph.graph_engine import KnowledgeGraphEngine
from app.intelligence.intelligence_engine import IntelligenceEngine
from tests.intelligence.test_product_identity_noise_filter import noisy_fullstack_scan


def make_context_pack() -> ChatContextPack:
    evidence = [
        EvidenceReference(source_type="file", source_id="README.md", file="README.md", reason="Project overview from README.", confidence="high"),
        EvidenceReference(source_type="file", source_id="README.md", file="README.md", reason="Project overview from README.", confidence="high"),
        EvidenceReference(source_type="file", source_id="main.py", file="main.py", reason="FastAPI app entry point.", confidence="high"),
        EvidenceReference(source_type="file", source_id="requirements.txt", file="requirements.txt", reason="Dependency manifest.", confidence="medium"),
        EvidenceReference(source_type="api_endpoint", source_id="/predict", file=None, reason="Detected API endpoint.", confidence="high"),
        EvidenceReference(source_type="framework", source_id="ai_hallucination_detection", file=None, reason="Detected domain signals for ai_hallucination_detection", confidence="low"),
        EvidenceReference(source_type="framework", source_id="ecommerce", file=None, reason="Detected domain signals for ecommerce", confidence="low"),
        EvidenceReference(source_type="module", source_id="analytics", file=None, reason="Detected domain signals for analytics", confidence="low"),
    ]
    filtered = [item for item in evidence if item.reason]
    return ChatContextPack(
        session_id="chat-quality-test",
        question="What does this project do?",
        intent="project_overview",
        project_identity={
            "summary": "Youtube Distraction appears to be a backend API service built with Python and Flask. It exposes a /predict endpoint.",
            "project_type": "backend",
            "frameworks": ["Flask", "Python"],
        },
        architecture_summary={
            "type": "service",
            "confidence": "medium",
            "entry_points": ["main.py"],
        },
        relevant_apis=[
            {"method": "POST", "path": "/predict", "handler": "predict", "file": "main.py", "framework": "Flask", "confidence": "high", "evidence": []},
        ],
        relevant_modules=[
            {"name": "prediction_service", "category": "service", "files": ["main.py"], "confidence": "medium", "evidence": []},
        ],
        selected_evidence=filtered,
        evidence_map={f"E{index}": item for index, item in enumerate(filtered, start=1)},
        warnings=[],
        confidence="medium",
    )


def test_duplicate_paragraphs_removed():
    composer = AnswerComposerV2()
    context_pack = make_context_pack()
    intent = ChatIntentResult(intent="project_overview", confidence="medium", entities=ChatIntentEntities())
    llm_result = {
        "answer": "This project appears to be a backend API service.\n\nThis project appears to be a backend API service.",
        "short_answer": "This project appears to be a backend API service.",
        "sections": [
            {
                "title": "What it is",
                "content": "Backend service.\n\nBackend service.",
                "bullets": ["POST /predict", "POST /predict"],
                "evidence_ids": ["E1", "E1"],
            },
            {
                "title": "What it is",
                "content": "Backend service.",
                "bullets": ["POST /predict"],
                "evidence_ids": ["E1"],
            },
        ],
        "warnings": [],
        "suggested_followups": ["What APIs exist?", "What APIs exist?"],
    }

    answer = composer.compose("What does this project do?", intent, context_pack, llm_result=llm_result)

    assert answer.answer.count("This project is organized as a backend API service.") == 1
    assert len(answer.sections) == 1
    assert answer.sections[0].bullets == ["POST /predict"]


def test_project_overview_answer_is_not_repeated_and_uncertainty_preserved():
    composer = AnswerComposerV2()
    context_pack = make_context_pack()
    intent = ChatIntentResult(intent="project_overview", confidence="medium", entities=ChatIntentEntities())

    answer = composer.compose("What does this project do?", intent, context_pack)
    lowered = answer.answer.lower()

    assert answer.answer.startswith("In short:")
    assert lowered.count("youtube distraction is organized as a backend api service built with python and flask. it exposes a /predict endpoint.") == 1
    assert "detailed but conservative summary centered on the repository's core workflow" in lowered
    assert [section.title for section in answer.sections] == ["What it is", "Detected architecture", "Key API", "What is uncertain"]


def test_weak_domain_tags_are_not_evidence_chips_and_evidence_is_limited():
    composer = AnswerComposerV2()
    context_pack = make_context_pack()
    intent = ChatIntentResult(intent="project_overview", confidence="medium", entities=ChatIntentEntities())

    answer = composer.compose("What does this project do?", intent, context_pack)
    labels = [evidence_display_label(item).lower() for item in answer.evidence]

    assert len(answer.evidence) <= 6
    assert len(labels) == len(set(labels))
    assert "readme.md" in labels
    assert "main.py" in labels
    assert "/predict" in labels
    assert all(token not in labels for token in {"ai_hallucination_detection", "ecommerce", "crm", "cms", "analytics", "devops", "chatbot"})


def test_project_overview_suggested_followups_present():
    composer = AnswerComposerV2()
    context_pack = make_context_pack()
    intent = ChatIntentResult(intent="project_overview", confidence="medium", entities=ChatIntentEntities())

    answer = composer.compose("What does this project do?", intent, context_pack)

    assert answer.suggested_followups[:3] == ["What is built?", "What APIs exist?", "What risks should I review?"]


def test_duplicate_section_titles_removed_as_final_cleanup():
    composer = AnswerComposerV2()
    context_pack = make_context_pack()
    intent = ChatIntentResult(intent="project_overview", confidence="medium", entities=ChatIntentEntities())
    llm_result = {
        "answer": "Answer.",
        "short_answer": "Answer.",
        "sections": [
            {"title": "What it is", "content": "Same section.", "bullets": [], "evidence_ids": []},
            {"title": "What it is", "content": "Same section.", "bullets": [], "evidence_ids": []},
        ],
        "warnings": [],
        "suggested_followups": [],
    }

    answer = composer.compose("What does this project do?", intent, context_pack, llm_result=llm_result)

    assert [section.title for section in answer.sections].count("What it is") == 1


def test_chat_no_html_markup():
    scan = noisy_fullstack_scan()
    intelligence = IntelligenceEngine().analyze(scan)
    graph = KnowledgeGraphEngine().build(scan, intelligence)

    answer = ChatEngine().answer("What does this project do?", scan, intelligence, graph)
    rendered = " ".join(
        [
            answer.answer,
            answer.short_answer or "",
            " ".join(section.content for section in answer.sections),
            " ".join(" ".join(section.bullets) for section in answer.sections),
        ]
    ).lower()

    for token in ("<p", "<img", "src=", "alt=", "width=", "logo-chatgpt-transparent"):
        assert token not in rendered
