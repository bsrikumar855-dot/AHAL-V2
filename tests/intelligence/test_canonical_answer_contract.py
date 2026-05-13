from __future__ import annotations

from app.intelligence.canonical_presenter import derive_project_what, derive_project_why
from app.intelligence.output_guard import CanonicalOutputGuard
from app.intelligence.presentation_models import CanonicalProjectIntelligence


def test_explicit_local_deep_research_what_why_are_precise():
    description = "Web frontend for Local Deep Research - AI research assistant."

    assert (
        derive_project_what("Sound Files For Notifications", description, "frontend_app")
        == "Sound Files For Notifications is a web frontend for the Local Deep Research AI research assistant."
    )
    assert (
        derive_project_why("Sound Files For Notifications", description, "frontend_app")
        == "It exists to provide a web frontend for interacting with the Local Deep Research AI research assistant."
    )


def test_explicit_whatsapp_gateway_what_why_are_precise():
    description = "Chat with Dexter through WhatsApp by linking your phone to the gateway."

    assert (
        derive_project_what("Whatsapp Gateway", description, "backend_service")
        == "Whatsapp Gateway is an AI assistant gateway that lets users chat with Dexter through WhatsApp."
    )
    assert (
        derive_project_why("Whatsapp Gateway", description, "backend_service")
        == "It exists to let users access Dexter through WhatsApp by linking their phone to the gateway."
    )


def test_explicit_developer_tool_why_does_not_cms_or_ecommerce():
    description = "AI-powered developer tool that transforms code changes into structured, queryable knowledge using Gemma models."

    what = derive_project_what("ContextBridge AI", description, "fullstack_app")
    why = derive_project_why("ContextBridge AI", description, "fullstack_app")

    assert what == "ContextBridge AI is an AI-powered developer tool that transforms code changes into structured, queryable knowledge using Gemma models."
    assert why == "It exists to help teams turn code changes into structured, queryable project knowledge."
    assert "cms" not in f"{what} {why}".lower()
    assert "ecommerce" not in f"{what} {why}".lower()


def test_curriculum_derivation_is_not_backend_api_layer():
    description = "This is my multi-month study plan for becoming a software engineer for a large company."

    assert (
        derive_project_what("Coding Interview University", description, "curriculum")
        == "Coding Interview University is a study-plan repository that organizes software engineering interview preparation resources."
    )
    assert (
        derive_project_why("Coding Interview University", description, "curriculum")
        == "It exists to help learners follow a structured path toward becoming a software engineer and preparing for large-company technical interviews."
    )


def test_department_portal_uses_repo_title_in_what_and_why():
    project_name = "SIET Inceptron — CSE Department Portal"

    assert (
        derive_project_what(project_name, "", "fullstack_app")
        == "SIET Inceptron — CSE Department Portal is a professional academic coordination portal for notices, coordination, and operations."
    )
    assert (
        derive_project_why(project_name, "", "fullstack_app")
        == "It exists to centralize academic notices, coordination, and operational information in one shared portal."
    )


def test_media_player_what_is_product_surface_not_goal():
    project_name = "AI Gesture Controlled Media Player"
    description = "An interactive media player built using computer vision that allows users to control videos and music using hand gestures and facial expressions in real-time."

    what = derive_project_what(project_name, description, "backend_service")
    why = derive_project_why(project_name, description, "backend_service")

    assert "computer-vision media player interface" in what.lower()
    assert "playback control" in what.lower()
    assert what != why


def test_guard_blocks_finance_when_not_supported():
    canonical = CanonicalProjectIntelligence(
        session_id="s1",
        project_name="Sound Files For Notifications",
        project_type="frontend",
        repo_type="frontend_app",
        product_summary="Sound Files For Notifications is a web frontend for the Local Deep Research AI research assistant.",
        project_goal="Sound Files For Notifications is a web frontend for the Local Deep Research AI research assistant.",
        product_domain="ai research assistant",
        architecture_summary="Frontend application.",
        what="Sound Files For Notifications is a web frontend for the Local Deep Research AI research assistant.",
        why="It exists to support financial research workflows.",
    )

    sanitized = CanonicalOutputGuard.sanitize_canonical(canonical)

    assert sanitized.why == (
        "Sound Files For Notifications exists to coordinate the user-facing interface, interaction flow, and supporting application logic into a coherent product experience."
    )


def test_canonical_output_guard_replaces_html_logo_markup():
    canonical = CanonicalProjectIntelligence(
        session_id="s-html",
        project_name="Create And Activate Virtual Environment",
        project_type="fullstack",
        repo_type="fullstack_app",
        product_summary='<p align="center"><img src="public/branding/ahal-logo-chatgpt-transparent.png" alt="AHAL AI Logo" width="280" /></p>',
        project_goal='<p align="center">',
        product_domain="unknown",
        architecture_summary="Fullstack application.",
        what='<img src="public/branding/ahal-logo-chatgpt-transparent.png" alt="AHAL AI Logo" width="280" />',
        why='<p align="center">',
    )

    sanitized = CanonicalOutputGuard.sanitize_canonical(canonical)
    rendered = " ".join([sanitized.product_summary, sanitized.project_goal, sanitized.what, sanitized.why]).lower()

    assert sanitized.product_summary == (
        "Create And Activate Virtual Environment is organized as a fullstack application that connects the user interface, application logic, and data flow."
    )
    assert sanitized.what == (
        "Create And Activate Virtual Environment is organized as a fullstack application that connects the user interface, application logic, and data flow."
    )
    assert sanitized.why == (
        "Create And Activate Virtual Environment exists to connect the interface, application logic, and storage layer into a coherent product workflow."
    )
    for token in ("<", ">", "img", "src=", "alt=", "width=", ".png"):
        assert token not in rendered
