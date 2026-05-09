from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.intelligence.repository_type_classifier import (
    RepositoryTypeClassifier,
    is_documentation_repo_type,
    looks_like_markdown_document,
)


class PRDFactSnapshot(BaseModel):
    has_tests: bool = False
    has_database: bool = False
    has_setup: bool = False
    has_auth: bool = False
    has_deployment: bool = False
    has_ci_cd: bool = False
    has_frontend: bool = False
    has_backend: bool = False
    api_count: int = 0
    module_count: int = 0
    framework_names: list[str] = Field(default_factory=list)
    language_names: list[str] = Field(default_factory=list)
    database_names: list[str] = Field(default_factory=list)
    frontend_frameworks: list[str] = Field(default_factory=list)
    backend_frameworks: list[str] = Field(default_factory=list)
    project_type: str = "unknown"
    repo_type: str = "unknown"
    domain: Optional[str] = None
    domain_confidence: str = "low"
    product_purpose_known: bool = False


def build_fact_snapshot(scan_result=None, intelligence_result=None, prd_result=None, product_identity=None) -> PRDFactSnapshot:
    repo_type_classifier = RepositoryTypeClassifier()
    contents = getattr(scan_result, "contents", {}) if scan_result is not None else {}
    if not isinstance(contents, dict):
        contents = {}
    files = getattr(scan_result, "files", []) if scan_result is not None else []
    file_paths = [str(getattr(item, "path", item) or "") for item in files or []]
    content_paths = [str(path or "") for path in contents.keys()]
    prd_paths: list[str] = []
    if prd_result is not None:
        for api in getattr(prd_result, "api_endpoints", []) or []:
            source_file = str(getattr(api, "source_file", "") or "").strip()
            if source_file:
                prd_paths.append(source_file)
        for mod in getattr(prd_result, "modules", []) or []:
            prd_paths.extend(str(path or "") for path in (getattr(mod, "files", []) or []))
    all_paths = [path.replace("\\", "/") for path in file_paths + content_paths + prd_paths]
    path_text = " ".join(path.lower() for path in all_paths)

    frameworks = getattr(intelligence_result, "frameworks", []) if intelligence_result is not None else []
    languages = getattr(intelligence_result, "languages", []) if intelligence_result is not None else []
    databases = getattr(intelligence_result, "databases", []) if intelligence_result is not None else []
    dependencies = getattr(intelligence_result, "dependencies", []) if intelligence_result is not None else []
    api_endpoints = getattr(intelligence_result, "api_endpoints", []) if intelligence_result is not None else []
    modules = getattr(intelligence_result, "modules", []) if intelligence_result is not None else []

    framework_names = _clean_names(frameworks)
    language_names = _clean_names(languages)
    database_names = _clean_names(databases)
    dependency_names = _clean_names(dependencies)

    setup_section = getattr(prd_result, "setup_notes", None) if prd_result is not None else None
    db_section = getattr(prd_result, "databases", None) if prd_result is not None else None
    overview_section = getattr(prd_result, "overview", None) if prd_result is not None else None
    if prd_result is not None:
        if not framework_names:
            framework_names = _extract_known_tokens(
                " ".join(
                    str(getattr(section, "content", "") or "")
                    for section in (getattr(prd_result, "tech_stack", None), getattr(prd_result, "architecture", None), overview_section)
                    if section is not None
                ),
                ("FastAPI", "Flask", "Django", "Express", "React", "Vite", "Next.js", "Vue", "Angular"),
            )
        if not database_names:
            database_names = _extract_known_tokens(
                " ".join(
                    str(getattr(section, "content", "") or "")
                    for section in (getattr(prd_result, "databases", None), getattr(prd_result, "tech_stack", None))
                    if section is not None
                ),
                ("MongoDB", "PostgreSQL", "SQLite", "MySQL", "Redis"),
            )
    if not language_names:
        language_names = _infer_languages(all_paths, contents)
    if not language_names:
        lowered_frameworks = {name.lower() for name in framework_names}
        if lowered_frameworks & {"fastapi", "flask", "django"}:
            language_names.append("Python")
        elif lowered_frameworks & {"express", "next.js", "react", "vite", "vue", "angular"}:
            language_names.append("JavaScript")

    has_tests = any("test" in path.lower() for path in all_paths)
    has_database = bool(database_names) or _has_database_indicators(contents, all_paths, dependency_names)
    if not has_database and db_section is not None:
        db_text = str(getattr(db_section, "content", "") or "").lower()
        has_database = bool(db_text and "no database/storage layer detected" not in db_text and "no database detected" not in db_text)

    has_setup = _has_setup_indicators(contents)
    if not has_setup and setup_section is not None:
        setup_text = str(getattr(setup_section, "content", "") or "").lower()
        has_setup = bool(setup_text and "insufficient setup evidence" not in setup_text and "insufficient evidence" not in setup_text)

    has_deployment = any(
        marker in path.lower()
        for path in all_paths
        for marker in ("dockerfile", "docker-compose", "procfile", "vercel.json", "netlify.toml")
    )
    has_ci_cd = any(marker in path.lower() for path in all_paths for marker in (".github/workflows", "gitlab-ci", "azure-pipelines"))
    has_auth = _has_auth_indicators(modules, dependencies, contents)

    repo_type = repo_type_classifier.classify(scan_result=scan_result, intelligence_result=intelligence_result, product_identity=product_identity).repo_type
    project_type = _project_type(intelligence_result, prd_result, path_text, framework_names, repo_type)
    has_frontend = project_type in {"frontend", "fullstack"}
    has_backend = project_type in {"backend", "fullstack"}

    frontend_frameworks = [name for name in framework_names if name.lower() in {"react", "vite", "next.js", "vue", "angular", "svelte"}]
    backend_frameworks = [name for name in framework_names if name.lower() in {"fastapi", "flask", "django", "express", "nestjs", "spring"}]

    domain = getattr(product_identity, "domain", None) if product_identity is not None else None
    domain_confidence = getattr(product_identity, "domain_confidence", "low") if product_identity is not None else "low"
    if product_identity is None and overview_section is not None:
        overview_text = str(getattr(overview_section, "content", "") or "").lower()
        if "product purpose evidence is partial" not in overview_text and "maintainable workflow" not in overview_text:
            domain_confidence = "medium"
    product_purpose_known = domain_confidence in {"medium", "high"} and domain not in {None, "", "unknown", "generic_backend", "generic_fullstack"}
    if project_type == "frontend" and domain == "unknown":
        product_purpose_known = False
    if overview_section is not None and any(token in str(getattr(overview_section, "content", "") or "").lower() for token in ("product purpose evidence is partial", "maintainable workflow")):
        product_purpose_known = False

    return PRDFactSnapshot(
        has_tests=has_tests,
        has_database=has_database,
        has_setup=has_setup,
        has_auth=has_auth,
        has_deployment=has_deployment,
        has_ci_cd=has_ci_cd,
        has_frontend=has_frontend,
        has_backend=has_backend,
        api_count=len(api_endpoints or []) if api_endpoints is not None else len(getattr(prd_result, "api_endpoints", []) or []),
        module_count=len([item for item in modules or [] if getattr(item, "name", None)]),
        framework_names=framework_names,
        language_names=language_names,
        database_names=database_names,
        frontend_frameworks=frontend_frameworks,
        backend_frameworks=backend_frameworks,
        project_type=project_type,
        repo_type=repo_type,
        domain=domain,
        domain_confidence=domain_confidence,
        product_purpose_known=product_purpose_known,
    )


