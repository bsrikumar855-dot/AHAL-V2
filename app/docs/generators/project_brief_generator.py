from app.docs.models import ProjectBrief, ProjectStatusItem, PRDSection, RiskItem, DocEvidence
from typing import List
from unittest.mock import Mock
from app.docs.utils.production_text import safe_next_steps
from app.docs.fact_snapshot import PRDFactSnapshot, build_fact_snapshot
from app.intelligence.product_identity import ProductIdentityResolver
from app.intelligence.repository_type_classifier import is_documentation_repo_type

def safe_str(value, default="") -> str:
    if value is None:
        return default
    if isinstance(value, Mock):
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        text = str(value)
    except Exception:
        return default
    if "MagicMock" in text or "Mock" in text:
        return default
    return text

def safe_join(values, sep=", ") -> str:
    cleaned = []
    for value in values or []:
        text = safe_str(value).strip()
        if text:
            cleaned.append(text)
    return sep.join(cleaned)

def safe_sequence(value):
    if isinstance(value, Mock):
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return []

class ProjectBriefGenerator:
    def __init__(self):
        self.identity_resolver = ProductIdentityResolver()

    def _has_database_evidence(self, intelligence_result, scan_result=None) -> bool:
        databases = getattr(intelligence_result, "databases", None)

        if isinstance(databases, (list, tuple, set)) and len(databases) > 0:
            return True


        db_keywords = ["mongodb", "postgresql", "mysql", "sqlite", "redis", "prisma", "sqlalchemy", "motor", "pymongo"]

        for f in safe_sequence(getattr(intelligence_result, "frameworks", [])):
            if any(k in safe_str(getattr(f, "name", f)).lower() for k in db_keywords):
                return True

        for dep in safe_sequence(getattr(intelligence_result, "dependencies", [])):
            if any(k in safe_str(getattr(dep, "name", dep)).lower() for k in db_keywords):
                return True

        for mod in safe_sequence(getattr(intelligence_result, "modules", [])):
            name = safe_str(getattr(mod, "name", mod)).lower()
            if any(k in name for k in db_keywords + ["db", "database", "repository.py", "models.py", "schemas.py"]):
                return True

        if scan_result:
            for f in safe_sequence(getattr(scan_result, "files", [])):
                f_lower = safe_str(getattr(f, "path", f)).lower()
                if any(key in f_lower for key in db_keywords + ["db", "database", "repository", "models", "schemas"]):
                    return True
            contents = getattr(scan_result, "contents", {})
            if isinstance(contents, dict):
                for k, v in contents.items():
                    k_lower = safe_str(k).lower()
                    if any(key in k_lower for key in db_keywords + ["db", "database", "repository", "models", "schemas"]):
                        return True
                    v_str = safe_str(v).lower()
                    if any(key in v_str for key in ["mongodb://", "mongo_uri", "database_url", "sqlite", "pymongo", "motor", "sqlalchemy"]):
                        return True

        return False

    def generate(
        self,
        scan_result,
        intelligence_result,
        graph_result,
        overview: PRDSection,
        risks: List[RiskItem],
        snapshot: PRDFactSnapshot | None = None,
        product_identity=None,
        canonical_intelligence=None,
    ) -> ProjectBrief:
        warnings = []
        product_identity = product_identity or self.identity_resolver.resolve(scan_result=scan_result, intelligence_result=intelligence_result)
        snapshot = snapshot or build_fact_snapshot(scan_result=scan_result, intelligence_result=intelligence_result, product_identity=product_identity)

        overview_lower = safe_str(getattr(overview, "content", ""), "").lower()
        has_runtime_signals = bool(
            snapshot.has_backend
            or snapshot.has_frontend
            or snapshot.api_count
            or any(token in overview_lower for token in ("backend", "frontend", "api", "service", "fastapi", "application"))
        )

        if is_documentation_repo_type(snapshot.repo_type) and canonical_intelligence is None and not has_runtime_signals:
            goal_text = safe_str(overview.content, "This repository appears to contain documentation or curriculum content.")
            what_text = "This repository organizes documentation, study-plan content, or reference material rather than an executable application."
            why_text = "It exists to help readers follow structured documentation or learning resources."
            completed = [
                ProjectStatusItem(title="Documentation Content", status="built", description="Repository documentation content is present.", confidence="high"),
                ProjectStatusItem(title="Resource Organization", status="built", description="Topics and resources are organized for readers.", confidence="medium"),
            ]
            remaining = [
                ProjectStatusItem(title="No executable application architecture was detected.", status="missing", description="No executable application architecture was detected.", confidence="high"),
                ProjectStatusItem(title="Database / Storage", status="missing", description="No database/storage layer is required based on available evidence.", confidence="high"),
            ]
            return ProjectBrief(
                goal=PRDSection(title="Project Goal", content=goal_text, confidence="medium"),
                what=PRDSection(title="What This Project Is", content=what_text, confidence="medium"),
                why=PRDSection(title="Why This Project Exists", content=why_text, confidence="medium"),
                completed=completed,
                remaining=remaining,
                issues=[],
                next_steps=safe_next_steps(remaining, []),
                confidence="medium",
                warnings=[],
            )

        if canonical_intelligence is not None:
            canonical_confidence = safe_str(getattr(getattr(canonical_intelligence, "confidence", None), "product_purpose", "medium"), "medium").lower()
            goal_section = PRDSection(
                title="Project Goal",
                content=safe_str(getattr(canonical_intelligence, "project_goal", "") or getattr(canonical_intelligence, "product_summary", "")),
                evidence=[],
                confidence=canonical_confidence,
            )
            what_section = PRDSection(
                title="What This Project Is",
                content=safe_str(getattr(canonical_intelligence, "what", "")),
                evidence=[],
                confidence=canonical_confidence,
            )
            why_section = PRDSection(
                title="Why This Project Exists",
                content=safe_str(getattr(canonical_intelligence, "why", "")),
                evidence=[],
                confidence=canonical_confidence,
            )
            completed = [
                ProjectStatusItem(
                    title=safe_str(getattr(item, "title", ""), "Detected capability"),
                    status="built",
                    description=safe_str(getattr(item, "description", ""), "Capability details were not returned."),
                    evidence=[],
                    confidence=safe_str(getattr(item, "confidence", "medium"), "medium").lower(),
                )
                for item in safe_sequence(getattr(canonical_intelligence, "completed", []))
            ]
            remaining = [
                ProjectStatusItem(
                    title=safe_str(getattr(item, "title", ""), "Remaining work"),
                    status="missing",
                    description=safe_str(getattr(item, "description", ""), "Remaining work details were not returned."),
                    evidence=[],
                    confidence=safe_str(getattr(item, "confidence", "medium"), "medium").lower(),
                )
                for item in safe_sequence(getattr(canonical_intelligence, "remaining", []))
            ]
            issues = [
                RiskItem(
                    severity=safe_str(getattr(item, "severity", "medium"), "medium").lower(),
                    title=safe_str(getattr(item, "title", ""), "Detected issue"),
                    description=safe_str(getattr(item, "title", ""), "Detected issue"),
                    evidence=[],
                    recommendation=safe_str(getattr(item, "recommendation", ""), "Review this issue and confirm follow-up action."),
                )
                for item in safe_sequence(getattr(canonical_intelligence, "issues", []))
            ]
            next_steps = safe_next_steps(remaining, issues)
            brief = ProjectBrief(
                goal=goal_section,
                what=what_section,
                why=why_section,
                completed=completed,
                remaining=remaining,
                issues=issues,
                next_steps=next_steps,
                confidence=canonical_confidence if canonical_confidence in {"high", "medium", "low"} else "medium",
                warnings=[],
            )
            assert brief.what.content == canonical_intelligence.what
            return brief

        def _safe_mapping_keys(value):
            if isinstance(value, dict):
                return [str(k) for k in value.keys()]
            return []

        def _safe_file_paths(scan_result):
            files = getattr(scan_result, "files", [])
            paths = []
            if isinstance(files, list):
                for f in files:
                    path = safe_str(getattr(f, "path", f))
                    if path:
                        paths.append(path)
            return paths

        contents = getattr(scan_result, "contents", {})
        content_keys = _safe_mapping_keys(contents)
        file_paths = _safe_file_paths(scan_result)
        all_paths = content_keys + file_paths
        
        # 1. Project Goal
        goal_content = self._goal_content(snapshot, product_identity, overview)
        goal_section = PRDSection(
            title="Project Goal",
            content=goal_content,
            evidence=overview.evidence,
            confidence=safe_str(overview.confidence, "low")
        )

        arch = getattr(intelligence_result, "architecture", "unknown")
        arch_type = safe_str(getattr(arch, "type", arch), "unknown")
        
        lower_content = safe_str(overview.content).lower()
        is_medical = "medical" in lower_content or "healthcare" in lower_content
        is_repo_intel = (
            (getattr(snapshot, "domain", None) == "repository_intelligence" and getattr(snapshot, "domain_confidence", "low") in {"high", "medium"})
            or "repository intelligence" in lower_content
            or "repository intelligence tool" in str(getattr(scan_result, "contents", {})).lower()
        )

        # 2. What This Project Is
        what_evidence = overview.evidence
        what_content = overview.content
        what_confidence = overview.confidence
            
        what_section = PRDSection(
            title="What This Project Is",
            content=what_content,
            evidence=what_evidence,
            confidence=what_confidence
        )

        # 3. Why This Project Exists
        why_evidence = [DocEvidence(source_type="file", source_id="project-purpose", reason="Derived from project purpose and detected implementation evidence.", confidence="medium")]
        architecture = str(getattr(snapshot, "architecture", "") or getattr(snapshot, "project_type", "") or getattr(snapshot, "repo_type", "") or "").lower()
        if is_repo_intel:
            why_content = "It exists to help users inspect repository structure, answer codebase questions, and produce analysis artifacts from repository evidence in a single workflow."
        elif getattr(snapshot, "domain", None) == "ai_hallucination_detection":
            why_content = "It exists to evaluate claims or AI-generated answers against external evidence when those verification workflows are present."
        elif is_medical:
            why_content = "It exists to support medical query workflows using AI-assisted diagnosis and retrieval components."
        else:
            if architecture == "frontend":
                why_content = "It exists to coordinate the user-facing experience, interaction flow, and supporting application behavior into a coherent product surface."
            elif architecture == "fullstack":
                why_content = "It exists to connect the interface, application logic, and data flow into a coherent product workflow."
            elif architecture == "backend":
                why_content = "It exists to centralize request handling, service logic, and data operations behind a maintainable service boundary."
            elif snapshot.repo_type == "dataset":
                why_content = "It exists to publish versioned release assets and supporting metadata so downstream users can install and reuse the binaries without rebuilding them locally."
            else:
                why_content = "It exists to centralize the repository's core workflow so the implementation remains maintainable, reviewable, and easy to extend."
            why_evidence[0].confidence = "low"
            
        why_section = PRDSection(
            title="Why This Project Exists",
            content=why_content,
            evidence=why_evidence,
            confidence=what_confidence
        )

        # 4. What Is Already Built
        completed: List[ProjectStatusItem] = []
        frameworks = safe_sequence(getattr(intelligence_result, "frameworks", []))
        f_names = []
        for f in frameworks:
            name = safe_str(getattr(f, "name", f))
            if name:
                f_names.append(name)
        if f_names:
            completed.append(ProjectStatusItem(
                title="Frameworks",
                status="built",
                description=f"Frameworks integrated: {safe_join(f_names)}",
                evidence=[DocEvidence(source_type="framework", source_id="fws", reason="Detected frameworks", confidence="high")],
                confidence="high"
            ))

        api_endpoints = safe_sequence(getattr(intelligence_result, "api_endpoints", []))
        if snapshot.api_count > 0:
            completed.append(ProjectStatusItem(
                title="API Layer",
                status="built",
                description=f"Backend API layer built with {snapshot.api_count} endpoints.",
                evidence=[DocEvidence(source_type="api", source_id="api", reason="Detected API routes", confidence="high")],
                confidence="high"
            ))
            
        databases = safe_sequence(getattr(intelligence_result, "databases", []))
        db_names = []
        for db in databases:
            name = safe_str(getattr(db, "name", None))
            if not name:
                name = safe_str(getattr(db, "type", None))
            if not name:
                name = safe_str(db)
            if name:
                db_names.append(name)
                
        has_db = snapshot.has_database or self._has_database_evidence(intelligence_result, scan_result)
        
        if db_names:
            completed.append(ProjectStatusItem(
                title="Database Integration",
                status="built",
                description=f"Database integration built: {safe_join(db_names)}",
                evidence=[DocEvidence(source_type="database", source_id="db", reason="Detected databases", confidence="high")],
                confidence="high"
            ))
            
        completed_titles = [safe_str(getattr(item, "title", "")) for item in completed]
        if has_db and not any("database" in title.lower() or "storage" in title.lower() for title in completed_titles):
            completed.append(ProjectStatusItem(
                title="Database integration",
                status="built",
                description="Database or storage evidence was detected in the codebase.",
                evidence=[DocEvidence(source_type="heuristics", source_id="db_evidence", reason="Detected database evidence", confidence="medium")],
                confidence="medium",
            ))

        modules = safe_sequence(getattr(intelligence_result, "modules", []))
        valid_modules = []
        for mod in modules:
            name = safe_str(getattr(mod, "name", mod))
            if name:
                valid_modules.append(mod)
        if snapshot.module_count > 0 and valid_modules:
            completed.append(ProjectStatusItem(
                title="Core Modules",
                status="built",
                description=f"{snapshot.module_count} core modules present.",
                evidence=[DocEvidence(source_type="module", source_id="mod", reason="Detected modules", confidence="high")],
                confidence="high"
            ))
            
        has_tests = snapshot.has_tests
        if has_tests:
            completed.append(ProjectStatusItem(
                title="Testing",
                status="built",
                description="Test suite is present.",
                evidence=[DocEvidence(source_type="file", source_id="tests", reason="Test files detected", confidence="high")],
                confidence="high"
            ))
            
        has_setup = snapshot.has_setup
        if has_setup:
            completed.append(ProjectStatusItem(
                title="Setup Configuration",
                status="built",
                description="Setup instructions/configurations present.",
                evidence=[DocEvidence(source_type="file", source_id="setup", reason="Setup files detected", confidence="high")],
                confidence="high"
            ))

        # Check endpoints for features
        chat_built = False
        analyze_built = False
        report_built = False
        for ep in api_endpoints:
            p = getattr(ep, "path", "").lower()
            if "chat" in p or "query" in p or "ask" in p:
                chat_built = True
            if "analyze" in p or "upload" in p or "github" in p:
                analyze_built = True
            if "report" in p or "prd" in p or "summarize" in p:
                report_built = True

        if chat_built:
            completed.append(ProjectStatusItem(
                title="Chat/Query API",
                status="built",
                description="Chat/query API built.",
                evidence=[DocEvidence(source_type="api", source_id="chat_api", reason="Chat endpoints detected", confidence="high")],
                confidence="high"
            ))
        if analyze_built:
            completed.append(ProjectStatusItem(
                title="Repository Analysis API" if is_repo_intel else "Analysis API",
                status="built",
                description="Repository analysis API built." if is_repo_intel else "Analysis API built.",
                evidence=[DocEvidence(source_type="api", source_id="analyze_api", reason="Analyze endpoints detected", confidence="high")],
                confidence="high"
            ))
        if report_built:
            completed.append(ProjectStatusItem(
                title="Report/PRD Generation" if is_repo_intel else "Report Generation",
                status="built",
                description="Report/PRD generation built." if is_repo_intel else "Report generation built.",
                evidence=[DocEvidence(source_type="api", source_id="report_api", reason="Report endpoints detected", confidence="high")],
                confidence="high"
            ))

        # 5. What Is Remaining
        remaining: List[ProjectStatusItem] = []
        
        has_auth = False
        for mod in valid_modules:
            name = safe_str(getattr(mod, "name", "")).lower()
            cat = safe_str(getattr(mod, "category", "")).lower()
            if "auth" in name or "auth" in cat:
                has_auth = True
                break
        for dep in safe_sequence(getattr(intelligence_result, "dependencies", [])):
            name = safe_str(getattr(dep, "name", dep)).lower()
            if "auth" in name or "jwt" in name:
                has_auth = True
                break
                
        if not snapshot.has_auth:
            remaining.append(ProjectStatusItem(
                title="Authentication",
                status="missing",
                description="No auth detected.",
                evidence=[DocEvidence(source_type="absence", source_id="auth", reason="No auth modules/dependencies", confidence="high")],
                confidence="high"
            ))

        if not has_tests:
            remaining.append(ProjectStatusItem(
                title="Tests",
                status="missing",
                description="No tests detected.",
                evidence=[DocEvidence(source_type="absence", source_id="tests", reason="No test files found", confidence="high")],
                confidence="high"
            ))

        has_docker = snapshot.has_deployment
        has_deploy = snapshot.has_deployment
        if not has_deploy:
            remaining.append(ProjectStatusItem(
                title="Deployment Configuration",
                status="missing",
                description="No deployment config detected.",
                evidence=[DocEvidence(source_type="absence", source_id="deploy", reason="No common deployment files found", confidence="high")],
                confidence="high"
            ))

        has_cicd = snapshot.has_ci_cd
        if not has_cicd:
            remaining.append(ProjectStatusItem(
                title="CI/CD",
                status="missing",
                description="No CI/CD detected.",
                evidence=[DocEvidence(source_type="absence", source_id="cicd", reason="No CI/CD configs found", confidence="high")],
                confidence="high"
            ))

        if not has_db:
            remaining.append(ProjectStatusItem(
                title="Database",
                status="missing",
                description="No database detected.",
                evidence=[DocEvidence(source_type="absence", source_id="database", reason="No database indicators found", confidence="high")],
                confidence="high"
            ))

        has_readme = any("readme" in p.lower() for p in all_paths)
        if not has_readme:
            remaining.append(ProjectStatusItem(
                title="README",
                status="missing",
                description="No README detected.",
                evidence=[DocEvidence(source_type="absence", source_id="readme", reason="No README file found", confidence="high")],
                confidence="high"
            ))

        # Workflow
        wf = getattr(intelligence_result, "workflow", None)
        wf_steps = safe_sequence(getattr(wf, "steps", [])) if wf else []
        if wf_steps and len(wf_steps) < 3:
            remaining.append(ProjectStatusItem(
                title="Workflow Documentation",
                status="partial",
                description="Partial workflow only.",
                evidence=[DocEvidence(source_type="heuristics", source_id="workflow", reason="Few workflow steps detected", confidence="high")],
                confidence="medium"
            ))

        # 6. Current Issues / Risks
        safe_risks = []
        for r in safe_sequence(risks):
            safe_title = safe_str(getattr(r, "title", "Risk"))
            safe_desc = safe_str(getattr(r, "description", ""))
            safe_sev = safe_str(getattr(r, "severity", "medium"))
            safe_rec = safe_str(getattr(r, "recommendation", ""))
            safe_r = RiskItem(title=safe_title, description=safe_desc, severity=safe_sev, recommendation=safe_rec)
            safe_risks.append(safe_r)

        # 7. Recommended Next Steps
        next_steps = safe_next_steps(remaining, safe_risks)
        
        if len(api_endpoints) > 5 and "Add or expand API documentation" not in next_steps:
            next_steps.append("Add or expand API documentation given the surface area.")
            
        if db_names and "Add database migration and backup documentation." not in next_steps:
            next_steps.append("Add database migration and backup documentation.")

        # Confidence Calculation
        if safe_str(overview.confidence) in ("high", "medium") and len(completed) >= 3:
            overall_confidence = "high"
        elif safe_str(overview.confidence) in ("high", "medium"):
            overall_confidence = "medium"
        else:
            overall_confidence = "low"

        def _title_key(item):
            return safe_str(getattr(item, "title", "")).strip().lower().replace("/", " ").replace("-", " ")

        if has_db:
            remaining = [
                item for item in remaining
                if "database" not in _title_key(item)
                and "storage" not in _title_key(item)
            ]
        if has_docker:
            remaining = [
                item for item in remaining
                if "deployment" not in _title_key(item)
                and "docker" not in _title_key(item)
            ]
        if has_tests:
            remaining = [
                item for item in remaining
                if "test" not in _title_key(item)
            ]
        if has_readme:
            remaining = [
                item for item in remaining
                if "readme" not in _title_key(item)
            ]
        if has_cicd:
            remaining = [
                item for item in remaining
                if "ci cd" not in _title_key(item)
                and "cicd" not in _title_key(item)
            ]

        return ProjectBrief(
            goal=goal_section,
            what=what_section,
            why=why_section,
            completed=completed,
            remaining=remaining,
            issues=safe_risks,
            next_steps=next_steps,
            confidence=overall_confidence,
            warnings=warnings
        )

    def _goal_content(self, snapshot: PRDFactSnapshot, product_identity, overview: PRDSection) -> str:
        overview_text = safe_str(overview.content, "")
        if snapshot.product_purpose_known or ("repository intelligence" in overview_text.lower()) or safe_str(overview.confidence, "low") == "high":
            return safe_str(overview.content, "Project goal could not be determined from the analyzed evidence.")
        frontend_stack = safe_join(snapshot.frontend_frameworks or snapshot.framework_names)
        backend_stack = safe_join(snapshot.backend_frameworks or snapshot.framework_names)
        if snapshot.project_type == "frontend":
            stack_text = f" built with {frontend_stack}" if frontend_stack else ""
            return f"This project is organized around a frontend interface{stack_text}. It coordinates the user-facing experience, interaction flow, and supporting application behavior."
        if snapshot.project_type == "fullstack":
            stack_parts = [part for part in [frontend_stack, backend_stack] if part]
            stack_text = f" built with {' and '.join(stack_parts[:2])}" if stack_parts else ""
            return f"This project is organized as a fullstack application{stack_text}. It connects the interface, application logic, and data flow into a coherent workflow."
        stack_text = f" built with {backend_stack}" if backend_stack else ""
        if snapshot.repo_type == "cli_tool":
            return f"This project is organized around a command-line workflow{stack_text}. It coordinates terminal-driven actions, execution steps, and supporting logic in a maintainable structure."
        if snapshot.repo_type in {"documentation", "curriculum", "knowledge_base"}:
            return f"This project is organized around structured reference material{stack_text}. It centralizes documentation, learning content, or curated knowledge into a readable workflow."
        if snapshot.repo_type in {"dataset", "design_assets"}:
            return f"This project is organized around content delivery and supporting assets{stack_text}. It packages the repository's source material into a structured distribution workflow."
        return f"This project is organized around backend API functionality{stack_text}. It concentrates request handling, service logic, and data operations within a maintainable service layer."
