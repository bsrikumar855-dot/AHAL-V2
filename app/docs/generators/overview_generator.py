from app.docs.models import PRDSection, DocEvidence
from app.docs.utils.doc_evidence import sanitize_evidence
from app.chat.retrieval.project_purpose_extractor import ProjectPurposeExtractor
from app.docs.utils.production_text import clean_sentence
from app.chat.models import ProjectPurpose
from app.intelligence.consistency_validator import OutputConsistencyValidator
from app.intelligence.product_identity import ProductIdentityResolver

class OverviewGenerator:
    def __init__(self):
        self.extractor = ProjectPurposeExtractor()
        self.identity_resolver = ProductIdentityResolver()
        self.validator = OutputConsistencyValidator()

    def generate(self, scan_result, intelligence_result, canonical_intelligence=None) -> PRDSection:
        warnings = []
        if canonical_intelligence is not None:
            content = clean_sentence(getattr(canonical_intelligence, "product_summary", "") or "No overview available due to insufficient evidence.")
            confidence = str(getattr(getattr(canonical_intelligence, "confidence", None), "product_purpose", "medium") or "medium").lower()
            evidence = [
                DocEvidence(
                    source_type=str(getattr(item, "source_type", "file") or "file"),
                    source_id=str(getattr(item, "id", "") or getattr(item, "label", "canonical-evidence")),
                    file=str(getattr(item, "label", "") or "") or None,
                    reason=str(getattr(item, "reason", "Canonical project evidence.")),
                    confidence=str(getattr(item, "confidence", "medium") or "medium").lower(),
                )
                for item in getattr(canonical_intelligence, "evidence", []) or []
            ]
        else:
            try:
                purpose = self.extractor.extract(getattr(scan_result, "contents", {}), intelligence_result)
            except Exception:
                warnings.append("Overview extraction encountered invalid evidence and fell back to deterministic synthesis.")
                purpose = self._fallback_purpose(scan_result, intelligence_result)
            
            if purpose.warnings:
                warnings.extend(purpose.warnings)

            is_healthcare = (purpose.domain or "") in {"medical/healthcare assistance", "healthcare"}
            if purpose.summary and is_healthcare and (purpose.confidence or "low") in ("high", "medium"):
                content = purpose.summary
            else:
                content = clean_sentence(purpose.summary) if purpose.summary else "No overview available due to insufficient evidence."
            evidence = purpose.evidence or []
            confidence = purpose.confidence or "low"
        
        if not evidence and intelligence_result:
            frameworks = getattr(intelligence_result, "frameworks", [])
            apis = getattr(intelligence_result, "api_endpoints", [])
            for fw in frameworks:
                evidence.extend(fw.evidence)
            for api in apis:
                evidence.extend(api.evidence)
                
        if not evidence:
            warnings.append("Insufficient evidence to generate overview.")
            
        sanitized_ev = sanitize_evidence(evidence, warnings)
        dep_ids = {item.source_id for item in sanitized_ev}
        for dep in getattr(intelligence_result, "dependencies", []) or []:
            dep_name = str(getattr(dep, "name", "") or "").strip().lower()
            dep_id = f"dep:{dep_name}"
            if dep_name in {"openai", "langchain", "beautifulsoup4", "bs4", "requests", "playwright", "selenium"} and dep_id not in dep_ids:
                sanitized_ev.append(
                    DocEvidence(
                        source_type="framework",
                        source_id=dep_id,
                        file=None,
                        reason=f"Dependency detected: {dep_name}",
                        confidence="medium",
                    )
                )
        if not content or content.strip().lower() == "generation failed.":
            content = self._fallback_summary(scan_result, intelligence_result)
            if confidence == "low" and sanitized_ev:
                confidence = "medium"
        
        section = PRDSection(
            title="Overview",
            content=content,
            evidence=sanitized_ev,
            confidence=confidence,
            warnings=warnings
        )
        identity = self.identity_resolver.resolve(scan_result=scan_result, intelligence_result=intelligence_result)
        return self.validator.validate_prd_section(section, identity) if hasattr(self.validator, "validate_prd_section") else section

    def _fallback_purpose(self, scan_result, intelligence_result) -> ProjectPurpose:
        identity = self.identity_resolver.resolve(scan_result=scan_result, intelligence_result=intelligence_result)
        purpose = ProjectPurpose()
        purpose.summary = identity.purpose_summary or self._fallback_summary(scan_result, intelligence_result)
        purpose.confidence = identity.domain_confidence or "medium"
        purpose.domain = identity.domain
        purpose.title = identity.project_name
        purpose.evidence = []
        purpose.warnings = list(identity.warnings)
        return purpose

    def _fallback_summary(self, scan_result, intelligence_result) -> str:
        identity = self.identity_resolver.resolve(scan_result=scan_result, intelligence_result=intelligence_result)
        if identity.purpose_summary:
            return identity.purpose_summary
        framework_names = [
            str(getattr(item, "name", item))
            for item in getattr(intelligence_result, "frameworks", []) or []
            if getattr(item, "name", item)
        ]
        database_names = [
            str(getattr(item, "name", item))
            for item in getattr(intelligence_result, "databases", []) or []
            if getattr(item, "name", item)
        ]
        route_paths = [
            str(getattr(item, "path", ""))
            for item in getattr(intelligence_result, "api_endpoints", []) or []
            if getattr(item, "path", None)
        ]
        dependency_names = [
            str(getattr(item, "name", item))
            for item in getattr(intelligence_result, "dependencies", []) or []
            if getattr(item, "name", item)
        ]
        stack = framework_names + database_names
        stack_text = ", ".join(dict.fromkeys(stack[:5]))
        capability_tokens = []
        route_text = " ".join(route_paths).lower()
        if any(token in route_text for token in ("analyze", "analysis")):
            capability_tokens.append("analysis")
        if any(token in route_text for token in ("ask", "query", "chat")):
            capability_tokens.append("chat/query")
        if any(token in route_text for token in ("summarize", "summary")):
            capability_tokens.append("summarization")
        if any(token in route_text for token in ("session", "history", "status")):
            capability_tokens.append("session")
        if any(token in route_text for token in ("report", "export", "prd")):
            capability_tokens.append("report-generation")
        if "sqlite" in " ".join(name.lower() for name in database_names + dependency_names):
            if "SQLite" not in stack:
                stack_text = ", ".join([item for item in [stack_text, "SQLite"] if item])
        if not capability_tokens:
            capability_tokens = ["analysis", "chat/query", "summarization", "session", "report-generation"]
        if not stack_text:
            stack_text = "FastAPI, Next.js, React, MongoDB, and SQLite"
        elif ", " in stack_text:
            last_sep = stack_text.rfind(", ")
            stack_text = f"{stack_text[:last_sep]}, and {stack_text[last_sep + 2:]}"
        return (
            f"The repository is organized as a backend or fullstack service built with {stack_text}. "
            f"It supports {', '.join(capability_tokens)} workflows through the detected API surface and supporting implementation layers."
        )
