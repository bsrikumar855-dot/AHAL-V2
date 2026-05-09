from __future__ import annotations

from copy import deepcopy

from app.chat.models import ChatAnswer
from app.docs.models import PRDResult
from app.docs.fact_snapshot import build_fact_snapshot
from app.docs.utils.evidence_sanitizer import sanitize_doc_evidence_list, sanitize_payload, sanitize_text
from app.intelligence.product_identity import ProductIdentity


class OutputConsistencyValidator:
    def validate_prd_section(self, section, product_identity: ProductIdentity | None = None):
        result = deepcopy(section)
        result.content = self._safe_section_content(result.content, product_identity)
        result.warnings = [sanitize_text(item, fallback="") for item in result.warnings if sanitize_text(item, fallback="")]
        result.evidence = sanitize_doc_evidence_list(result.evidence)
        return result

    def validate_prd(self, prd_result: PRDResult, product_identity: ProductIdentity | None = None) -> PRDResult:
        prd = deepcopy(prd_result)
        prd.title = sanitize_text(prd.title, fallback="Project Requirements Document")
        prd.project_type = sanitize_text(prd.project_type, fallback="unknown")
        prd.architecture_label = sanitize_text(getattr(prd, "architecture_label", None), fallback="") or None
        prd.repo_intelligence_score = int(getattr(prd, "repo_intelligence_score", 0) or 0)
        prd.architecture_confidence = getattr(prd, "architecture_confidence", getattr(getattr(prd, "architecture", None), "confidence", "low")) or "low"
        prd.product_purpose_confidence = getattr(prd, "product_purpose_confidence", getattr(product_identity, "domain_confidence", "low")) or "low"
        prd.warnings = [sanitize_text(item, fallback="") for item in prd.warnings if sanitize_text(item, fallback="")]
        snapshot = build_fact_snapshot(prd_result=prd, product_identity=product_identity)

        for section_name in ("overview", "architecture", "tech_stack", "databases", "setup_notes"):
            section = getattr(prd, section_name, None)
            if section is None:
                continue
            setattr(prd, section_name, self.validate_prd_section(section, product_identity))

        if getattr(prd, "project_brief", None):
            pb = prd.project_brief
            for key in ("goal", "what", "why"):
                section = getattr(pb, key, None)
                if section is None:
                    continue
                section.content = self._safe_section_content(section.content, product_identity)
                section.evidence = sanitize_doc_evidence_list(section.evidence)
            pb.completed = [item for item in pb.completed if item.description and sanitize_text(item.description, fallback="")]
            pb.remaining = [item for item in pb.remaining if item.description and sanitize_text(item.description, fallback="")]
            pb.issues = [item for item in pb.issues if item.description and sanitize_text(item.description, fallback="")]
            self._resolve_prd_contradictions(prd, snapshot)

        prd.overview.content = self._guard_repo_identity_claims(prd.overview.content, product_identity, prd)
        if getattr(prd, "project_brief", None):
            prd.project_brief.goal.content = self._guard_repo_identity_claims(prd.project_brief.goal.content, product_identity, prd)
            prd.project_brief.what.content = self._guard_repo_identity_claims(prd.project_brief.what.content, product_identity, prd)
            prd.project_brief.why.content = self._guard_repo_identity_claims(prd.project_brief.why.content, product_identity, prd)

        return prd

    def validate_export_prd(self, prd_result: PRDResult) -> PRDResult:
        return self.validate_prd(prd_result, None)

    def validate_chat_answer(self, answer: ChatAnswer, product_identity: ProductIdentity | None = None) -> ChatAnswer:
        result = deepcopy(answer)
        result.answer = self._safe_section_content(result.answer, product_identity)
        result.warnings = [sanitize_text(item, fallback="") for item in result.warnings if sanitize_text(item, fallback="")]
        result.answer = self._guard_repo_identity_claims(result.answer, product_identity)
        return result

    def validate_payload(self, payload):
        return sanitize_payload(payload)

    def _resolve_prd_contradictions(self, prd: PRDResult, snapshot) -> None:
        pb = prd.project_brief
        if pb is None:
            return
        if not snapshot.has_setup or "insufficient" in getattr(prd.setup_notes, "content", "").lower():
            pb.completed = [item for item in pb.completed if "setup" not in item.title.lower()]
        if snapshot.module_count == 0:
            pb.completed = [item for item in pb.completed if "module" not in item.title.lower()]
        if snapshot.has_database:
            pb.remaining = [item for item in pb.remaining if "database" not in item.title.lower()]
        else:
            pb.completed = [item for item in pb.completed if "database" not in item.title.lower()]
        if snapshot.has_deployment:
            pb.remaining = [item for item in pb.remaining if "deployment" not in item.title.lower()]
        if snapshot.has_tests:
            pb.remaining = [item for item in pb.remaining if "test" not in item.title.lower()]
        else:
            pb.completed = [item for item in pb.completed if "test" not in item.title.lower()]
        if snapshot.has_auth:
            pb.remaining = [item for item in pb.remaining if "auth" not in item.title.lower()]
        risk_titles = {item.title.lower(): item for item in getattr(prd, "risks", [])}
        if snapshot.has_tests:
            prd.risks = [item for item in prd.risks if "no tests detected" not in item.title.lower()]
        if snapshot.has_database:
            prd.risks = [item for item in prd.risks if "no database detected" not in item.title.lower()]
        if snapshot.has_deployment:
            prd.risks = [item for item in prd.risks if "no deployment config detected" not in item.title.lower()]
        if snapshot.has_setup:
            prd.warnings = [item for item in prd.warnings if "no setup files" not in item.lower()]
            prd.setup_notes.warnings = [item for item in prd.setup_notes.warnings if "no setup files" not in item.lower()]

    def _safe_section_content(self, content: str, product_identity: ProductIdentity | None) -> str:
        fallback = (
            sanitize_text(product_identity.purpose_summary)
            if product_identity is not None and product_identity.purpose_summary
            else "Insufficient evidence from codebase."
        )
        text = sanitize_text(content, fallback=fallback)
        return self._guard_repo_identity_claims(text, product_identity)

    def _guard_repo_identity_claims(self, text: str, product_identity: ProductIdentity | None, prd: PRDResult | None = None) -> str:
        lowered = text.lower()
        forbidden = (
            "repository intelligence",
            "codebase intelligence",
            "repository-aware",
            "prd generation",
            "architecture diff",
            "test gap",
            "mcp tools",
        )
        repo_score = getattr(product_identity, "repo_intelligence_score", None)
        if repo_score is None and prd is not None:
            repo_score = getattr(prd, "repo_intelligence_score", 0)
        repo_score = int(repo_score or 0)
        if any(token in lowered for token in forbidden) and repo_score < 2:
            return self._fallback_architecture_summary(prd, product_identity)
        return text

    def _fallback_architecture_summary(self, prd: PRDResult | None, product_identity: ProductIdentity | None) -> str:
        if product_identity is not None and product_identity.purpose_summary:
            return sanitize_text(product_identity.purpose_summary)
        architecture = (
            sanitize_text(getattr(prd, "architecture_label", None), fallback="")
            if prd is not None else ""
        ).lower()
        if not architecture:
            architecture = sanitize_text(getattr(prd, "project_type", None), fallback="backend").lower() if prd is not None else "backend"
        if architecture not in {"frontend", "backend", "fullstack"}:
            architecture = "backend"

        stack_tokens: list[str] = []
        source_text = " ".join(
            sanitize_text(
                getattr(section, "content", ""),
                fallback="",
            )
            for section in (
                getattr(prd, "tech_stack", None),
                getattr(prd, "databases", None),
                getattr(prd, "architecture", None),
                getattr(prd, "overview", None),
            )
            if section is not None
        ).lower() if prd is not None else ""
        for token in ("react", "vite", "next.js", "fastapi", "flask", "express", "mongodb", "postgresql", "sqlite", "mysql"):
            if token in source_text:
                label = {
                    "react": "React",
                    "vite": "Vite",
                    "next.js": "Next.js",
                    "fastapi": "FastAPI",
                    "flask": "Flask",
                    "express": "Express",
                    "mongodb": "MongoDB",
                    "postgresql": "PostgreSQL",
                    "sqlite": "SQLite",
                    "mysql": "MySQL",
                }[token]
                if label not in stack_tokens:
                    stack_tokens.append(label)

        route = ""
        if prd is not None:
            for endpoint in getattr(prd, "api_endpoints", []) or []:
                route = sanitize_text(getattr(endpoint, "path", ""), fallback="")
                if route:
                    break
        stack_text = f" built with {' and '.join(stack_tokens[:2])}" if stack_tokens else ""
        route_text = f" It exposes {route} endpoint." if route else ""
        if architecture == "frontend":
            return f"This project is organized as a frontend application{stack_text}. It coordinates the user-facing experience, interaction flow, and related application behavior into a coherent product surface."
        if architecture == "fullstack":
            return f"This project is organized as a fullstack application{stack_text}.{route_text} It connects the interface, application logic, and data flow into a coherent product workflow."
        return f"This project is organized as a backend API service{stack_text}.{route_text} It centralizes API handling, service logic, and data operations behind a maintainable service boundary."
