from __future__ import annotations

from typing import Any

from app.chat.retrieval.project_purpose_extractor import ProjectPurposeExtractor
from app.code.models import CodeSessionResult
from app.docs.prd_engine import PRDEngine
from app.docs.utils.evidence_sanitizer import sanitize_payload
from app.docs.utils.production_text import clean_list, clean_sentence
from app.graph.graph_engine import KnowledgeGraphEngine
from app.intelligence.canonical_presenter import CanonicalProjectPresenter, derive_project_why
from app.intelligence.consistency_validator import OutputConsistencyValidator
from app.intelligence.output_guard import CanonicalOutputGuard
from app.intelligence.intelligence_engine import IntelligenceEngine
from app.intelligence.product_identity import ProductIdentityResolver
from app.intelligence.product_identity_gate import repo_type_label
from app.models.file_schema import ScanResult
from app.sessions.session_manager import session_manager
from app.utils.ignored_paths import is_ignored_path


_FALLBACK_TEXT = "Insufficient evidence to determine full system purpose."
_SCHEMA_VERSION = 2


def build_intelligence_schema(session_id: str, session_type: str, scan_result: ScanResult | None) -> dict[str, Any]:
    info = session_manager.get_info(session_id)
    cached = session_manager.get_artifact(session_id, "intelligence_schema")
    if isinstance(cached, dict) and cached.get("schema_version") == _SCHEMA_VERSION:
        return _normalize_output_flags(sanitize_payload(_finalize_schema(cached)))
    truth_validator = OutputConsistencyValidator()
    identity_resolver = ProductIdentityResolver()
    canonical_presenter = CanonicalProjectPresenter()
    base = {
        "schema_version": _SCHEMA_VERSION,
        "session_id": session_id,
        "session_type": session_type,
        "status": getattr(info.status, "value", "completed") if info else "completed",
        "project_name": "this project",
        "project_goal": _FALLBACK_TEXT,
        "architecture_style": _FALLBACK_TEXT,
        "repo_type": "unknown",
        "key_modules": [],
        "core_features": [],
        "risks": [],
        "summary": {
            "what": _FALLBACK_TEXT,
            "why": _FALLBACK_TEXT,
            "remaining": [],
            "issues": [],
        },
        "technical": {
            "tech_stack": [],
            "api_surface": [],
            "workflow": [],
            "database": [],
        },
        "evidence": [],
        "warnings": clean_list(getattr(info, "warnings", []) if info else []),
        "confidence": getattr(info, "confidence", "low") if info else "low",
        "repo_visibility": getattr(info, "repo_visibility", "unknown") if info else "unknown",
        "hallucination_risk": "low",
    }

    if session_type == "code":
        code_result = session_manager.get_artifact(session_id, "code_result")
        if isinstance(code_result, CodeSessionResult):
            base["hallucination_risk"] = "medium" if code_result.confidence != "high" else "low"
            return _normalize_output_flags(sanitize_payload(_finalize_schema(_build_code_schema(base, code_result))))
        return _normalize_output_flags(sanitize_payload(_finalize_schema(base)))

    if scan_result is None:
        return _normalize_output_flags(sanitize_payload(_finalize_schema(base)))

    try:
        intelligence = IntelligenceEngine().analyze(scan_result=scan_result, session_id=session_id, include_llm_explanation=False)
        graph = KnowledgeGraphEngine().build(scan_result=scan_result, intelligence_result=intelligence, session_id=session_id)
        prd = PRDEngine().generate(scan_result=scan_result, intelligence_result=intelligence, graph_result=graph, session_id=session_id)
        purpose = ProjectPurposeExtractor().extract(getattr(scan_result, "contents", {}), intelligence)
        identity = identity_resolver.resolve(scan_result=scan_result, intelligence_result=intelligence)
        prd = truth_validator.validate_prd(prd, identity)
        canonical = canonical_presenter.build(session_id=session_id, scan_result=scan_result, intelligence_result=intelligence, graph_result=graph, prd_result=prd)
        base["project_name"] = identity.project_name or ("this backend service" if identity.domain == "generic_backend" else "this project")

        project_brief = getattr(prd, "project_brief", None)
        base["project_goal"] = clean_sentence(CanonicalOutputGuard.sanitize_text(canonical.project_goal or getattr(getattr(project_brief, "goal", None), "content", purpose.summary or _FALLBACK_TEXT), canonical))
        base["architecture_style"] = clean_sentence(getattr(getattr(intelligence, "architecture", None), "type", _FALLBACK_TEXT))
        base["key_modules"] = [
            {
                "name": getattr(module, "name", ""),
                "category": getattr(module, "category", ""),
                "description": clean_sentence(getattr(module, "description", getattr(module, "name", _FALLBACK_TEXT))),
            }
            for module in getattr(prd, "modules", [])[:8]
            if getattr(module, "name", "")
        ]
        base["core_features"] = clean_list(
            list(getattr(purpose, "capabilities", []) or [])
            + [f"{getattr(api, 'method', '').upper()} {getattr(api, 'path', '')}" for api in getattr(intelligence, "api_endpoints", [])[:4]]
        )
        base["risks"] = [
            {
                "title": getattr(risk, "title", ""),
                "severity": getattr(risk, "severity", "low"),
                "recommendation": clean_sentence(getattr(risk, "recommendation", _FALLBACK_TEXT)),
            }
            for risk in getattr(prd, "risks", [])[:8]
            if getattr(risk, "title", "")
        ]
        base["summary"] = {
            "what": clean_sentence(CanonicalOutputGuard.sanitize_text(canonical.what, canonical)),
            "why": clean_sentence(CanonicalOutputGuard.sanitize_text(canonical.why, canonical)),
            "remaining": [clean_sentence(item.description or item.title or _FALLBACK_TEXT) for item in canonical.remaining[:6]],
            "issues": [clean_sentence(item.title or _FALLBACK_TEXT) for item in canonical.issues[:6]],
        }
        base["project_brief"] = {
            "goal": base["project_goal"],
            "what": base["summary"]["what"],
            "why": base["summary"]["why"],
        }
        base["technical"] = {
            "tech_stack": clean_list(canonical.tech_stack.languages + canonical.tech_stack.frameworks + canonical.tech_stack.tools),
            "api_surface": [item.model_dump() for item in canonical.api_surface[:10]],
            "workflow": [item.model_dump() for item in canonical.workflow[:8]],
            "database": clean_list(canonical.tech_stack.databases),
        }
        base["evidence"] = [item.model_dump() for item in canonical.evidence]
        base["warnings"] = clean_list(list(base["warnings"]) + list(getattr(prd, "warnings", []) or []) + list(getattr(intelligence, "warnings", []) or []))
        base["confidence"] = canonical.confidence.overall.lower()
        base["project_type"] = canonical.project_type
        base["repo_type"] = canonical.repo_type
        base["architecture_confidence"] = canonical.confidence.architecture.lower()
        base["product_purpose_confidence"] = canonical.confidence.product_purpose.lower()
        base["hallucination_risk"] = _hallucination_risk(
            canonical.confidence.overall,
            canonical.confidence.architecture,
            canonical.confidence.product_purpose,
            base["warnings"],
        )
        if base["hallucination_risk"] in {"medium", "high"}:
            base["warnings"] = clean_list(
                list(base["warnings"]) + ["Hallucination guard is active because the repository evidence required conservative wording."]
            )
        base["canonical_intelligence"] = canonical.model_dump()
        session_manager.set_session_metadata(
            session_id,
            confidence=base["confidence"],
            warnings=base["warnings"],
            repo_visibility=base["repo_visibility"],
        )
    except Exception as exc:
        identity = identity_resolver.resolve(scan_result=scan_result, intelligence_result=None)
        purpose = ProjectPurposeExtractor().extract(getattr(scan_result, "contents", {}), None)
        repo_architecture = str(identity.architecture or "software project").lower()
        repo_type_hint = {
            "frontend": "frontend_app",
            "backend": "backend_service",
            "fullstack": "fullstack_app",
        }.get(repo_architecture, "unknown")
        project_name = identity.project_name or "This repository"
        base["project_name"] = project_name
        base["project_goal"] = clean_sentence(getattr(identity, "purpose_summary", "") or getattr(purpose, "summary", "") or _FALLBACK_TEXT)
        fallback_source = " ".join(
            [
                str(getattr(identity, "purpose_summary", "") or ""),
                str(base["project_goal"] or ""),
                str(getattr(purpose, "summary", "") or ""),
            ]
        ).lower()
        if repo_architecture == "backend" or "backend api service" in fallback_source or "backend service" in fallback_source:
            fallback_why = "It exists to centralize the application's core logic and API handling behind a maintainable service boundary."
        elif repo_architecture == "frontend" or "frontend application" in fallback_source:
            fallback_why = "It exists to present the user-facing experience and coordinate the main interaction workflow."
        elif repo_architecture == "fullstack" or "fullstack application" in fallback_source:
            fallback_why = "It exists to connect the user interface, application logic, and shared workflow into one coherent product experience."
        else:
            fallback_why = derive_project_why(project_name, "", repo_type_hint, identity.domain or "", base["project_goal"])
        if repo_architecture == "frontend":
            base["summary"] = {
                "what": clean_sentence(f"{project_name} is organized as a frontend application. It coordinates the user-facing interface, interaction flow, and supporting application behavior into a coherent product surface."),
                "why": clean_sentence(fallback_why),
                "remaining": [],
                "issues": [],
            }
        elif repo_architecture == "fullstack":
            base["summary"] = {
                "what": clean_sentence(f"{project_name} is organized as a fullstack application. It connects the interface, application logic, and data flow into a coherent product workflow."),
                "why": clean_sentence(fallback_why),
                "remaining": [],
                "issues": [],
            }
        elif repo_architecture == "backend":
            base["summary"] = {
                "what": clean_sentence(f"{project_name} is organized as a backend API service. It centralizes API handling, service logic, and data operations behind a maintainable service boundary."),
                "why": clean_sentence(fallback_why),
                "remaining": [],
                "issues": [],
            }
        else:
            base["summary"] = {
                "what": clean_sentence(f"{project_name} is organized as a software project. It coordinates the repository's primary workflow and supporting implementation details."),
                "why": clean_sentence(fallback_why),
                "remaining": [],
                "issues": [],
            }
        base["architecture_style"] = clean_sentence(f"{identity.architecture.capitalize()} application.") if identity.architecture else _FALLBACK_TEXT
        base["key_modules"] = []
        base["core_features"] = clean_list(list(getattr(purpose, "capabilities", []) or []))
        base["risks"] = []
        base["project_brief"] = {
            "goal": base["project_goal"],
            "what": base["summary"]["what"],
            "why": base["summary"]["why"],
        }
        base["technical"] = {
            "tech_stack": [],
            "api_surface": [],
            "workflow": [],
            "database": [],
        }
        base["evidence"] = [item.model_dump() for item in getattr(identity, "evidence", [])[:8]]
        base["warnings"] = clean_list(list(base["warnings"]) + list(getattr(identity, "warnings", [])) + [f"Intelligence generation fell back to deterministic evidence parsing: {type(exc).__name__}"])
        base["confidence"] = identity.domain_confidence
        base["project_type"] = repo_architecture or "software"
        base["repo_type"] = repo_type_hint
        base["architecture_confidence"] = identity.domain_confidence
        base["product_purpose_confidence"] = identity.domain_confidence
        base["hallucination_risk"] = _hallucination_risk(
            base["confidence"],
            base["architecture_confidence"],
            base["product_purpose_confidence"],
            base["warnings"],
        )
        if base["hallucination_risk"] in {"medium", "high"}:
            base["warnings"] = clean_list(
                list(base["warnings"]) + ["Hallucination guard is active because the repository evidence required conservative wording."]
            )
        base["canonical_intelligence"] = {
            "project_name": project_name,
            "product_summary": base["summary"]["what"],
            "project_goal": base["project_goal"],
            "what": base["summary"]["what"],
            "why": base["summary"]["why"],
        }
        session_manager.set_session_metadata(
            session_id,
            confidence=base["confidence"],
            warnings=base["warnings"],
            repo_visibility=base["repo_visibility"],
        )
    result = _normalize_output_flags(sanitize_payload(_finalize_schema(base)))
    session_manager.set_artifact(session_id, "intelligence_schema", result)
    return result


