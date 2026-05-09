from __future__ import annotations

import re

from app.intelligence.presentation_models import (
    CanonicalAPI,
    CanonicalEvidence,
    CanonicalIssue,
    CanonicalProjectIntelligence,
    CanonicalStatusItem,
    CanonicalWorkflowStep,
)
from app.intelligence.readme_sanitizer import is_markup_noise_candidate, sanitize_text_for_display


class CanonicalOutputGuard:
    _FORBIDDEN_PATTERNS = (
        re.compile(r"content management application", re.IGNORECASE),
        re.compile(r"content management system", re.IGNORECASE),
        re.compile(r"\bcms\b", re.IGNORECASE),
        re.compile(r"\bcrm\b", re.IGNORECASE),
        re.compile(r"\becommerce\b", re.IGNORECASE),
        re.compile(r"analytics platform", re.IGNORECASE),
        re.compile(r"devops platform", re.IGNORECASE),
        re.compile(r"chatbot platform", re.IGNORECASE),
        re.compile(r"ai_hallucination_detection", re.IGNORECASE),
    )
    _EMOJI_PREFIX_RE = re.compile(r"^[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF\s]+")
    _AHAL_LEAK_PATTERNS = (
        re.compile(r"unfamiliar codebases", re.IGNORECASE),
        re.compile(r"repository-aware questions", re.IGNORECASE),
        re.compile(r"generate technical documentation", re.IGNORECASE),
        re.compile(r"architecture diffs", re.IGNORECASE),
        re.compile(r"test gap reports", re.IGNORECASE),
        re.compile(r"project intelligence", re.IGNORECASE),
    )
    _FINANCE_PATTERNS = (
        re.compile(r"financial research", re.IGNORECASE),
        re.compile(r"finance workflows", re.IGNORECASE),
        re.compile(r"investment research", re.IGNORECASE),
    )
    _MEDICAL_PATTERNS = (
        re.compile(r"medical diagnosis", re.IGNORECASE),
        re.compile(r"healthcare platform", re.IGNORECASE),
    )
    _DOC_APP_PATTERNS = (
        re.compile(r"Backend API Layer", re.IGNORECASE),
        re.compile(r"frontend app", re.IGNORECASE),
        re.compile(r"database integration", re.IGNORECASE),
        re.compile(r"auth missing", re.IGNORECASE),
        re.compile(r"deployment missing", re.IGNORECASE),
    )
    _RAW_DISPLAY_PATTERNS = (
        re.compile(r"<p", re.IGNORECASE),
        re.compile(r"<img", re.IGNORECASE),
        re.compile(r"</", re.IGNORECASE),
        re.compile(r"\bsrc\s*=", re.IGNORECASE),
        re.compile(r"\balt\s*=", re.IGNORECASE),
        re.compile(r"\bwidth\s*=", re.IGNORECASE),
        re.compile(r"\bheight\s*=", re.IGNORECASE),
        re.compile(r"\balign\s*=", re.IGNORECASE),
        re.compile(r"\.png\b", re.IGNORECASE),
        re.compile(r"\.svg\b", re.IGNORECASE),
        re.compile(r"public/branding", re.IGNORECASE),
        re.compile(r"logo-chatgpt-transparent", re.IGNORECASE),
    )

    @classmethod
    def sanitize_canonical(cls, canonical: CanonicalProjectIntelligence) -> CanonicalProjectIntelligence:
        sanitized = canonical.model_copy(deep=True)
        sanitized.product_summary = cls._sanitize_field_text(sanitized.product_summary, sanitized, prefer_summary=True)
        sanitized.project_goal = cls._sanitize_field_text(sanitized.project_goal or sanitized.product_summary, sanitized, prefer_summary=True)
        sanitized.what = cls._sanitize_field_text(sanitized.what, sanitized, prefer_summary=False)
        sanitized.why = cls.sanitize_why(sanitized)
        if cls._should_strip_ahal_why(sanitized):
            sanitized.why = cls._conservative_fallback(sanitized, field="why")
        sanitized.architecture_summary = cls.sanitize_text(sanitized.architecture_summary, sanitized)
        sanitized.product_domain = cls.sanitize_text(sanitized.product_domain, sanitized)
        sanitized.warnings = [cls.sanitize_text(item, sanitized) for item in sanitized.warnings if cls.sanitize_text(item, sanitized)]
        sanitized.completed = [
            CanonicalStatusItem(
                title=cls.sanitize_text(item.title, sanitized),
                description=cls._sanitize_field_text(item.description, sanitized, prefer_summary=False),
                evidence_ids=item.evidence_ids,
                confidence=item.confidence,
            )
            for item in sanitized.completed
        ]
        sanitized.remaining = [
            CanonicalStatusItem(
                title=cls.sanitize_text(item.title, sanitized),
                description=cls._sanitize_field_text(item.description, sanitized, prefer_summary=False),
                evidence_ids=item.evidence_ids,
                confidence=item.confidence,
            )
            for item in sanitized.remaining
        ]
        sanitized.issues = [
            CanonicalIssue(
                severity=cls.sanitize_text(item.severity, sanitized),
                title=cls._sanitize_field_text(item.title, sanitized, prefer_summary=False),
                recommendation=cls._sanitize_field_text(item.recommendation, sanitized, prefer_summary=False),
                evidence_ids=item.evidence_ids,
            )
            for item in sanitized.issues
        ]
        sanitized.api_surface = [
            CanonicalAPI(
                method=cls.sanitize_text(item.method, sanitized),
                path=cls.sanitize_text(item.path, sanitized),
                purpose=cls._sanitize_field_text(item.purpose, sanitized, prefer_summary=False),
                source=cls.sanitize_text(item.source, sanitized),
                evidence_ids=item.evidence_ids,
            )
            for item in sanitized.api_surface
        ]
        sanitized.workflow = [
            CanonicalWorkflowStep(
                step=item.step,
                title=cls.sanitize_text(item.title, sanitized),
                description=cls._sanitize_field_text(item.description, sanitized, prefer_summary=False),
                evidence_ids=item.evidence_ids,
            )
            for item in sanitized.workflow
        ]
        sanitized.evidence = [
            CanonicalEvidence(
                id=item.id,
                label=cls._sanitize_field_text(item.label, sanitized, prefer_summary=False),
                source_type=cls.sanitize_text(item.source_type, sanitized),
                reason=cls._sanitize_field_text(item.reason, sanitized, prefer_summary=False),
                confidence=item.confidence,
            )
            for item in sanitized.evidence
        ]
        cls.assert_no_forbidden_terms(sanitized.product_summary, sanitized)
        cls.assert_no_forbidden_terms(sanitized.what, sanitized)
        return sanitized

    @classmethod
    def sanitize_text(cls, text: str, canonical: CanonicalProjectIntelligence | None = None) -> str:
        raw_value = str(text or "").replace("**", "").strip()
        raw_had_markup = cls._contains_markup_noise(raw_value)
        value = raw_value
        value = sanitize_text_for_display(value, fallback="")
        value = cls._EMOJI_PREFIX_RE.sub("", value).strip()
        if not value:
            if canonical is not None and raw_had_markup:
                return cls._conservative_fallback(canonical, field="what")
            return ""
        value = re.sub(r"\bappears to be\b", "is organized as", value, flags=re.IGNORECASE)
        value = re.sub(r"\bclinical diagnosis\b", "medical diagnosis", value, flags=re.IGNORECASE)
        if canonical is not None and (raw_had_markup or cls._contains_markup_noise(value)):
            return cls._conservative_fallback(canonical, field="what")
        if canonical is not None and cls._contains_unsupported_terms(value, canonical):
            replacement = cls._fallback_text(canonical, prefer_summary=False)
            value = replacement if replacement else value
        if canonical is not None and cls._should_strip_ahal_why_for_text(value, canonical):
            value = cls._conservative_fallback(canonical, field="why")
        return value

    @classmethod
    def assert_no_forbidden_terms(cls, text: str, canonical: CanonicalProjectIntelligence | None = None) -> None:
        if canonical is None:
            return
        if cls._contains_unsupported_terms(str(text or ""), canonical):
            raise ValueError("Forbidden wrong-domain text detected in canonical output.")

    @classmethod
    def sanitize_why(cls, canonical: CanonicalProjectIntelligence) -> str:
        raw_value = str(getattr(canonical, "why", "") or "").replace("**", "").strip()
        raw_had_markup = cls._contains_markup_noise(raw_value)
        value = raw_value
        value = sanitize_text_for_display(value, fallback="")
        value = cls._EMOJI_PREFIX_RE.sub("", value).strip()
        if not value:
            return cls._conservative_fallback(canonical, field="why")
        value = re.sub(r"\bappears to be\b", "is organized as", value, flags=re.IGNORECASE)
        value = re.sub(r"\bclinical diagnosis\b", "medical diagnosis", value, flags=re.IGNORECASE)
        if raw_had_markup or cls._contains_markup_noise(value):
            return cls._conservative_fallback(canonical, field="why")
        if cls._contains_unsupported_terms(value, canonical):
            return cls._conservative_fallback(canonical, field="why")
        return cls._sanitize_field_text(value, canonical, prefer_summary=False)

    @classmethod
    def _sanitize_field_text(cls, text: str, canonical: CanonicalProjectIntelligence, prefer_summary: bool) -> str:
        raw_value = str(text or "").replace("**", "").strip()
        raw_had_markup = cls._contains_markup_noise(raw_value)
        value = raw_value
        value = sanitize_text_for_display(value, fallback="")
        value = cls._EMOJI_PREFIX_RE.sub("", value).strip()
        if not value:
            if raw_had_markup:
                field = "summary" if prefer_summary else "what"
                return cls._conservative_fallback(canonical, field=field)
            return ""
        value = re.sub(r"\bappears to be\b", "is organized as", value, flags=re.IGNORECASE)
        value = re.sub(r"\bclinical diagnosis\b", "medical diagnosis", value, flags=re.IGNORECASE)
        if raw_had_markup or cls._contains_markup_noise(value):
            field = "summary" if prefer_summary else "what"
            return cls._conservative_fallback(canonical, field=field)
        if cls._contains_unsupported_terms(value, canonical):
            replacement = cls._fallback_text(canonical, prefer_summary=prefer_summary)
            value = replacement if replacement else value
        return value

    @classmethod
    def _fallback_text(cls, canonical: CanonicalProjectIntelligence, prefer_summary: bool) -> str:
        if prefer_summary and str(getattr(canonical, "product_summary", "") or "").strip():
            return str(canonical.product_summary).replace("**", "").strip()
        if str(getattr(canonical, "what", "") or "").strip():
            return str(canonical.what).replace("**", "").strip()
        if str(getattr(canonical, "product_summary", "") or "").strip():
            return str(canonical.product_summary).replace("**", "").strip()
        return ""

    @classmethod
    def _contains_markup_noise(cls, text: str) -> bool:
        value = str(text or "")
        if not value.strip():
            return False
        return is_markup_noise_candidate(value) or any(pattern.search(value) for pattern in cls._RAW_DISPLAY_PATTERNS)

    @classmethod
    def _conservative_fallback(cls, canonical: CanonicalProjectIntelligence, field: str = "summary") -> str:
        name = str(getattr(canonical, "project_name", "") or "This project").strip()
        repo_type = str(getattr(canonical, "repo_type", "") or "").lower()
        project_type = str(getattr(canonical, "project_type", "") or "").lower()
        normalized = repo_type or project_type
        if field == "why":
            if normalized in {"frontend_app", "frontend"}:
                return f"{name} exists to coordinate the user-facing interface, interaction flow, and supporting application logic into a coherent product experience."
            if normalized in {"backend_service", "backend"}:
                return f"{name} exists to centralize API handling, service logic, and data operations behind a maintainable service boundary."
            if normalized in {"fullstack_app", "fullstack", "application"} or project_type == "fullstack":
                return f"{name} exists to connect the interface, application logic, and storage layer into a coherent product workflow."
            return f"{name} exists to centralize the repository's core workflow so the implementation remains maintainable, reviewable, and easy to extend."
        if normalized in {"frontend_app", "frontend"}:
            if field == "what":
                return f"{name} is organized as a frontend application that presents the product surface and coordinates user-facing workflows."
            return f"{name} is organized as a frontend application that presents the product surface and coordinates user-facing workflows."
        if normalized in {"backend_service", "backend"}:
            if field == "what":
                return f"{name} is organized as a backend service that concentrates API handling, service logic, and data operations."
            return f"{name} is organized as a backend service that concentrates API handling, service logic, and data operations."
        if normalized in {"fullstack_app", "fullstack", "application"} or project_type == "fullstack":
            if field == "what":
                return f"{name} is organized as a fullstack application that connects the user interface, application logic, and data flow."
            return f"{name} is organized as a fullstack application that connects the user interface, application logic, and data flow."
        if normalized in {"design_assets", "design_assets_repo"}:
            return f"{name} is organized as a design-assets repository that supports brand, UI, and creative delivery workflows."
        if field == "what":
            return f"{name} is organized as a software project with a maintainable workflow and supporting implementation details."
        return f"{name} is organized as a software project with a maintainable workflow and supporting implementation details."

    @classmethod
    def _contains_forbidden_terms(cls, text: str) -> bool:
        return any(pattern.search(str(text or "")) for pattern in cls._FORBIDDEN_PATTERNS)

    @classmethod
    def _contains_unsupported_terms(cls, text: str, canonical: CanonicalProjectIntelligence) -> bool:
        value = str(text or "")
        if cls._is_developer_project(canonical) and cls._contains_forbidden_terms(value):
            return True
        if not cls._supports_finance(canonical) and any(pattern.search(value) for pattern in cls._FINANCE_PATTERNS):
            return True
        if not cls._supports_medical(canonical) and any(pattern.search(value) for pattern in cls._MEDICAL_PATTERNS):
            return True
        if str(getattr(canonical, "repo_type", "") or "").lower() in {"documentation", "curriculum", "knowledge_base"} and any(
            pattern.search(value) for pattern in cls._DOC_APP_PATTERNS
        ):
            return True
        return False

    @classmethod
    def _supports_finance(cls, canonical: CanonicalProjectIntelligence) -> bool:
        joined = cls._canonical_supported_text(canonical)
        return any(token in joined for token in ("finance", "financial", "investment", "market", "stock", "portfolio", "trading"))

    @classmethod
    def _supports_medical(cls, canonical: CanonicalProjectIntelligence) -> bool:
        joined = cls._canonical_supported_text(canonical)
        return any(token in joined for token in ("medical", "healthcare", "clinical", "diagnosis"))

    @classmethod
    def _canonical_joined_text(cls, canonical: CanonicalProjectIntelligence) -> str:
        return " ".join(
            [
                str(getattr(canonical, "product_domain", "") or ""),
                str(getattr(canonical, "product_summary", "") or ""),
                str(getattr(canonical, "what", "") or ""),
                str(getattr(canonical, "why", "") or ""),
            ]
        ).lower()

    @classmethod
    def _canonical_supported_text(cls, canonical: CanonicalProjectIntelligence) -> str:
        return " ".join(
            [
                str(getattr(canonical, "product_domain", "") or ""),
                str(getattr(canonical, "product_summary", "") or ""),
                str(getattr(canonical, "what", "") or ""),
            ]
        ).lower()

    @classmethod
    def _is_developer_project(cls, canonical: CanonicalProjectIntelligence) -> bool:
        joined = " ".join(
            [
                str(getattr(canonical, "product_domain", "") or ""),
                str(getattr(canonical, "product_summary", "") or ""),
                str(getattr(canonical, "what", "") or ""),
            ]
        ).lower()
        return any(token in joined for token in ("developer", "code intelligence", "repository intelligence", "queryable knowledge", "code changes"))

    @classmethod
    def _should_strip_ahal_why(cls, canonical: CanonicalProjectIntelligence) -> bool:
        project_name = str(getattr(canonical, "project_name", "") or "").lower()
        if project_name in {"ahal", "ahal ai"}:
            return False
        if cls._is_developer_project(canonical):
            return False
        return any(pattern.search(str(getattr(canonical, "why", "") or "")) for pattern in cls._AHAL_LEAK_PATTERNS)

    @classmethod
    def _should_strip_ahal_why_for_text(cls, text: str, canonical: CanonicalProjectIntelligence) -> bool:
        project_name = str(getattr(canonical, "project_name", "") or "").lower()
        if project_name in {"ahal", "ahal ai"}:
            return False
        if cls._is_developer_project(canonical):
            return False
        return any(pattern.search(str(text or "")) for pattern in cls._AHAL_LEAK_PATTERNS)
