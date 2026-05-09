from __future__ import annotations


WEAK_PRODUCT_SIGNALS = {
    "summarization",
    "session tracking",
    "chat",
    "query",
    "report generation",
    "dashboard",
    "status endpoint",
    "health endpoint",
    "docker",
    "ci/cd",
    "auth",
    "database",
    "upload",
    "api surface",
}

GENERIC_PROJECT_NAMES = {"analyzed project", "uploaded project", "untitled", "project", "repo"}

INSTRUCTIONAL_PROJECT_PHRASES = {
    "create and activate virtual environment",
    "create virtual environment",
    "activate virtual environment",
    "set up virtual environment",
    "setup virtual environment",
    "install dependencies",
    "run the app",
    "run the application",
    "run project",
    "getting started",
    "quick start",
    "clone the repository",
}


def is_generic_project_name(project_name: str) -> bool:
    return str(project_name or "").strip().lower() in GENERIC_PROJECT_NAMES


def is_instructional_project_name(project_name: str) -> bool:
    value = str(project_name or "").strip().lower()
    if not value:
        return False
    if value in INSTRUCTIONAL_PROJECT_PHRASES:
        return True
    if any(value.startswith(prefix) for prefix in ("create ", "activate ", "install ", "run ", "set up ", "setup ", "getting started", "quick start", "how to ")):
        return True
    if "virtual environment" in value and any(token in value for token in ("create", "activate", "setup", "set up", "install")):
        return True
    return False


def repo_type_label(repo_type: str, project_type: str = "") -> str:
    raw = str(repo_type or project_type or "repository").strip().lower()
    if raw in {"", "unknown"}:
        return "software project"
    mapping = {
        "backend_service": "backend service",
        "frontend_app": "frontend application",
        "fullstack_app": "fullstack application",
        "backend": "backend service",
        "frontend": "frontend application",
        "fullstack": "fullstack application",
        "cli_tool": "command-line tool repository",
    }
    return mapping.get(raw, raw.replace("_", " ") or "repository")


def conservative_summary(project_name: str, repo_type: str, project_type: str = "") -> str:
    label = repo_type_label(repo_type, project_type)
    subject = "This repository" if is_generic_project_name(project_name) else project_name
    if subject == "This repository":
        return f"This repository is organized as a {label}. It is structured around a maintainable workflow with clear boundaries between inputs, processing logic, and supporting assets."
    return f"{subject} is organized as a {label}. It is structured around a maintainable workflow with clear boundaries between inputs, processing logic, and supporting assets."


def conservative_what(project_name: str, repo_type: str, project_type: str = "") -> str:
    label = repo_type_label(repo_type, project_type)
    subject = "This repository" if is_generic_project_name(project_name) else project_name
    return f"{subject} is a {label} that is structured around the repository's primary workflow and supporting implementation details."


def conservative_why() -> str:
    return "It is intended to centralize the repository's core workflow within a maintainable, reviewable implementation boundary."