def _clean_names(items) -> list[str]:
    names: list[str] = []
    for item in items or []:
        name = str(getattr(item, "name", item) or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _has_database_indicators(contents: dict[str, object], paths: list[str], dependency_names: list[str]) -> bool:
    markers = ("mongodb://", "mongo_uri", "database_url", "sqlite", "pymongo", "motor", "sqlalchemy", "postgresql", "mysql", "redis")
    if any(token in " ".join(dependency_names).lower() for token in ("mongo", "postgres", "mysql", "sqlite", "sqlalchemy", "redis", "pymongo", "motor")):
        return True
    for path in paths:
        lowered = path.lower()
        if any(marker in lowered for marker in ("db.py", "database", "models.py", "schemas.py", "repository.py")):
            return True
    for value in contents.values():
        text = str(value or "").lower()
        if any(marker in text for marker in markers):
            return True
    return False


def _has_setup_indicators(contents: dict[str, object]) -> bool:
    lowered_keys = {str(key).lower() for key in contents.keys()}
    if any(key in lowered_keys for key in ("requirements.txt", "package.json", "pyproject.toml", "dockerfile")):
        return True
    for key, value in contents.items():
        if "readme" in str(key).lower():
            text = str(value or "").lower()
            if any(token in text for token in ("install", "setup", "run", "start", "build")):
                return True
    return False


def _has_auth_indicators(modules, dependencies, contents: dict[str, object]) -> bool:
    for item in modules or []:
        if any(token in str(getattr(item, attr, "") or "").lower() for attr in ("name", "category") for token in ("auth", "jwt", "oauth")):
            return True
    for item in dependencies or []:
        if any(token in str(getattr(item, "name", item) or "").lower() for token in ("auth", "jwt", "oauth")):
            return True
    return any("auth" in str(path).lower() for path in contents.keys())


def _project_type(intelligence_result, prd_result, path_text: str, framework_names: list[str], repo_type: str = "unknown") -> str:
    if is_documentation_repo_type(repo_type):
        return repo_type
    arch_value = ""
    if prd_result is not None:
        arch_value = str(getattr(prd_result, "architecture_label", "") or getattr(prd_result, "project_type", "") or "").lower()
    if not arch_value and intelligence_result is not None:
        arch = getattr(intelligence_result, "architecture", None)
        arch_value = str(getattr(arch, "type", arch or "")).lower()
    if arch_value in {"frontend", "backend", "fullstack"}:
        return arch_value
    frameworks_text = " ".join(framework_names).lower()
    has_frontend = any(token in path_text or token in frameworks_text for token in ("src/pages", "src/app", ".tsx", ".jsx", "react", "vite", "next.js"))
    has_backend = any(token in path_text or token in frameworks_text for token in ("fastapi", "flask", "django", "express", "main.py", "app.py"))
    if has_frontend and has_backend:
        return "fullstack"
    if has_frontend:
        return "frontend"
    return "unknown"


def _extract_known_tokens(text: str, tokens: tuple[str, ...]) -> list[str]:
    lowered = (text or "").lower()
    rows = []
    for token in tokens:
        if token.lower() in lowered and token not in rows:
            rows.append(token)
    return rows


def _infer_languages(paths: list[str], contents: dict[str, object]) -> list[str]:
    language_map = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".html": "HTML",
        ".css": "CSS",
    }
    rows: list[str] = []
    for path in paths:
        lowered = path.lower()
        for suffix, language in language_map.items():
            if lowered.endswith(suffix) and language not in rows:
                rows.append(language)
        if looks_like_markdown_document(lowered) and "Markdown" not in rows:
            rows.append("Markdown")
    lowered_keys = {str(key).lower() for key in contents.keys()}
    if any(key.endswith(("requirements.txt", "pyproject.toml")) for key in lowered_keys) and "Python" not in rows:
        rows.append("Python")
    if "package.json" in lowered_keys:
        if "TypeScript" not in rows and any(path.lower().endswith((".ts", ".tsx")) for path in paths):
            rows.append("TypeScript")
        elif "JavaScript" not in rows and "TypeScript" not in rows:
            rows.append("JavaScript")
    return rows
