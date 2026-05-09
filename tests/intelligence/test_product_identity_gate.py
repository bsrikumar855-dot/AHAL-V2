from app.intelligence.product_identity_gate import conservative_summary, conservative_what, conservative_why, is_generic_project_name, repo_type_label


def test_generic_project_name_uses_repository_subject():
    assert is_generic_project_name("Analyzed Project") is True
    assert conservative_summary("Analyzed Project", "backend_service") == (
        "This repository is organized as a backend service. It is structured around a maintainable workflow with clear boundaries between inputs, processing logic, and supporting assets."
    )


def test_repo_type_labels_are_conservative():
    assert repo_type_label("fullstack_app") == "fullstack application"
    assert repo_type_label("backend_service") == "backend service"


def test_conservative_what_and_why_are_unknown_first():
    assert conservative_what("Repo", "frontend_app") == (
        "This repository is a frontend application that is structured around the repository's primary workflow and supporting implementation details."
    )
    assert conservative_why() == "It is intended to centralize the repository's core workflow within a maintainable, reviewable implementation boundary."