def _build_code_schema(base: dict[str, Any], code_result: CodeSessionResult) -> dict[str, Any]:
    is_minimal = not code_result.detected_functions and not code_result.detected_classes and not code_result.entrypoints
    
    base["project_goal"] = _FALLBACK_TEXT if is_minimal else clean_sentence(code_result.summary)
    base["architecture_style"] = _FALLBACK_TEXT if is_minimal else clean_sentence(f"Code snippet analysis for {code_result.language}.")
    base["key_modules"] = [
        {"name": name, "category": "class", "description": clean_sentence(f"Detected class {name}.")}
        for name in code_result.detected_classes[:8]
    ]
    base["core_features"] = clean_list(code_result.detected_functions + code_result.entrypoints)
    base["risks"] = [{"title": issue, "severity": "medium", "recommendation": "Review and validate this potential issue before production use."} for issue in code_result.issues[:6]]
    base["summary"] = {
        "what": _FALLBACK_TEXT if is_minimal else clean_sentence(code_result.summary),
        "why": _FALLBACK_TEXT,
        "remaining": clean_list(code_result.suggested_improvements),
        "issues": clean_list(code_result.issues),
    }
    base["technical"] = {
        "tech_stack": clean_list([code_result.language] + code_result.imports),
        "api_surface": [],
        "workflow": [],
        "database": [],
    }
    base["evidence"] = [{"source_id": item.source_id, "reason": clean_sentence(item.reason)} for item in code_result.evidence[:10]]
    base["warnings"] = clean_list(list(base["warnings"]) + list(code_result.warnings))
    base["confidence"] = code_result.confidence
    return base


