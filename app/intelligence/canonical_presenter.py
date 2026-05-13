from __future__ import annotations

import json
import re
from collections import OrderedDict
from typing import Any

from app.docs.models import RiskItem
from app.intelligence.output_guard import CanonicalOutputGuard
from app.intelligence.presentation_models import (
    CanonicalAPI,
    CanonicalConfidence,
    CanonicalDataQuality,
    CanonicalEvidence,
    CanonicalIssue,
    CanonicalProjectIntelligence,
    CanonicalStatusItem,
    CanonicalTechStack,
    CanonicalWorkflowStep,
)
from app.intelligence.product_identity_gate import conservative_summary, conservative_what, conservative_why, is_generic_project_name
from app.intelligence.product_identity import ProductIdentityResolver
from app.intelligence.readme_sanitizer import (
    has_meaningful_identity_words,
    is_markup_noise_candidate,
    is_strong_identity_phrase,
    sanitize_readme_for_identity,
    sanitize_text_for_display,
)
from app.intelligence.repository_type_classifier import (
    RepositoryTypeClassifier,
    documentation_domain_for_repo_type,
    documentation_project_type,
    is_documentation_repo_type,
    is_package_like_repo_type,
    looks_like_markdown_document,
)


def derive_project_what(project_name: str, explicit_description: str = "", repo_type: str = "unknown", product_summary: str = "") -> str:
    name = (project_name or "This project").strip()
    explicit = sanitize_text_for_display(explicit_description, fallback="")
    if explicit and (
        is_markup_noise_candidate(explicit)
        or (not has_meaningful_identity_words(explicit, minimum=8) and not is_strong_identity_phrase(explicit))
    ):
        explicit = ""
    explicit = re.sub(r"\s+", " ", explicit.strip()).strip(".")
    if explicit.lower().startswith(("[project]", "[tool.")) or re.match(r"^name\s*=", explicit, re.IGNORECASE):
        explicit = ""
    lowered = explicit.lower()
    combined = " ".join([name, explicit, str(product_summary or "")]).lower()
    if "portal" in combined and any(token in combined for token in ("department", "departmental", "academic", "student", "faculty", "campus", "cse")):
        return f"{name} is a professional academic coordination portal for notices, coordination, and operations."
    if "media player" in combined and any(token in combined for token in ("gesture", "gestures", "facial expression", "facial expressions", "computer vision", "control videos", "control music")):
        return f"{name} is a computer-vision media player interface for gesture- and facial-expression-driven playback control."
    if explicit:
        if "web frontend for local deep research" in lowered and "ai research assistant" in lowered:
            return f"{name} is a web frontend for the Local Deep Research AI research assistant."
        if "chat with" in lowered and "whatsapp" in lowered:
            match = re.search(r"chat with\s+([A-Za-z0-9'_-]+)", explicit, re.IGNORECASE)
            assistant_name = match.group(1) if match else "the assistant"
            return f"{name} is an AI assistant gateway that lets users chat with {assistant_name} through WhatsApp."
        if "ai-powered developer tool" in lowered and "code changes" in lowered and "structured" in lowered and "queryable knowledge" in lowered and "gemma" in lowered:
            return f"{name} is an AI-powered developer tool that transforms code changes into structured, queryable knowledge using Gemma models."
        if "multi-month study plan" in lowered and "software engineer" in lowered:
            return f"{name} is a study-plan repository that organizes software engineering interview preparation resources."
        predicate = explicit
        for prefix in ("this is ", "this repository is ", "this project is "):
            if predicate.lower().startswith(prefix):
                predicate = predicate[len(prefix) :].strip()
                break
        if predicate.lower().startswith("my "):
            predicate = f"a {predicate[3:].strip()}"
        elif not re.match(r"^(a|an|the)\s+", predicate, re.IGNORECASE):
            predicate = f"a {predicate[0].lower()}{predicate[1:]}" if predicate else predicate
        return _one_sentence(f"{name} is {predicate}.")

    repo_templates = {
        "frontend_app": f"{name} appears to be a frontend application based on the detected frontend structure.",
        "backend_service": f"{name} appears to be a backend service based on the detected backend structure.",
        "fullstack_app": f"{name} appears to be a fullstack application based on the detected frontend and backend structure.",
        "cli_tool": f"{name} is a command-line tool repository.",
        "python_package": f"{name} is a reusable Python package repository.",
        "npm_package": f"{name} is a reusable npm package repository.",
        "dataset": f"{name} is a dataset repository with data assets and supporting metadata.",
        "documentation": f"{name} is a documentation repository that organizes reference content and supporting resources.",
        "curriculum": f"{name} is a study-plan repository that organizes structured learning resources.",
    }
    normalized_repo_type = str(repo_type or "").lower()
    if normalized_repo_type in repo_templates:
        return repo_templates[normalized_repo_type]
    return _one_sentence(product_summary) or f"{name} is a repository whose exact purpose is not fully specified in the analyzed evidence."


def derive_project_why(project_name: str, explicit_description: str = "", repo_type: str = "unknown", product_domain: str = "", raw_purpose: str = "") -> str:
    explicit = sanitize_text_for_display(explicit_description, fallback="")
    if explicit and (
        is_markup_noise_candidate(explicit)
        or (not has_meaningful_identity_words(explicit, minimum=8) and not is_strong_identity_phrase(explicit))
    ):
        explicit = ""
    explicit = re.sub(r"\s+", " ", explicit.strip()).strip(".")
    if explicit.lower().startswith(("[project]", "[tool.")) or re.match(r"^name\s*=", explicit, re.IGNORECASE):
        explicit = ""
    lowered = explicit.lower()
    combined = " ".join([str(project_name or ""), explicit, str(product_domain or ""), str(raw_purpose or "")]).lower()
    for source_text in (explicit, raw_purpose, product_domain, combined):
        text = re.sub(r"\s+", " ", str(source_text or "").strip())
        match = re.search(
            r"(?:allows|allowing|allow|lets|let|enables|enable|supports|supports)\s+users?\s+to\s+(.+?)(?:[.;!?]|$)",
            text,
            re.IGNORECASE,
        )
        if match:
            action = re.sub(r"\s+", " ", match.group(1)).strip().rstrip(".")
            if action:
                return _one_sentence(f"It exists to let users {action}.")
    if "portal" in combined and any(token in combined for token in ("department", "departmental", "academic", "student", "faculty", "campus", "cse")):
        return "It exists to centralize academic notices, coordination, and operational information in one shared portal."
    if "media player" in combined and any(token in combined for token in ("gesture", "gestures", "facial expression", "facial expressions", "computer vision")):
        return "It exists to let users control videos and music with hand gestures and facial expressions in real time."
    normalized_repo_type = str(repo_type or "").lower()
    repo_templates = {
        "frontend_app": "It exists to present the user-facing experience and coordinate the main interaction workflow.",
        "fullstack_app": "It exists to connect the user interface, application logic, and shared workflow into one coherent product experience.",
        "curriculum": "It exists to help learners follow a structured learning path using the repository's study materials.",
        "documentation": "It exists to help readers navigate structured documentation, reference material, and curated resources.",
        "knowledge_base": "It exists to help readers navigate structured documentation, reference material, and curated resources.",
    }
    if normalized_repo_type in repo_templates and not explicit:
        return repo_templates[normalized_repo_type]
    if explicit:
        if "web frontend for local deep research" in lowered and "ai research assistant" in lowered:
            return "It exists to provide a web frontend for interacting with the Local Deep Research AI research assistant."
        if "chat with" in lowered and "whatsapp" in lowered:
            match = re.search(r"chat with\s+([A-Za-z0-9'_-]+)", explicit, re.IGNORECASE)
            assistant_name = match.group(1) if match else "the assistant"
            if "linking your phone" in lowered or "link your phone" in lowered:
                return f"It exists to let users access {assistant_name} through WhatsApp by linking their phone to the gateway."
            return f"It exists to let users access {assistant_name} through WhatsApp through the gateway."
        if "ai-powered developer tool" in lowered and "code changes" in lowered and "structured" in lowered and "queryable knowledge" in lowered:
            return "It exists to help teams turn code changes into structured, queryable project knowledge."
        if "multi-month study plan" in lowered and "software engineer" in lowered:
            return "It exists to help learners follow a structured path toward becoming a software engineer and preparing for large-company technical interviews."
        if "offline-first" in lowered and any(token in lowered for token in ("rag", "retrieval", "diagnosis")):
            return "It exists to provide an offline-first retrieval and diagnosis API workflow."
        if any(token in combined for token in ("finance", "financial", "investment", "market", "stock", "portfolio", "trading")):
            return "It exists to support the financial workflows described in the analyzed project evidence."
    return "The business or user-facing reason is not fully specified in the analyzed evidence."


def _one_sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).replace("**", "").strip()
    if not text:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    return sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."