def _collect_evidence(intelligence) -> list[dict[str, str]]:
    evidence = []
    for collection in (
        getattr(intelligence, "frameworks", []),
        getattr(intelligence, "api_endpoints", []),
        getattr(intelligence, "modules", []),
        getattr(intelligence, "databases", []),
    ):
        for item in collection:
            for ev in getattr(item, "evidence", [])[:2]:
                file_path = getattr(ev, "file", "")
                if file_path and not is_ignored_path(file_path):
                    evidence.append({"file": file_path, "reason": clean_sentence(getattr(ev, "reason", ""))})
            if len(evidence) >= 12:
                return evidence
    return evidence


def _infer_project_name(info, scan_result: ScanResult | None) -> str:
    if info and getattr(info, "source_name", ""):
        source_name = str(info.source_name)
        return source_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or source_name
    contents = getattr(scan_result, "contents", {}) if scan_result else {}
    if isinstance(contents, dict):
        for path in contents.keys():
            if "readme" in str(path).lower():
                return "Project"
    return "Project"


def _confidence_label(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _hallucination_risk(overall: str, architecture: str, product_purpose: str, warnings: list[str]) -> str:
    lowered = " ".join([str(overall or ""), str(architecture or ""), str(product_purpose or ""), " ".join(warnings or [])]).lower()
    if any(token in lowered for token in ("product purpose evidence is partial", "insufficient evidence", "conservative wording", "maintainable workflow")):
        return "high"
    levels = [str(overall or "").lower(), str(architecture or "").lower(), str(product_purpose or "").lower()]
    low_count = sum(1 for level in levels if level == "low")
    medium_count = sum(1 for level in levels if level == "medium")
    if low_count >= 2:
        return "high"
    if low_count == 1 or medium_count > 0:
        return "medium"
    return "low"


def _finalize_schema(value):
    if isinstance(value, dict):
        finalized = {}
        for key, item in value.items():
            finalized[str(key)] = _finalize_schema(item)
        return finalized
    if isinstance(value, list):
        return [_finalize_schema(item) for item in value if _finalize_schema(item) not in (None, "")]
    if value is None:
        return ""
    if isinstance(value, str):
        cleaned = clean_sentence(value) if value and value in {"unknown", "Unknown"} else str(value)
        lowered = cleaned.lower()
        if "magicmock" in lowered or "type='" in lowered or "confidence='" in lowered:
            return _FALLBACK_TEXT
        if is_ignored_path(cleaned):
            return ""
        return cleaned
    return value


def _normalize_output_flags(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    payload["repo_visibility"] = str(payload.get("repo_visibility", "unknown") or "unknown").strip().lower().rstrip(".") or "unknown"
    payload["hallucination_risk"] = str(payload.get("hallucination_risk", "low") or "low").strip().lower().rstrip(".") or "low"
    return payload