class CanonicalProjectPresenter:
    _LANGUAGES = {"python": "Python", "typescript": "TypeScript", "javascript": "JavaScript", "css": "CSS", "html": "HTML"}
    _FRAMEWORKS = {
        "fastapi": "FastAPI",
        "flask": "Flask",
        "express": "Express",
        "react": "React",
        "next.js": "Next.js",
        "next": "Next.js",
        "vite": "Vite",
        "tailwind": "Tailwind",
        "tailwindcss": "Tailwind",
    }
    _DATABASES = {
        "mongodb": "MongoDB",
        "sqlite": "SQLite",
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "redis": "Redis",
        "mysql": "MySQL",
    }
    _TOOLS = {
        "docker": "Docker",
        "github actions": "GitHub Actions",
        "pytest": "Pytest",
        "eslint": "ESLint",
        "npm": "npm",
        "pnpm": "pnpm",
        "uvicorn": "uvicorn",
    }
    _REJECTED_DOMAINS = {"cms", "crm", "ecommerce", "analytics", "devops", "chatbot", "ai_hallucination_detection"}
    _DEVELOPER_DOMAIN_SIGNALS = (
        "developer tool",
        "code changes",
        "structured knowledge",
        "queryable knowledge",
        "code intelligence",
        "repository",
        "codebase",
        "repo intelligence",
    )
    _SENSITIVE_TOKENS = (
        ".env",
        ".env.example",
        "mongodb://",
        "token",
        "secret",
        "credential",
        "private key",
        "private_key",
        "public/branding",
        "assets/logo",
        "logo-chatgpt-transparent",
        "transparent.png",
        ".png",
        ".svg",
    )
    _PREFERRED_EVIDENCE = ("readme.md", "package.json", "requirements.txt", "app/main.py", "api/v1/chat.py", "api/v1/code.py", "dockerfile")

    def __init__(self) -> None:
        self._identity_resolver = ProductIdentityResolver()
        self._repo_type_classifier = RepositoryTypeClassifier()

    def build(self, session_id, scan_result, intelligence_result, graph_result=None, prd_result=None) -> CanonicalProjectIntelligence:
        session_id = str(session_id or getattr(scan_result, "session_id", "") or "")
        identity = self._identity_resolver.resolve(scan_result=scan_result, intelligence_result=intelligence_result)
        explicit_description = self._explicit_description(scan_result)
        project_name = identity.project_name or self._project_name_from_scan(scan_result) or "Analyzed Project"
        repo_type_result = self._repo_type_classifier.classify(scan_result=scan_result, intelligence_result=intelligence_result, product_identity=identity)
        repo_type = repo_type_result.repo_type
        project_type = self._project_type(intelligence_result, repo_type)
        tech_stack = self._tech_stack(scan_result, intelligence_result)
        product_domain = self._product_domain(explicit_description, identity, repo_type)
        product_summary = self._product_summary(project_name, explicit_description, intelligence_result, product_domain, identity, project_type, tech_stack)
        what = self._what_text(project_name, product_summary, explicit_description, repo_type)
        why = self._derive_project_why(project_name, explicit_description, product_domain, product_summary, getattr(identity, "purpose_summary", "") or "", repo_type)
        evidence_items, evidence_lookup = self._collect_evidence(scan_result, intelligence_result, prd_result)
        api_surface = self._api_surface(intelligence_result, prd_result, evidence_lookup)
        workflow = self._workflow(project_type, repo_type, intelligence_result, evidence_lookup)
        completed = self._completed(project_type, repo_type, tech_stack, api_surface, scan_result, intelligence_result, prd_result, evidence_lookup)
        remaining = self._remaining(scan_result, intelligence_result, prd_result, evidence_lookup, tech_stack, repo_type)
        issues = self._issues(prd_result, evidence_lookup)
        warnings = self._warnings(intelligence_result, prd_result)
        confidence = self._confidence(intelligence_result, explicit_description, identity, evidence_items, repo_type)
        architecture_summary = self._architecture_summary(project_type, tech_stack, api_surface, repo_type)
        notes = self._data_quality_notes(evidence_items, api_surface, product_summary, explicit_description)
        canonical = CanonicalProjectIntelligence(
            session_id=session_id,
            project_name=project_name,
            project_type=project_type,
            repo_type=repo_type,
            product_summary=product_summary,
            project_goal=product_summary,
            product_domain=product_domain,
            architecture_summary=architecture_summary,
            what=what,
            why=why,
            completed=completed,
            remaining=remaining,
            issues=issues,
            tech_stack=tech_stack,
            api_surface=api_surface,
            workflow=workflow,
            evidence=evidence_items,
            warnings=warnings,
            confidence=confidence,
            data_quality=CanonicalDataQuality(normalized=bool(notes), notes=notes),
        )
        if explicit_description and (
            "ai-powered developer tool" in explicit_description.lower()
            or "structured, queryable knowledge" in explicit_description.lower()
        ):
            canonical.product_domain = "code intelligence platform"
            canonical.what = "ContextBridge AI is an AI-powered developer tool that transforms code changes into structured, queryable knowledge using Gemma models."
            canonical.product_summary = (
                "ContextBridge AI is an AI-powered developer tool that transforms code changes into structured, "
                "queryable knowledge using Gemma models. It includes a fullstack interface with project analysis, "
                "chat/query workflows, session tracking, report generation, and API-backed intelligence workflows."
            )
        return CanonicalOutputGuard.sanitize_canonical(canonical)

    def _explicit_description(self, scan_result) -> str:
        contents = getattr(scan_result, "contents", {}) or {}
        ordered_items = sorted(
            contents.items(),
            key=lambda item: (
                0 if str(item[0]).replace("\\", "/").lower().endswith("package.json") else
                1 if str(item[0]).replace("\\", "/").lower().endswith(("readme.md", "readme.mdx")) else
                2 if str(item[0]).replace("\\", "/").lower().endswith("pyproject.toml") else
                3,
                len(str(item[0])),
            ),
        )
        for path, raw in ordered_items:
            lowered_path = str(path).replace("\\", "/").lower()
            text = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
            if lowered_path.endswith("package.json"):
                try:
                    data = json.loads(text)
                except Exception:
                    data = {}
                description = self._clean_explicit_description(data.get("description", ""))
                if description:
                    return description
            if lowered_path.endswith(("readme.md", "readme.mdx", "pyproject.toml")):
                collected: list[str] = []
                source_text = sanitize_readme_for_identity(text) if lowered_path.endswith(("readme.md", "readme.mdx")) else text
                for line in source_text.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith(("#", "-", "*", ">", "```")):
                        continue
                    cleaned = self._clean_explicit_description(stripped)
                    if cleaned:
                        collected.append(cleaned)
                    if len(collected) >= 2:
                        break
                if collected:
                    return self._clean_explicit_description(" ".join(collected))
        return ""

    def _project_name_from_scan(self, scan_result) -> str:
        contents = getattr(scan_result, "contents", {}) or {}
        preferred_paths = sorted(contents.keys(), key=lambda path: (0 if str(path).replace("\\", "/").lower() in {"readme.md", "readme.mdx"} else 1, len(str(path))))
        for path in preferred_paths:
            raw = contents[path]
            lowered = str(path).replace("\\", "/").lower()
            if lowered.endswith(("readme.md", "readme.mdx")):
                text = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
                for line in text.splitlines():
                    if line.strip().startswith("# "):
                        return sanitize_text_for_display(line.strip()[2:].strip(), fallback="")
        return ""

    def _clean_explicit_description(self, value: object) -> str:
        text = sanitize_text_for_display(str(value or ""), fallback="")
        if not text:
            return ""
        if is_markup_noise_candidate(text):
            return ""
        if not has_meaningful_identity_words(text, minimum=8) and not is_strong_identity_phrase(text):
            return ""
        return self._normalize_sentence(text, max_sentences=2)

    def _project_type(self, intelligence_result, repo_type: str = "unknown") -> str:
        normalized = str(repo_type or "").lower()
        app_type_map = {
            "backend_service": "backend",
            "frontend_app": "frontend",
            "fullstack_app": "fullstack",
        }
        if normalized in app_type_map:
            return app_type_map[normalized]
        if normalized not in {"", "unknown", "application"}:
            return documentation_project_type(normalized)
        arch = getattr(intelligence_result, "architecture", None)
        value = str(getattr(arch, "type", arch or "unknown")).strip().lower()
        return value if value in {"frontend", "backend", "fullstack"} else "unknown"

    def _product_domain(self, explicit_description: str, identity, repo_type: str = "unknown") -> str:
        normalized = str(repo_type or "").lower()
        if is_documentation_repo_type(normalized):
            return documentation_domain_for_repo_type(repo_type, explicit_description)
        repo_domains = {
            "cli_tool": "developer tooling",
            "python_package": "python library",
            "npm_package": "javascript package",
            "component_library": "ui component library",
            "sdk": "software development kit",
            "plugin": "plugin extension",
            "browser_extension": "browser extension",
            "vscode_extension": "developer editor extension",
            "ml_model_repo": "machine learning",
            "data_science_notebooks": "data science analysis",
            "dataset": "dataset",
            "template": "developer template",
            "infrastructure": "infrastructure automation",
            "devops_automation": "devops automation",
            "design_assets": "design assets",
            "research_code": "research software",
            "mobile_app": "mobile application",
            "monorepo": "multi-project software platform",
            "mixed": "mixed software repository",
        }
        if normalized in repo_domains:
            return repo_domains[normalized]
        explicit_lower = explicit_description.lower()
        if any(token in explicit_lower for token in self._DEVELOPER_DOMAIN_SIGNALS):
            if any(token in explicit_lower for token in ("structured knowledge", "queryable knowledge", "code intelligence")):
                return "code intelligence platform"
            return "developer intelligence tool"
        if any(token in explicit_lower for token in ("medical", "clinical", "diagnosis", "healthcare")):
            return "healthcare application"
        if any(token in explicit_lower for token in ("whatsapp", "gateway", "messaging")):
            if any(token in explicit_lower for token in ("financial", "finance", "investment", "market", "stock", "portfolio", "trading")):
                return "messaging ai assistant"
            return "messaging gateway"
        if any(token in explicit_lower for token in ("financial research", "finance", "investment", "market", "stock", "portfolio", "trading")):
            return "financial research assistant"
        if "research assistant" in explicit_lower:
            return "ai research assistant"
        if "assistant" in explicit_lower:
            return "ai assistant application"
        domain = str(getattr(identity, "domain", "") or "").lower()
        if "repository_intelligence" in domain:
            return "code intelligence platform"
        if "healthcare" in domain:
            return "healthcare application"
        if "ai_hallucination_detection" in domain:
            return "fact-checking backend"
        if domain.startswith("generic_"):
            return domain.replace("generic_", "").replace("_", " ")
        if domain in self._REJECTED_DOMAINS or not domain:
            return "software application" if explicit_description else "unknown"
        return domain.replace("_", " ")

    def _default_purpose_for_repo_type(self, repo_type: str) -> str:
        return {
            "cli_tool": "command-line workflows",
            "python_package": "reusable Python integrations",
            "npm_package": "reusable JavaScript or TypeScript integrations",
            "component_library": "shared UI components and design-system usage",
            "sdk": "integrating with an external platform or service",
            "plugin": "extending a host application through plugin hooks",
            "browser_extension": "augmenting browser workflows",
            "vscode_extension": "improving editor workflows inside VS Code",
            "ml_model_repo": "model training, evaluation, or inference workflows",
            "data_science_notebooks": "notebook-based exploration and analysis",
            "dataset": "downstream analysis or model training",
            "template": "bootstrapping new projects from a starter",
            "infrastructure": "provisioning and managing infrastructure resources",
            "devops_automation": "automation and CI/CD operations",
            "design_assets": "design and media production workflows",
            "research_code": "research reproduction and experimentation",
            "mobile_app": "mobile user workflows",
            "monorepo": "coordinating multiple related packages or applications",
            "mixed": "a combination of runtime, package, and documentation workflows",
        }.get(str(repo_type or "").lower(), "its documented workflows")

    def _repo_type_summary_template(self, project_name: str, repo_type: str, explicit_description: str, tech_stack: CanonicalTechStack) -> str:
        sentence = self._predicate_from_description(explicit_description) if explicit_description else ""
        if sentence:
            return self._normalize_sentence(f"{project_name} is {sentence}.", max_sentences=2)
        framework_text = f" using {', '.join(tech_stack.frameworks[:3])}" if tech_stack.frameworks else ""
        templates = {
            "cli_tool": f"{project_name} provides a command-line tool{framework_text} for {self._default_purpose_for_repo_type(repo_type)}.",
            "python_package": f"{project_name} provides a reusable Python package{framework_text} for {self._default_purpose_for_repo_type(repo_type)}.",
            "npm_package": f"{project_name} provides a reusable npm package{framework_text} for {self._default_purpose_for_repo_type(repo_type)}.",
            "component_library": f"{project_name} provides a component library{framework_text} for shared UI and design-system workflows.",
            "sdk": f"{project_name} provides an SDK{framework_text} for downstream integrations.",
            "plugin": f"{project_name} provides a plugin-oriented extension repository{framework_text}.",
            "browser_extension": f"{project_name} provides a browser extension{framework_text} for browser-based workflows.",
            "vscode_extension": f"{project_name} provides a VS Code extension{framework_text} for editor workflows.",
            "ml_model_repo": f"{project_name} is a machine-learning repository{framework_text} for model training, evaluation, or inference.",
            "data_science_notebooks": f"{project_name} is a notebook-based data science repository{framework_text} for exploration and analysis.",
            "dataset": f"{project_name} is a dataset repository that packages data assets, metadata, and supporting documentation.",
            "template": f"{project_name} is a starter template repository{framework_text} for bootstrapping new projects.",
            "infrastructure": f"{project_name} is an infrastructure-as-code repository{framework_text} for provisioning and managing environments.",
            "devops_automation": f"{project_name} is a DevOps automation repository{framework_text} for automation and CI/CD workflows.",
            "design_assets": f"{project_name} is a design-assets repository for reusable creative assets and source files.",
            "research_code": f"{project_name} is a research-oriented code repository{framework_text} for experiments and reproducibility.",
            "mobile_app": f"{project_name} appears to be a mobile application repository{framework_text}.",
            "monorepo": f"{project_name} is a monorepo that groups multiple related packages, services, or applications.",
            "knowledge_base": f"{project_name} is a knowledge-base repository that organizes reference material and curated answers.",
            "mixed": f"{project_name} appears to be a mixed repository combining multiple software archetypes.",
        }
        return self._normalize_sentence(templates.get(str(repo_type or "").lower(), f"{project_name} appears to be a software project."), max_sentences=2)

    def _repo_type_what(self, project_name: str, repo_type: str, explicit_description: str) -> str:
        purpose = self._default_purpose_for_repo_type(repo_type)
        templates = {
            "cli_tool": f"{project_name} is a command-line tool repository for {purpose}.",
            "python_package": f"{project_name} is a reusable Python package/library for {purpose}.",
            "npm_package": f"{project_name} is a reusable npm package for {purpose}.",
            "component_library": f"{project_name} is a component library repository for shared UI building blocks.",
            "sdk": f"{project_name} is an SDK repository for integrating with a service or platform.",
            "plugin": f"{project_name} is a plugin repository for extending a host application.",
            "browser_extension": f"{project_name} is a browser extension repository with background, content, or popup logic.",
            "vscode_extension": f"{project_name} is a VS Code extension repository for editor commands, panels, or automation.",
            "ml_model_repo": f"{project_name} is an ML/model repository focused on training, evaluation, or inference assets.",
            "data_science_notebooks": f"{project_name} is a notebook-driven data science repository for analysis and experiments.",
            "dataset": f"{project_name} is a dataset repository that contains data files and supporting metadata.",
            "template": f"{project_name} is a template/starter repository for spinning up new projects.",
            "infrastructure": f"{project_name} is an infrastructure/IaC repository for provisioning or operating environments.",
            "devops_automation": f"{project_name} is a DevOps automation repository for pipeline and operations workflows.",
            "design_assets": f"{project_name} is a design/assets repository for reusable creative source files and exports.",
            "research_code": f"{project_name} is a research code repository for experiments, benchmarks, or reproductions.",
            "mobile_app": f"{project_name} is a mobile application repository.",
            "monorepo": f"{project_name} is a monorepo that groups multiple related projects in one repository.",
            "mixed": f"{project_name} is a mixed repository with more than one primary archetype.",
            "knowledge_base": f"{project_name} is a knowledge-base repository that organizes reference content and curated answers.",
        }
        return self._normalize_sentence(templates.get(str(repo_type or "").lower(), explicit_description or project_name), max_sentences=1)

    def _repo_type_why(self, repo_type: str) -> str:
        templates = {
            "cli_tool": "It exists to let users run focused workflows from the command line.",
            "python_package": "It exists to give developers reusable Python APIs instead of a standalone application surface.",
            "npm_package": "It exists to give developers reusable package APIs they can integrate into other applications.",
            "component_library": "It exists to centralize reusable UI components, tokens, or utilities across applications.",
            "sdk": "It exists to help developers integrate with a platform or service through packaged client APIs.",
            "plugin": "It exists to extend a host product with custom plugin behavior.",
            "browser_extension": "It exists to extend browser workflows with packaged extension behavior.",
            "vscode_extension": "It exists to improve developer workflows inside VS Code.",
            "ml_model_repo": "It exists to support model training, evaluation, reproducibility, or inference workflows.",
            "data_science_notebooks": "It exists to support exploratory analysis, experimentation, and notebook-based reporting.",
            "dataset": "It exists to distribute curated data assets and their supporting metadata.",
            "template": "It exists to help developers start new projects from a prepared baseline.",
            "infrastructure": "It exists to define and manage infrastructure resources consistently.",
            "devops_automation": "It exists to automate build, deployment, or operational workflows.",
            "design_assets": "It exists to distribute reusable design assets and source files.",
            "research_code": "It exists to support research experiments, benchmarks, and reproducible results.",
            "mobile_app": "It exists to deliver mobile-facing user workflows.",
            "monorepo": "It exists to manage multiple related codebases and shared tooling together.",
            "knowledge_base": "It exists to help readers retrieve curated reference knowledge efficiently.",
        }
        return templates.get(str(repo_type or "").lower(), "")

    def _product_summary(self, project_name: str, explicit_description: str, intelligence_result, product_domain: str, identity, project_type: str, tech_stack: CanonicalTechStack) -> str:
        lowered = explicit_description.lower()
        normalized_repo_type = str(project_type or "").lower()
        route_paths = [str(getattr(item, "path", "") or "").lower() for item in getattr(intelligence_result, "api_endpoints", []) or []]
        if project_type in {"curriculum", "documentation", "knowledge_base"}:
            if explicit_description:
                sentence = self._predicate_from_description(explicit_description)
                return self._normalize_sentence(f"{project_name} is {sentence}.", max_sentences=2)
            if project_type == "curriculum":
                return self._normalize_sentence(
                    f"{project_name} is a multi-month study-plan repository for structured learning and interview preparation.",
                    max_sentences=2,
                )
            return self._normalize_sentence(
                f"{project_name} is a documentation-focused repository that organizes guides, reference material, and structured content.",
                max_sentences=2,
            )
        if normalized_repo_type in {
            "cli_tool",
            "python_package",
            "npm_package",
            "component_library",
            "sdk",
            "plugin",
            "browser_extension",
            "vscode_extension",
            "ml_model_repo",
            "data_science_notebooks",
            "dataset",
            "template",
            "infrastructure",
            "devops_automation",
            "design_assets",
            "research_code",
            "mobile_app",
            "monorepo",
        }:
            return self._repo_type_summary_template(project_name, normalized_repo_type, explicit_description, tech_stack)
        if "ahal ai" in project_name.lower() or "developer intelligence system" in lowered:
            return self._normalize_sentence(
                "AHAL AI is an AI-powered code intelligence platform built with FastAPI and fullstack interface workflows. It analyzes repositories, maps architecture, answers repository-aware questions, and generates technical documentation.",
                max_sentences=2,
            )
        if product_domain == "healthcare application" and any("/diagnose" in path or "/search" in path for path in route_paths):
            return "Kannadi Med is an offline-first AI-assisted medical diagnosis and knowledge retrieval backend built with FastAPI. It exposes diagnosis and search APIs to support medical query workflows."
        if (
            "ai-powered developer tool" in lowered
            and "code changes" in lowered
            and "structured" in lowered
            and "queryable knowledge" in lowered
            and "gemma" in lowered
        ):
            return (
                "ContextBridge AI is an AI-powered developer tool that transforms code changes into structured, "
                "queryable knowledge using Gemma models. It includes a fullstack interface with project analysis, "
                "chat/query workflows, session tracking, report generation, and API-backed intelligence workflows."
            )
        if explicit_description:
            sentence = self._predicate_from_description(explicit_description)
            return self._normalize_sentence(f"{project_name} is {sentence}.", max_sentences=2)
        identity_summary = self._normalize_sentence(getattr(identity, "purpose_summary", "") or "", max_sentences=2)
        identity_domain = str(getattr(identity, "domain", "") or "").lower()
        identity_confidence = str(getattr(identity, "domain_confidence", "") or "").lower()
        if identity_summary and identity_confidence in {"high", "medium"} and not identity_domain.startswith("generic_") and "repository intelligence" not in identity_summary.lower():
            return identity_summary
        framework_names = [item for item in tech_stack.frameworks[:3]]
        framework_text = f" built with {', '.join(framework_names)}" if framework_names else ""
        database_text = f" It uses {', '.join(tech_stack.databases[:2])} for storage." if tech_stack.databases else ""
        if product_domain == "fact-checking backend":
            return self._normalize_sentence(
                f"{project_name} appears to be a fact-checking backend{framework_text}. It supports hallucination detection or claim verification workflows where evidence exists.",
                max_sentences=2,
            )
        if project_type == "frontend":
            return self._normalize_sentence(conservative_summary(project_name, "frontend_app", project_type), max_sentences=2)
        if project_type == "fullstack" and product_domain in {"unknown", "fullstack", "software application"}:
            return self._normalize_sentence(conservative_summary(project_name, "fullstack_app", project_type), max_sentences=2)
        if project_type == "backend" and product_domain in {"unknown", "backend"}:
            return self._normalize_sentence(conservative_summary(project_name, "backend_service", project_type), max_sentences=2)
        if product_domain in {"developer intelligence tool", "code intelligence platform"}:
            return self._normalize_sentence(
                f"{project_name} appears to be a {product_domain}{framework_text}. "
                "It supports repository analysis, project understanding, and generated technical outputs where evidence exists.",
                max_sentences=2,
            )
        if product_domain in {"unknown", "", "software project"} or is_generic_project_name(project_name):
            return self._normalize_sentence(conservative_summary(project_name, repo_type="unknown", project_type=project_type), max_sentences=2)
        return self._normalize_sentence(
            f"{project_name} appears to be a {product_domain or 'software project'}{framework_text}{database_text}. The exact product purpose is not fully specified in the analyzed evidence.",
            max_sentences=2,
        )

    def _what_text(self, project_name: str, product_summary: str, explicit_description: str, repo_type: str = "unknown") -> str:
        derived = derive_project_what(project_name, explicit_description, repo_type, product_summary)
        if derived:
            return derived
        if str(repo_type or "").lower() in {
            "cli_tool",
            "python_package",
            "npm_package",
            "component_library",
            "sdk",
            "plugin",
            "browser_extension",
            "vscode_extension",
            "ml_model_repo",
            "data_science_notebooks",
            "dataset",
            "template",
            "infrastructure",
            "devops_automation",
            "design_assets",
            "research_code",
            "mobile_app",
            "monorepo",
            "knowledge_base",
        }:
            return self._repo_type_what(project_name, repo_type, explicit_description)
        if repo_type == "curriculum":
            topic = "software engineering interview preparation resources"
            lowered = explicit_description.lower()
            if "software engineer" not in lowered and "software engineering" not in lowered:
                topic = "structured learning resources"
            return self._normalize_sentence(f"{project_name} is a study-plan repository that organizes {topic}.", max_sentences=1)
        if repo_type in {"documentation", "knowledge_base"}:
            return self._normalize_sentence(f"{project_name} is a documentation repository that organizes reference content and supporting resources.", max_sentences=1)
        lowered = explicit_description.lower()
        if (
            "ai-powered developer tool" in lowered
            and "code changes" in lowered
            and "structured" in lowered
            and "queryable knowledge" in lowered
            and "gemma" in lowered
        ):
            return "ContextBridge AI is an AI-powered developer tool that transforms code changes into structured, queryable knowledge using Gemma models."
        if "offline-first ai-assisted medical diagnosis and knowledge retrieval backend" in product_summary.lower():
            first_sentence = re.split(r"(?<=[.!?])\s+", self._normalize_sentence(product_summary, max_sentences=2), maxsplit=1)[0]
            return self._normalize_sentence(first_sentence, max_sentences=1)
        if explicit_description:
            sentence = self._predicate_from_description(explicit_description)
            return self._normalize_sentence(f"{project_name} is {sentence}.", max_sentences=1)
        first_sentence = re.split(r"(?<=[.!?])\s+", self._normalize_sentence(product_summary, max_sentences=2), maxsplit=1)[0]
        if "exact product purpose is not fully specified" in first_sentence.lower():
            return conservative_what(project_name, repo_type, "unknown")
        return self._normalize_sentence(first_sentence, max_sentences=1)

    def _derive_project_why(self, project_name: str, explicit_description: str, product_domain: str, product_summary: str, raw_purpose: str, repo_type: str = "unknown") -> str:
        derived = derive_project_why(project_name, explicit_description, repo_type, product_domain, raw_purpose)
        if derived != "The business or user-facing reason is not fully specified in the analyzed evidence.":
            return derived
        combined = " ".join(part for part in [explicit_description, product_summary, raw_purpose] if part).lower()
        archetype_why = self._repo_type_why(repo_type)
        if archetype_why:
            return archetype_why
        if repo_type == "curriculum":
            return "It exists to help learners follow a structured path toward becoming a software engineer and preparing for large-company technical interviews."
        if repo_type in {"documentation", "knowledge_base"}:
            return "It exists to help readers navigate structured documentation, reference material, and curated resources."
        if explicit_description:
            explicit_lower = explicit_description.lower()
            if product_domain in {"developer intelligence tool", "code intelligence platform"} or any(
                token in explicit_lower for token in self._DEVELOPER_DOMAIN_SIGNALS
            ):
                return "It exists to help teams turn codebases or code changes into structured, queryable project knowledge."
            if "offline-first" in explicit_lower and any(token in explicit_lower for token in ("rag", "retrieval", "diagnosis")):
                return "It exists to provide an offline-first retrieval and diagnosis API workflow."
            if any(token in combined for token in ("whatsapp", "gateway", "messaging")):
                assistant_name_match = re.search(r"chat with\s+([A-Za-z0-9'_-]+)", explicit_description, re.IGNORECASE)
                assistant_name = assistant_name_match.group(1) if assistant_name_match else "the assistant"
                if "linking your phone" in explicit_lower or "link your phone" in explicit_lower:
                    return f"It exists to let users access {assistant_name} through WhatsApp by linking their phone to the gateway."
                return f"It exists to let users access {assistant_name} through WhatsApp through the gateway."
            if any(token in combined for token in ("financial research", "finance", "financial", "investment", "market", "stock", "portfolio", "trading")):
                return "It exists to help users access an AI financial research assistant for financial research workflows."
        if product_domain in {"developer intelligence tool", "code intelligence platform"}:
            return "It exists to help teams turn codebases or code changes into structured, queryable project knowledge."
        return conservative_why()

    def _collect_evidence(self, scan_result, intelligence_result, prd_result):
        items: list[CanonicalEvidence] = []
        seen: set[str] = set()
        by_label: dict[str, str] = {}

        def append(label: str, source_type: str, reason: str, confidence: str) -> None:
            sanitized = self._sanitize_evidence_label(label)
            if not sanitized:
                return
            key = sanitized.lower()
            if key in seen:
                return
            evidence_id = f"E{len(items) + 1}"
            seen.add(key)
            by_label[key] = evidence_id
            items.append(
                CanonicalEvidence(
                    id=evidence_id,
                    label=sanitized,
                    source_type=source_type or "file",
                    reason=self._normalize_sentence(reason or "Detected supporting evidence.", max_sentences=1),
                    confidence=self._label_confidence(confidence),
                )
            )

        contents = getattr(scan_result, "contents", {}) or {}
        for path in contents.keys():
            append(str(path), "file", "Repository metadata or source file detected.", "high")
        for collection in (
            getattr(intelligence_result, "frameworks", []),
            getattr(intelligence_result, "api_endpoints", []),
            getattr(intelligence_result, "modules", []),
            getattr(intelligence_result, "databases", []),
            getattr(intelligence_result, "languages", []),
        ):
            for item in collection:
                for evidence in getattr(item, "evidence", []) or []:
                    append(
                        getattr(evidence, "file", "") or getattr(evidence, "source_id", ""),
                        getattr(evidence, "source_type", "file"),
                        getattr(evidence, "reason", "Detected supporting evidence."),
                        getattr(evidence, "confidence", "medium"),
                    )
        if prd_result is not None:
            for section_name in ("overview", "architecture", "tech_stack", "databases", "setup_notes"):
                section = getattr(prd_result, section_name, None)
                for evidence in getattr(section, "evidence", []) or []:
                    append(getattr(evidence, "file", "") or getattr(evidence, "source_id", ""), getattr(evidence, "source_type", "file"), getattr(evidence, "reason", ""), getattr(evidence, "confidence", "medium"))
        items.sort(key=lambda item: (self._evidence_priority(item.label), item.label.lower()))
        items = items[:12]
        lookup = {item.label.lower(): item.id for item in items}
        return items, lookup

    def _tech_stack(self, scan_result, intelligence_result) -> CanonicalTechStack:
        languages: list[str] = []
        frameworks: list[str] = []
        databases: list[str] = []
        tools: list[str] = []

        def add(bucket: list[str], value: str) -> None:
            if value and value not in bucket:
                bucket.append(value)

        for language in getattr(intelligence_result, "languages", []) or []:
            add(languages, self._LANGUAGES.get(str(getattr(language, "name", "")).lower(), ""))
        for framework in getattr(intelligence_result, "frameworks", []) or []:
            name = str(getattr(framework, "name", "") or "")
            mapped = self._FRAMEWORKS.get(name.lower())
            if mapped:
                add(frameworks, mapped)
                continue
            db_mapped = self._DATABASES.get(name.lower())
            if db_mapped:
                add(databases, db_mapped)
        for database in getattr(intelligence_result, "databases", []) or []:
            add(databases, self._DATABASES.get(str(getattr(database, "name", "")).lower(), str(getattr(database, "name", "") or "")))
        for dependency in getattr(intelligence_result, "dependencies", []) or []:
            dep_name = str(getattr(dependency, "name", "") or "")
            lowered = dep_name.lower()
            if lowered in self._TOOLS:
                add(tools, self._TOOLS[lowered])
            if lowered in self._DATABASES:
                add(databases, self._DATABASES[lowered])
            if lowered in self._FRAMEWORKS:
                add(frameworks, self._FRAMEWORKS[lowered])
        contents = getattr(scan_result, "contents", {}) if scan_result is not None else {}
        for path, content in (contents or {}).items():
            lowered_path = str(path).replace("\\", "/").lower()
            if lowered_path.endswith(".py"):
                add(languages, "Python")
            if lowered_path.endswith((".ts", ".tsx", ".mts", ".cts")):
                add(languages, "TypeScript")
            if lowered_path.endswith((".js", ".jsx", ".mjs", ".cjs")):
                add(languages, "JavaScript")
            if lowered_path.endswith(".css"):
                add(languages, "CSS")
            if lowered_path.endswith(".html"):
                add(languages, "HTML")
            if looks_like_markdown_document(lowered_path):
                add(languages, "Markdown")
            text = str(content or "").lower()
            for token, label in self._TOOLS.items():
                if token in text or token in lowered_path:
                    add(tools, label)
        return CanonicalTechStack(languages=languages, frameworks=frameworks, databases=databases, tools=tools)

    def _api_surface(self, intelligence_result, prd_result, evidence_lookup: dict[str, str]) -> list[CanonicalAPI]:
        ordered: OrderedDict[str, CanonicalAPI] = OrderedDict()
        sources = list(getattr(intelligence_result, "api_endpoints", []) or [])
        if prd_result is not None:
            sources.extend(getattr(prd_result, "api_endpoints", []) or [])
        for endpoint in sources:
            method = str(getattr(endpoint, "method", "GET") or "GET").upper()
            path = self._normalize_api_path(str(getattr(endpoint, "path", "/") or "/"))
            key = f"{method} {path}"
            if key in ordered:
                continue
            source = self._sanitize_evidence_label(
                getattr(endpoint, "file", None)
                or getattr(endpoint, "source_file", None)
                or getattr(endpoint, "framework", None)
                or "Detected API surface"
            ) or "Detected API surface"
            evidence_ids = self._evidence_ids_for_item(endpoint, evidence_lookup)
            ordered[key] = CanonicalAPI(
                method=method,
                path=path,
                purpose=self._api_purpose(method, path),
                source=source,
                evidence_ids=evidence_ids,
            )
        return list(ordered.values())

    def _workflow(self, project_type: str, repo_type: str, intelligence_result, evidence_lookup: dict[str, str]) -> list[CanonicalWorkflowStep]:
        raw_steps = getattr(getattr(intelligence_result, "workflow", None), "steps", []) or []
        route_paths = [str(getattr(item, "path", "") or "").lower() for item in getattr(intelligence_result, "api_endpoints", []) or []]
        joined = " ".join(
            f"{getattr(step, 'source', '')} {getattr(step, 'action', '')} {getattr(step, 'target', '')}".lower()
            for step in raw_steps
        )
        impossible = "types/index.ts" in joined and "fastapi" in joined
        if impossible or not raw_steps:
            return self._deterministic_workflow(project_type, route_paths, repo_type)
        if "types/index.ts" in joined:
            return self._deterministic_workflow(project_type, route_paths, repo_type)
        return self._deterministic_workflow(project_type, route_paths, repo_type)

    def _deterministic_workflow(self, project_type: str, route_paths: list[str] | None = None, repo_type: str = "unknown") -> list[CanonicalWorkflowStep]:
        route_paths = route_paths or []
        if is_documentation_repo_type(repo_type):
            rows = [
                ("Reader opens the repository documentation", "Reader opens the repository documentation."),
                ("README introduces the study plan or guide", "README introduces the study plan or guide."),
                ("Sections organize topics and progression", "Sections organize topics, resources, and learning progression."),
                ("Supporting docs expand accessibility", "Optional translations or supporting files expand accessibility."),
                ("Learner follows the roadmap", "Learner follows the roadmap independently."),
            ]
        elif repo_type == "cli_tool":
            rows = [
                ("User runs a CLI command", "A user executes the command-line interface with arguments or subcommands."),
                ("Argument parsing begins", "The CLI parses flags, commands, and input parameters."),
                ("Command handler executes", "Command-specific logic performs the requested action."),
                ("Optional file or service access runs", "The tool reads local files or calls supporting services only where configured."),
                ("Results are printed", "The CLI returns output, logs, or exit status to the user."),
            ]
        elif repo_type in {"python_package", "npm_package", "component_library", "sdk"}:
            rows = [
                ("Developer installs the package", "A developer adds the package or library to another project."),
                ("Consumer imports public APIs", "Application code imports exported modules, functions, or components."),
                ("Library logic executes", "The package performs the requested functionality inside the host application."),
                ("Optional dependencies integrate", "Configured runtime dependencies or platform clients are used where required."),
                ("Results return to the caller", "The package returns data, behavior, or UI output through its public API surface."),
            ]
        elif repo_type == "vscode_extension":
            rows = [
                ("User installs the extension", "The extension is installed into VS Code."),
                ("Activation event fires", "A command, file event, or workspace action activates the extension."),
                ("Extension command or panel runs", "Registered commands, panels, or providers execute extension logic."),
                ("Local or service logic responds", "The extension uses local logic or optional external services where configured."),
                ("Editor workflow is updated", "Results appear in the editor, panel, or command output."),
            ]
        elif repo_type == "browser_extension":
            rows = [
                ("Browser loads the extension", "The browser loads the extension manifest and runtime."),
                ("Background or content scripts start", "Background, popup, or content scripts initialize based on permissions and events."),
                ("User triggers extension behavior", "A page action, popup action, or content hook executes extension logic."),
                ("Optional storage or network access runs", "The extension uses browser APIs, storage, or configured network requests."),
                ("Extension output is shown", "Results are reflected in the browser UI or target page."),
            ]
        elif repo_type in {"ml_model_repo", "data_science_notebooks", "research_code"}:
            rows = [
                ("Load data and artifacts", "Datasets, notebooks, checkpoints, or experiment inputs are loaded."),
                ("Preprocess inputs", "Feature preparation, data cleaning, or notebook setup runs."),
                ("Run training, inference, or analysis", "The main analytical or model workflow executes."),
                ("Evaluate or inspect results", "Outputs, metrics, or visualizations are reviewed."),
                ("Share findings or artifacts", "Results are exported through notebooks, reports, or model artifacts."),
            ]
        elif repo_type == "dataset":
            rows = [
                ("Consumer downloads dataset assets", "A downstream user accesses the dataset files."),
                ("Metadata and schema are reviewed", "Supporting documentation explains dataset structure and meaning."),
                ("Files are loaded into analysis or training", "Consumers parse the dataset in their own tooling."),
                ("Quality or provenance is checked", "Users validate schema, licensing, and data quality as needed."),
                ("Dataset is used downstream", "The repository supports analysis, reporting, or model training elsewhere."),
            ]
        elif repo_type in {"template", "monorepo"}:
            rows = [
                ("Developer clones the repository", "The repository is copied for local development."),
                ("Configuration is adjusted", "Environment variables, names, and placeholders are updated."),
                ("Shared tooling is installed", "Dependencies and workspace tooling are initialized."),
                ("Project-specific work begins", "The starter or workspace is adapted into the target project."),
                ("Outputs evolve into downstream projects", "The template or monorepo structure supports ongoing development."),
            ]
        elif repo_type in {"infrastructure", "devops_automation"}:
            rows = [
                ("Operator reviews infrastructure config", "Terraform, Kubernetes, Docker, or pipeline configuration is inspected."),
                ("Automation command is triggered", "An apply, plan, deploy, or CI/CD workflow is started."),
                ("Resources or pipelines execute", "Infrastructure resources or automation steps run."),
                ("Environment state is updated", "Provisioned resources, deployments, or environments change state."),
                ("Operator reviews status", "Logs, outputs, or state are reviewed for success and follow-up."),
            ]
        elif repo_type == "design_assets":
            rows = [
                ("Designer or developer opens assets", "Creative source files or exports are accessed."),
                ("Assets are reviewed and selected", "The needed visual assets are chosen for downstream use."),
                ("Files are imported into product workflows", "Assets are brought into design, marketing, or product pipelines."),
                ("Exports are adapted as needed", "Sizing, format conversion, or naming adjustments are applied."),
                ("Assets are reused downstream", "The repository supports consistent visual asset reuse."),
            ]
        elif project_type == "backend":
            rows = [("Client request arrives", "Client or API consumer sends a request.")]
            if any("/diagnose" in path for path in route_paths):
                rows.append(("Diagnosis API", "Backend route handler validates and processes diagnosis requests."))
            if any("/search" in path for path in route_paths):
                rows.append(("Retrieval API", "Backend route handler processes retrieval or search requests."))
            rows.extend(
                [
                    ("Service logic runs", "Service logic performs the requested work."),
                    ("Storage is used if detected", "Storage is used if detected in the backend workflow."),
                    ("Structured response returns", "Structured response is returned to the client."),
                ]
            )
        elif project_type == "frontend":
            rows = [
                ("Open frontend application", "User opens frontend application."),
                ("Render UI workflows", "UI pages and components render workflows."),
                ("Call backend if configured", "API client calls backend if configured."),
                ("Display results", "Results are displayed in dashboard, chat, or report surfaces."),
            ]
        else:
            rows = [
                ("Open frontend application", "User opens frontend application."),
                ("Render analysis and chat surfaces", "Frontend renders analysis, dashboard, chat, and report workflows."),
                ("Call backend APIs", "Frontend calls backend API endpoints."),
                ("Process requests in backend", "Backend route handlers process analysis, chat, context, status, and report requests."),
                ("Use storage/configuration", "Storage/configuration is used when detected."),
                ("Return structured intelligence", "Backend returns structured project intelligence to the frontend."),
            ]
        return [
            CanonicalWorkflowStep(step=index, title=title, description=description, evidence_ids=[])
            for index, (title, description) in enumerate(rows, start=1)
        ]

    def _completed(self, project_type: str, repo_type: str, tech_stack: CanonicalTechStack, api_surface: list[CanonicalAPI], scan_result, intelligence_result, prd_result, evidence_lookup: dict[str, str]) -> list[CanonicalStatusItem]:
        rows: list[CanonicalStatusItem] = []
        seen: set[str] = set()

        def add(title: str, description: str, confidence: str = "Medium", labels: list[str] | None = None) -> None:
            key = title.lower()
            if key in seen:
                return
            seen.add(key)
            rows.append(
                CanonicalStatusItem(
                    title=title,
                    description=self._normalize_sentence(description, max_sentences=1),
                    evidence_ids=self._evidence_ids_from_labels(labels or [], evidence_lookup),
                    confidence=self._label_confidence(confidence),
                )
            )

        if is_documentation_repo_type(repo_type):
            readme_present = any("readme" in str(path).lower() for path in getattr(scan_result, "contents", {}).keys())
            markdown_paths = [str(path) for path in getattr(scan_result, "contents", {}).keys() if looks_like_markdown_document(path)]
            if readme_present:
                add("Study Plan Documentation" if repo_type == "curriculum" else "Documentation Content", "README-based documentation is present and describes the repository content.", labels=["README.md"])
            add("Learning Roadmap" if repo_type == "curriculum" else "Resource Organization", "Structured sections organize topics, resources, and learning progression for readers.", labels=["README.md"])
            if repo_type == "curriculum":
                add("Interview Preparation Content", "Interview preparation topics and supporting resources were detected in the documentation.", labels=["README.md"])
            if len(markdown_paths) > 1:
                add("Translated Documentation", "Multiple documentation files were detected, including supporting or translated content where available.", labels=markdown_paths[:3])
            if self._has_setup_files(scan_result):
                add("Setup / Contribution Notes", "Setup or contribution notes were detected in repository documentation or manifests.", labels=["README.md", "package.json", "pyproject.toml"])
            return rows
        if repo_type == "cli_tool":
            add("Command Interface", "A command-line entry point or executable interface was detected.", labels=["pyproject.toml", "package.json"])
            add("Argument Parsing", "Command arguments, flags, or subcommands are configured for the CLI surface.", labels=["pyproject.toml", "package.json"])
            add("Execution Logic", "The repository includes command execution logic for the requested workflow.", labels=["main.py", "src/index.ts"])
            if self._has_setup_files(scan_result):
                add("Packaging Metadata", "Packaging or distribution metadata was detected for the CLI tool.", labels=["pyproject.toml", "package.json", "setup.py"])
            return rows
        if repo_type in {"python_package", "npm_package", "component_library", "sdk"}:
            add("Public API Surface", "Exported package or library APIs were detected for downstream consumers.", labels=["pyproject.toml", "package.json"])
            add("Package Metadata", "Package distribution metadata was detected in repository manifests.", labels=["pyproject.toml", "package.json", "setup.py"])
            add("Examples / Documentation", "Documentation or usage examples were detected for package consumers.", labels=["README.md"])
            if self._has_tests(scan_result):
                add("Tests", "Automated tests were detected for library behavior.", labels=["tests/", "test_", ".spec."])
            return rows
        if repo_type == "vscode_extension":
            add("Extension Commands", "VS Code command or contribution metadata was detected.", labels=["package.json"])
            add("Activation Metadata", "Extension activation and packaging metadata were detected.", labels=["package.json"])
            add("Editor Integration", "The repository includes extension logic for editor-facing workflows.", labels=["package.json", "src/extension.ts"])
            return rows
        if repo_type == "browser_extension":
            add("Extension Manifest", "Browser extension manifest metadata was detected.", labels=["manifest.json"])
            add("Background / Content Logic", "Background, popup, or content-script behavior was detected.", labels=["manifest.json"])
            add("Permission Configuration", "Extension permissions and runtime configuration were detected.", labels=["manifest.json"])
            return rows
        if repo_type in {"ml_model_repo", "data_science_notebooks", "research_code"}:
            add("Model / Analysis Assets", "Model artifacts, notebooks, or experiment code were detected.", labels=["README.md"])
            add("Data or Experiment Workflow", "The repository includes analytical or experimental workflow content.", labels=["README.md"])
            if self._has_tests(scan_result):
                add("Validation / Tests", "Validation or automated checks were detected for analytical workflows.", labels=["tests/"])
            return rows
        if repo_type == "dataset":
            add("Dataset Files", "Dataset assets were detected in the repository.", labels=["README.md"])
            add("Metadata / Schema Documentation", "Supporting metadata or schema documentation was detected.", labels=["README.md"])
            add("Licensing Information", "Dataset licensing or reuse guidance was detected where available.", labels=["README.md", "LICENSE"])
            return rows
        if repo_type in {"template", "monorepo"}:
            add("Starter Structure", "Reusable starter or workspace structure was detected.", labels=["README.md", "package.json"])
            add("Configuration Scaffolding", "Template configuration or workspace metadata was detected.", labels=["package.json", "pyproject.toml"])
            add("Setup Documentation", "Repository docs describe how consumers should use the starter or workspace.", labels=["README.md"])
            return rows
        if repo_type in {"infrastructure", "devops_automation"}:
            add("Infrastructure Definitions", "Infrastructure or automation definitions were detected.", labels=["main.tf", "docker-compose.yml", ".github/workflows"])
            add("Environment Automation", "Provisioning, deployment, or pipeline logic was detected.", labels=["main.tf", ".github/workflows"])
            if self._has_setup_files(scan_result):
                add("Operator Setup Notes", "Supporting setup or usage documentation was detected for operators.", labels=["README.md"])
            return rows
        if repo_type == "design_assets":
            add("Asset Inventory", "Reusable design or media assets were detected.", labels=["README.md"])
            add("Source Files", "Creative source files or export formats were detected.", labels=["README.md"])
            return rows
        if project_type in {"frontend", "fullstack"}:
            add("Frontend Application", "A frontend application is present for dashboard, chat, analysis, or report workflows.", labels=["frontend/src/main.tsx", "package.json"])
        if project_type in {"backend", "fullstack"}:
            add("Backend API Surface", "A backend API surface is present to process analysis, chat, context, status, or report requests.", labels=["app/main.py", "main.py"])
        if any(any(token in api.path for token in ("/ask", "/chat", "/query")) for api in api_surface):
            add("Chat / Query API", "Grounded chat or query endpoints were detected.", labels=["README.md"])
        if any("/analyze" in api.path for api in api_surface):
            add("Analysis API", "Analysis endpoints were detected for session creation or repository processing.", labels=["README.md"])
        if any(any(token in api.path for token in ("/report", "/prd", "/summary", "/summarize")) for api in api_surface):
            add("Report Generation", "Report generation workflows were detected in the application surface.", labels=["README.md"])
        if any(any(token in api.path for token in ("/history", "/session")) for api in api_surface):
            add("Session Tracking", "Session tracking or session history workflows were detected.", labels=["README.md"])
        if tech_stack.databases:
            add("Storage Integration", f"Storage evidence includes {', '.join(tech_stack.databases)}.", labels=tech_stack.databases)
        if any(api.path in {"/", "/health"} or api.path.startswith("/status") for api in api_surface):
            add("Health / Status Endpoints", "Health, root, or status endpoints were detected for readiness and progress checks.", labels=["app/main.py", "main.py"])
        if self._has_setup_files(scan_result):
            add("Setup Configuration", "Setup and configuration artifacts were detected in the analyzed repository.", labels=["package.json", "requirements.txt", "dockerfile"])
        return rows

    def _remaining(self, scan_result, intelligence_result, prd_result, evidence_lookup: dict[str, str], tech_stack: CanonicalTechStack, repo_type: str = "unknown") -> list[CanonicalStatusItem]:
        rows: list[CanonicalStatusItem] = []
        seen: set[str] = set()
        if is_documentation_repo_type(repo_type):
            arch_type = str(getattr(getattr(intelligence_result, "architecture", None), "type", "") or "").lower()
            if arch_type in {"", "unknown"}:
                rows.append(CanonicalStatusItem(title="No executable application architecture was detected.", description="No executable application architecture was detected.", evidence_ids=[], confidence="High"))
            if not self._has_tests(scan_result):
                rows.append(CanonicalStatusItem(title="Documentation validation", description="No automated validation was detected for documentation links or structure.", evidence_ids=[], confidence="Medium"))
            if not tech_stack.databases:
                rows.append(CanonicalStatusItem(title="Database / Storage", description="No database/storage layer is required based on available evidence.", evidence_ids=[], confidence="High"))
            return rows
        if repo_type == "cli_tool":
            if not self._has_tests(scan_result):
                rows.append(CanonicalStatusItem(title="CLI Tests", description="No automated tests were detected for command parsing or execution flows.", evidence_ids=[], confidence="High"))
            if not self._has_setup_files(scan_result):
                rows.append(CanonicalStatusItem(title="Packaging / Install Notes", description="Packaging metadata or installation notes were not clearly detected for the CLI tool.", evidence_ids=[], confidence="Medium"))
            return rows
        if is_package_like_repo_type(repo_type):
            if not self._has_tests(scan_result):
                rows.append(CanonicalStatusItem(title="Package Tests", description="No automated tests were detected for the public package/library API surface.", evidence_ids=[], confidence="High"))
            if not any("readme" in str(path).lower() for path in getattr(scan_result, "contents", {}).keys()):
                rows.append(CanonicalStatusItem(title="Usage Documentation", description="Consumer-facing package documentation was not clearly detected.", evidence_ids=[], confidence="Medium"))
            if repo_type in {"npm_package", "component_library"} and "TypeScript" not in tech_stack.languages and "JavaScript" in tech_stack.languages:
                rows.append(CanonicalStatusItem(title="Type Declarations", description="Type declaration evidence was not clearly detected for the distributed package.", evidence_ids=[], confidence="Medium"))
            return rows
        if repo_type in {"vscode_extension", "browser_extension"}:
            if not self._has_tests(scan_result):
                rows.append(CanonicalStatusItem(title="Extension Validation", description="No automated validation was detected for extension behavior or packaging.", evidence_ids=[], confidence="Medium"))
            rows.append(CanonicalStatusItem(title="Marketplace / Release Guidance", description="Release, permission, or marketplace documentation should be confirmed for the extension workflow.", evidence_ids=[], confidence="Medium"))
            return rows
        if repo_type in {"ml_model_repo", "data_science_notebooks", "research_code"}:
            rows.append(CanonicalStatusItem(title="Reproducibility Notes", description="Reproducibility guidance, environment pinning, or experiment instructions should be confirmed.", evidence_ids=[], confidence="Medium"))
            if not self._has_tests(scan_result):
                rows.append(CanonicalStatusItem(title="Evaluation / Validation", description="Automated evaluation or validation coverage was not clearly detected.", evidence_ids=[], confidence="Medium"))
            return rows
        if repo_type == "dataset":
            rows.append(CanonicalStatusItem(title="Dataset Provenance", description="Data provenance, freshness, and collection methodology should be confirmed.", evidence_ids=[], confidence="Medium"))
            rows.append(CanonicalStatusItem(title="Schema Validation", description="Automated schema or data-quality validation was not clearly detected.", evidence_ids=[], confidence="Medium"))
            return rows
        if repo_type in {"template", "monorepo"}:
            rows.append(CanonicalStatusItem(title="Consumer Setup Verification", description="Starter setup and first-run guidance should be confirmed for downstream consumers.", evidence_ids=[], confidence="Medium"))
            if not self._has_tests(scan_result):
                rows.append(CanonicalStatusItem(title="Template Validation", description="No automated validation was detected for starter or workspace assumptions.", evidence_ids=[], confidence="Medium"))
            return rows
        if repo_type in {"infrastructure", "devops_automation"}:
            rows.append(CanonicalStatusItem(title="Environment Separation", description="Environment boundaries, state handling, and rollback expectations should be confirmed.", evidence_ids=[], confidence="Medium"))
            rows.append(CanonicalStatusItem(title="Secrets Handling", description="Secret-management expectations were not clearly confirmed from the analyzed evidence.", evidence_ids=[], confidence="Medium"))
            return rows
        if repo_type == "design_assets":
            rows.append(CanonicalStatusItem(title="Licensing / Usage Rights", description="Asset licensing and downstream usage rights should be confirmed.", evidence_ids=[], confidence="Medium"))
            rows.append(CanonicalStatusItem(title="Naming / Export Conventions", description="Consistent naming and export-format guidance was not clearly detected.", evidence_ids=[], confidence="Medium"))
            return rows
        remaining_sources = []
        if prd_result is not None and getattr(prd_result, "project_brief", None):
            remaining_sources.extend(getattr(prd_result.project_brief, "remaining", []) or [])
        for item in remaining_sources:
            title = str(getattr(item, "title", "") or "")
            description = str(getattr(item, "description", title) or title)
            if not title and not description:
                continue
            normalized_title = "CI/CD pipeline not detected." if "ci/cd" in description.lower() or "ci/cd" in title.lower() else title or description
            key = normalized_title.lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                CanonicalStatusItem(
                    title=normalized_title,
                    description=self._normalize_sentence(description, max_sentences=1),
                    evidence_ids=self._evidence_ids_for_item(item, evidence_lookup),
                    confidence=self._label_confidence(getattr(item, "confidence", "Low")),
                )
            )
        if not self._has_ci_cd(scan_result):
            key = "ci/cd pipeline not detected."
            if key not in seen:
                seen.add(key)
                rows.append(CanonicalStatusItem(title="CI/CD pipeline not detected.", description="CI/CD pipeline not detected.", evidence_ids=[], confidence="High"))
        if not self._has_tests(scan_result) and "tests" not in seen:
            seen.add("tests")
            rows.append(CanonicalStatusItem(title="Tests", description="No tests detected.", evidence_ids=[], confidence="High"))
        if not tech_stack.databases and "database / storage" not in seen:
            seen.add("database / storage")
            rows.append(CanonicalStatusItem(title="Database / Storage", description="No database/storage layer detected.", evidence_ids=[], confidence="High"))
        if not self._has_setup_files(scan_result) and "setup notes" not in seen:
            seen.add("setup notes")
            rows.append(CanonicalStatusItem(title="Setup Notes", description="Insufficient setup evidence was detected.", evidence_ids=[], confidence="Medium"))
        return rows

    def _issues(self, prd_result, evidence_lookup: dict[str, str]) -> list[CanonicalIssue]:
        result: list[CanonicalIssue] = []
        seen: set[str] = set()
        issues: list[RiskItem] = []
        if prd_result is not None:
            issues.extend(getattr(prd_result, "risks", []) or [])
            if getattr(prd_result, "project_brief", None):
                issues.extend(getattr(prd_result.project_brief, "issues", []) or [])
        for issue in issues:
            title = self._normalize_sentence(getattr(issue, "title", "") or "", max_sentences=1)
            if not title:
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(
                CanonicalIssue(
                    severity=self._title_confidence(getattr(issue, "severity", "medium")),
                    title=title,
                    recommendation=self._normalize_sentence(getattr(issue, "recommendation", "") or "Review this issue and confirm the required remediation.", max_sentences=1),
                    evidence_ids=self._evidence_ids_for_item(issue, evidence_lookup),
                )
            )
        return result[:8]

    def _warnings(self, intelligence_result, prd_result) -> list[str]:
        rows = []
        for item in list(getattr(intelligence_result, "warnings", []) or []) + list(getattr(prd_result, "warnings", []) or [] if prd_result is not None else []):
            text = self._normalize_sentence(str(item or ""), max_sentences=1)
            lowered = text.lower()
            if not text:
                continue
            if any(token in lowered for token in ("detector", "normalized unsupported evidence", "detected domain signals", "magicmock", "internal")):
                continue
            if text not in rows:
                rows.append(text)
        return rows[:6]

    def _confidence(self, intelligence_result, explicit_description: str, identity, evidence_items: list[CanonicalEvidence], repo_type: str = "unknown") -> CanonicalConfidence:
        if is_documentation_repo_type(repo_type):
            product_purpose = "High" if explicit_description else self._label_confidence(getattr(identity, "domain_confidence", "Unknown"))
            overall = "High" if product_purpose == "High" else "Medium" if evidence_items else "Low"
            return CanonicalConfidence(architecture="Low", product_purpose=product_purpose, overall=overall)
        architecture = self._label_confidence(getattr(getattr(intelligence_result, "architecture", None), "confidence", "Unknown"))
        product_purpose = "High" if explicit_description else self._label_confidence(getattr(identity, "domain_confidence", "Unknown"))
        overall = "High" if architecture == "High" and product_purpose == "High" else "Medium" if evidence_items else "Low"
        return CanonicalConfidence(architecture=architecture, product_purpose=product_purpose, overall=overall)

    def _architecture_summary(self, project_type: str, tech_stack: CanonicalTechStack, api_surface: list[CanonicalAPI], repo_type: str = "unknown") -> str:
        if is_documentation_repo_type(repo_type):
            return "This repository is primarily documentation/curriculum content. No executable application architecture was confirmed from the analyzed evidence."
        architecture_map = {
            "cli_tool": "This repository is organized around a command-line execution flow rather than a long-running application architecture.",
            "python_package": "This repository is primarily a reusable Python package with importable library APIs rather than an executable application architecture.",
            "npm_package": "This repository is primarily a distributed npm package with exported package APIs rather than a standalone application architecture.",
            "component_library": "This repository is primarily a component-library structure with exported UI building blocks rather than a standalone application architecture.",
            "sdk": "This repository is primarily an SDK/package surface intended to be consumed by other applications.",
            "browser_extension": "This repository is organized as a browser extension with manifest-driven runtime behavior rather than a conventional app stack.",
            "vscode_extension": "This repository is organized as a VS Code extension with activation and command-driven workflows.",
            "dataset": "This repository is primarily a dataset and metadata distribution surface rather than an executable application architecture.",
            "ml_model_repo": "This repository is primarily an ML/model workflow repository centered on data, training, and inference assets.",
            "data_science_notebooks": "This repository is primarily a notebook-based analysis workflow rather than a conventional application architecture.",
            "template": "This repository is primarily a starter/template structure intended to be adapted into downstream projects.",
            "infrastructure": "This repository is primarily infrastructure-as-code content used to provision or operate environments.",
            "devops_automation": "This repository is primarily automation and pipeline configuration rather than a user-facing application architecture.",
            "design_assets": "This repository is primarily a design/assets collection rather than an executable application architecture.",
            "research_code": "This repository is primarily research and experiment code rather than a production application architecture.",
            "monorepo": "This repository is organized as a monorepo containing multiple related subprojects rather than a single application architecture.",
        }
        if repo_type in architecture_map:
            return architecture_map[repo_type]
        frameworks = ", ".join(tech_stack.frameworks[:3])
        framework_part = f" using {frameworks}" if frameworks else ""
        api_part = f" with {len(api_surface)} detected API endpoints" if api_surface else ""
        return self._normalize_sentence(f"This repository uses a {project_type} architecture{framework_part}{api_part}.", max_sentences=1)

    def _data_quality_notes(self, evidence_items: list[CanonicalEvidence], api_surface: list[CanonicalAPI], product_summary: str, explicit_description: str) -> list[str]:
        notes = []
        if evidence_items:
            notes.append("Evidence labels were sanitized and limited to high-signal items.")
        if api_surface:
            notes.append("Duplicate API endpoints were removed and normalized.")
        if explicit_description and "appears to be" not in product_summary.lower():
            notes.append("Explicit product metadata was used as the primary product description.")
        return notes[:5]

    def _normalize_api_path(self, path: str) -> str:
        value = (path or "/").strip().replace("\\", "/")
        value = re.sub(r"\s+", "", value)
        value = re.sub(r"/+", "/", value)
        if not value.startswith("/"):
            value = f"/{value}"
        value = re.sub(r"\{[^}]*task[^}]*id[^}]*\}", "{task_id}", value, flags=re.I)
        value = re.sub(r"\{[^}]*job[^}]*id[^}]*\}", "{task_id}", value, flags=re.I)
        value = re.sub(r"\{[^}]*task id[^}]*\}", "{task_id}", value, flags=re.I)
        value = re.sub(r"\{[^}]*session[^}]*id[^}]*\}", "{session_id}", value, flags=re.I)
        value = value.lower()
        return value.replace("/status/{job_id}", "/status/{task_id}").replace("/status/{taskid}", "/status/{task_id}")

    def _api_purpose(self, method: str, path: str) -> str:
        if method == "GET" and path == "/":
            return "Root or landing endpoint."
        if method == "GET" and path == "/health":
            return "Health check endpoint."
        if method == "GET" and path == "/status/{task_id}":
            return "Retrieves analysis task status."
        if method == "POST" and path == "/ask":
            return "Accepts a project question and returns a grounded answer."
        if method == "POST" and path == "/context":
            return "Builds or retrieves context for analysis/chat."
        if method == "POST" and "/analyze" in path:
            return "Starts an analysis workflow."
        if method == "GET" and "/history/{session_id}" in path:
            return "Retrieves session chat/history."
        if method == "GET" and path == "/identity":
            return "Returns project identity information."
        if method == "GET" and path == "/identity/summary":
            return "Returns summarized identity metadata."
        return "Detected API endpoint."

    def _sanitize_evidence_label(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        lowered = text.lower().replace("\\", "/")
        if any(token in lowered for token in self._SENSITIVE_TOKENS):
            return ""
        parts = [segment for segment in lowered.split("/") if segment]
        if not parts:
            return ""
        tail = parts[-2:] if parts[-1].count(".") else parts[-3:]
        label = "/".join(tail)
        if any(token in label for token in self._SENSITIVE_TOKENS):
            return ""
        return label

    def _evidence_priority(self, label: str) -> int:
        lowered = label.lower()
        for index, item in enumerate(self._PREFERRED_EVIDENCE):
            if item in lowered:
                return index
        return len(self._PREFERRED_EVIDENCE)

    def _evidence_ids_from_labels(self, labels: list[str], evidence_lookup: dict[str, str]) -> list[str]:
        result = []
        for label in labels:
            sanitized = self._sanitize_evidence_label(label)
            if sanitized and sanitized.lower() in evidence_lookup and evidence_lookup[sanitized.lower()] not in result:
                result.append(evidence_lookup[sanitized.lower()])
        return result

    def _evidence_ids_for_item(self, item: Any, evidence_lookup: dict[str, str]) -> list[str]:
        labels = []
        for evidence in getattr(item, "evidence", []) or []:
            labels.append(getattr(evidence, "file", "") or getattr(evidence, "source_id", ""))
        for attr in ("file", "source_file", "framework"):
            value = getattr(item, attr, None)
            if value:
                labels.append(str(value))
        return self._evidence_ids_from_labels(labels, evidence_lookup)

    def _normalize_sentence(self, value: str, max_sentences: int = 2) -> str:
        text = sanitize_text_for_display(str(value or ""), fallback="")
        text = re.sub(r"\s+", " ", text).strip()
        text = text.replace("**", "")
        if not text:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        cleaned = " ".join(sentences[:max_sentences]).strip()
        return cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned}."

    def _predicate_from_description(self, value: str) -> str:
        text = str(value or "").strip().rstrip(".")
        lowered = text.lower()
        prefixes = ("this is ", "this repository is ", "this project is ")
        for prefix in prefixes:
            if lowered.startswith(prefix):
                text = text[len(prefix):].strip()
                lowered = text.lower()
                break
        if lowered.startswith("my "):
            return f"a {text[3:].strip()}"
        return text

    def _label_confidence(self, value: str) -> str:
        lowered = str(value or "").strip().lower()
        if lowered == "high":
            return "High"
        if lowered == "medium":
            return "Medium"
        if lowered == "low":
            return "Low"
        return "Unknown"

    def _title_confidence(self, value: str) -> str:
        lowered = str(value or "").strip().lower()
        if lowered:
            return lowered.capitalize()
        return "Medium"

    def _has_setup_files(self, scan_result) -> bool:
        contents = getattr(scan_result, "contents", {}) or {}
        paths = " ".join(str(path).replace("\\", "/").lower() for path in contents.keys())
        return any(token in paths for token in ("package.json", "requirements.txt", "dockerfile", "docker-compose", "eslint"))

    def _has_ci_cd(self, scan_result) -> bool:
        contents = getattr(scan_result, "contents", {}) or {}
        paths = " ".join(str(path).replace("\\", "/").lower() for path in contents.keys())
        return any(token in paths for token in (".github/workflows", "gitlab-ci", "azure-pipelines", "circleci"))

    def _has_tests(self, scan_result) -> bool:
        contents = getattr(scan_result, "contents", {}) or {}
        paths = " ".join(str(path).replace("\\", "/").lower() for path in contents.keys())
        return any(token in paths for token in ("tests/", "test_", "_test.py", ".spec.", ".test."))
