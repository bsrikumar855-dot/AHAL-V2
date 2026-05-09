from __future__ import annotations

import os
import re
from typing import Iterable

from app.docs.models import DocEvidence
from app.docs.utils.production_text import clean_list, clean_sentence, summarize_stack
from app.docs.utils.section_utils import safe_str
from app.intelligence.intelligence_engine import IntelligenceEngine
from app.onboarding.models import OnboardingReport, OnboardingStep
from app.testing import TestGapDetector
from app.utils.ignored_paths import is_ignored_path


_AUDIENCES = {"new_engineer", "frontend", "backend", "qa", "devops"}
_READING_WEIGHTS = {
    "docs": 4,
    "entry": 5,
    "api": 5,
    "services": 5,
    "models": 3,
    "workflow": 3,
    "config": 2,
    "tests": 2,
    "risks": 1,
}


class OnboardingGenerator:
    def generate(
        self,
        session_id,
        scan_result,
        intelligence_result=None,
        graph_result=None,
        prd_result=None,
        audience="new_engineer",
        time_budget_minutes=30,
    ) -> OnboardingReport:
        audience = safe_str(audience, "new_engineer").lower() or "new_engineer"
        if audience not in _AUDIENCES:
            raise ValueError("Unsupported audience. Allowed: new_engineer, frontend, backend, qa, devops")
        budget = max(1, int(time_budget_minutes or 30))

        if intelligence_result is None:
            intelligence_result = IntelligenceEngine().analyze(
                scan_result=scan_result,
                session_id=session_id,
                include_llm_explanation=False,
            )

        contents = getattr(scan_result, "contents", {}) or {}
        if not isinstance(contents, dict):
            contents = {}

        all_paths = self._all_paths(scan_result, contents)
        readme_files = [path for path in all_paths if self._is_doc_path(path)]
        entry_points = self._entry_points(intelligence_result, all_paths)
        api_routes = self._api_routes(intelligence_result)
        service_files = self._service_files(intelligence_result, all_paths)
        model_files = self._model_files(intelligence_result, all_paths)
        workflow_files, workflow_descriptions = self._workflows(intelligence_result, graph_result, all_paths)
        config_files = self._config_files(all_paths)
        test_files = self._test_files(all_paths)
        critical_modules = self._critical_modules(intelligence_result, prd_result, all_paths, audience)
        important_apis = self._important_apis(intelligence_result, prd_result)
        test_gap_result = self._test_gap_result(session_id, scan_result, intelligence_result)
        gotchas = self._gotchas(
            intelligence_result=intelligence_result,
            graph_result=graph_result,
            prd_result=prd_result,
            test_gap_result=test_gap_result,
            scan_result=scan_result,
            entry_points=entry_points,
            config_files=config_files,
            api_routes=api_routes,
            all_paths=all_paths,
        )
        safe_first_tasks = self._safe_first_tasks(test_gap_result, readme_files, important_apis, config_files, service_files)
        avoid_first = self._avoid_first(all_paths, critical_modules)
        reading_order = self._reading_order(
            audience=audience,
            budget=budget,
            readme_files=readme_files,
            entry_points=entry_points,
            api_routes=api_routes,
            service_files=service_files,
            model_files=model_files,
            workflow_files=workflow_files,
            config_files=config_files,
            test_files=test_files,
            gotchas=gotchas,
        )
        project_context = self._project_context(intelligence_result, prd_result, entry_points, api_routes, workflow_descriptions)
        summary = self._summary(audience, project_context, reading_order, gotchas, important_apis)
        warnings = self._warnings(intelligence_result, graph_result, prd_result, test_gap_result)
        confidence = self._confidence(intelligence_result, reading_order, gotchas)
        evidence_count = sum(len(step.evidence) for step in reading_order)
        evidence_count += sum(len(item.evidence) for item in getattr(test_gap_result, "gaps", [])[:5]) if test_gap_result else 0

        return OnboardingReport(
            session_id=session_id,
            audience=audience,
            time_budget_minutes=budget,
            summary=summary,
            project_context=project_context,
            reading_order=reading_order,
            key_entry_points=clean_list(entry_points, max_items=12),
            critical_modules=clean_list(critical_modules, max_items=12),
            important_apis=clean_list(important_apis, max_items=12),
            main_workflows=clean_list(workflow_descriptions, max_items=12),
            gotchas=clean_list(gotchas, max_items=12),
            safe_first_tasks=clean_list(safe_first_tasks, max_items=8),
            avoid_first=clean_list(avoid_first, max_items=8),
            confidence=confidence,
            warnings=clean_list(warnings, max_items=12),
            evidence_count=evidence_count,
        )

    def _all_paths(self, scan_result, contents: dict[str, str]) -> list[str]:
        file_paths = [str(getattr(item, "path", "") or "") for item in getattr(scan_result, "files", []) or []]
        merged = sorted({path for path in [*file_paths, *contents.keys()] if path and not is_ignored_path(path)})
        return merged

    def _entry_points(self, intelligence_result, all_paths: list[str]) -> list[str]:
        rows = []
        for item in getattr(intelligence_result, "entry_points", []) or []:
            path = safe_str(getattr(item, "file", ""), "")
            if path and not is_ignored_path(path):
                entry_type = safe_str(getattr(item, "type", ""), "unknown")
                framework = safe_str(getattr(item, "framework", ""), "")
                detail = f"{path} - {entry_type} entry point"
                if framework:
                    detail += f" ({framework})"
                rows.append(detail)
        inferred = []
        for path in all_paths:
            lowered = path.lower()
            if lowered.endswith(("main.py", "app.py", "server.js", "server.ts", "index.ts", "index.js", "src/main.tsx", "src/main.jsx", "src/pages/_app.tsx")):
                inferred.append(f"{path} - inferred entry point")
        return clean_list(rows + inferred, max_items=8)

    def _api_routes(self, intelligence_result) -> list[str]:
        rows = []
        for endpoint in getattr(intelligence_result, "api_endpoints", []) or []:
            method = safe_str(getattr(endpoint, "method", ""), "").upper()
            route = safe_str(getattr(endpoint, "path", ""), "")
            file_path = safe_str(getattr(endpoint, "file", ""), "")
            if method and route and file_path and not is_ignored_path(file_path):
                rows.append(f"{method} {route} ({file_path})")
        return rows[:12]

    def _service_files(self, intelligence_result, all_paths: list[str]) -> list[str]:
        rows = []
        for module in getattr(intelligence_result, "modules", []) or []:
            category = safe_str(getattr(module, "category", ""), "").lower()
            for path in getattr(module, "files", []) or []:
                normalized = safe_str(path, "")
                if normalized and not is_ignored_path(normalized) and category in {"service", "worker", "auth", "utility"}:
                    rows.append(normalized)
        if rows:
            return clean_list(rows, max_items=10)
        fallback = [path for path in all_paths if any(token in path.lower() for token in ("/service", "\\service", "/worker", "\\worker", "/auth", "\\auth", "pipeline", "indexer"))]
        return fallback[:10]

    def _model_files(self, intelligence_result, all_paths: list[str]) -> list[str]:
        rows = []
        for module in getattr(intelligence_result, "modules", []) or []:
            category = safe_str(getattr(module, "category", ""), "").lower()
            for path in getattr(module, "files", []) or []:
                normalized = safe_str(path, "")
                if normalized and not is_ignored_path(normalized) and category in {"model", "schema", "database"}:
                    rows.append(normalized)
        if rows:
            return clean_list(rows, max_items=10)
        fallback = [path for path in all_paths if any(token in path.lower() for token in ("model", "schema", "migration", "db", "database"))]
        return fallback[:10]

    def _workflows(self, intelligence_result, graph_result, all_paths: list[str]) -> tuple[list[str], list[str]]:
        files = []
        descriptions = []
        for step in getattr(getattr(intelligence_result, "workflow", None), "steps", []) or []:
            source = clean_sentence(f"{safe_str(getattr(step, 'source', ''), '')} -> {safe_str(getattr(step, 'action', ''), '')} -> {safe_str(getattr(step, 'target', ''), '')}")
            descriptions.append(source)
            evidence = getattr(step, "evidence", []) or []
            for item in evidence:
                path = safe_str(getattr(item, "file", ""), "")
                if path and not is_ignored_path(path):
                    files.append(path)
        if not descriptions and graph_result is not None:
            for edge in getattr(graph_result, "edges", []) or []:
                if safe_str(getattr(edge, "type", ""), "") in {"routes_to", "part_of_workflow", "calls"}:
                    descriptions.append(clean_sentence(f"{safe_str(getattr(edge, 'label', ''), '')} workflow evidence detected"))
                    for item in getattr(edge, "evidence", [])[:1]:
                        path = safe_str(getattr(item, "file", ""), "")
                        if path and not is_ignored_path(path):
                            files.append(path)
        if not descriptions:
            for path in all_paths:
                lowered = path.lower()
                if any(token in lowered for token in ("workflow", "pipeline", "worker", "jobs", "tasks")):
                    descriptions.append(clean_sentence(f"Read {path} to understand a core project workflow"))
                    files.append(path)
        return clean_list(files, max_items=10), clean_list(descriptions, max_items=10)

    def _config_files(self, all_paths: list[str]) -> list[str]:
        return [
            path for path in all_paths
            if path.lower().endswith((
                ".env.example", "docker-compose.yml", "docker-compose.yaml", "dockerfile",
                "requirements.txt", "pyproject.toml", "package.json", "makefile", ".yml", ".yaml"
            )) or any(token in path.lower() for token in ("config", "settings", "deploy", "k8s", "helm", "compose"))
        ][:12]

    def _test_files(self, all_paths: list[str]) -> list[str]:
        rows = []
        for path in all_paths:
            lowered = path.replace("\\", "/").lower()
            name = os.path.basename(lowered)
            if "/tests/" in f"/{lowered}" or "/__tests__/" in f"/{lowered}" or name.startswith("test_") or name.endswith((".spec.ts", ".spec.tsx", ".test.ts", ".test.tsx", "_test.py", ".test.js", ".spec.js")):
                rows.append(path)
        return rows[:12]

    def _critical_modules(self, intelligence_result, prd_result, all_paths: list[str], audience: str) -> list[str]:
        rows = []
        preferred = {
            "backend": {"api", "service", "database", "auth", "model", "schema"},
            "frontend": {"ui", "api", "service", "schema"},
            "qa": {"api", "service", "worker", "auth", "database"},
            "devops": {"config", "worker", "database", "service"},
            "new_engineer": {"api", "service", "database", "auth", "config", "worker", "model"},
        }[audience]
        for module in getattr(intelligence_result, "modules", []) or []:
            category = safe_str(getattr(module, "category", ""), "").lower()
            if category not in preferred:
                continue
            files = [safe_str(path, "") for path in getattr(module, "files", []) or []]
            files = [path for path in files if path and not is_ignored_path(path)]
            if not files:
                continue
            rows.append(f"{safe_str(getattr(module, 'name', ''), os.path.basename(files[0]))} ({category}) - {files[0]}")
        if prd_result is not None:
            for module in getattr(prd_result, "modules", []) or []:
                if safe_str(getattr(module, "category", ""), "").lower() in preferred:
                    files = [path for path in getattr(module, "files", []) or [] if path and not is_ignored_path(path)]
                    if files:
                        rows.append(f"{safe_str(getattr(module, 'name', ''), os.path.basename(files[0]))} ({safe_str(getattr(module, 'category', ''), 'unknown')}) - {files[0]}")
        if rows:
            return clean_list(rows, max_items=12)
        fallback = [path for path in all_paths if any(token in path.lower() for token in ("api", "service", "model", "schema", "config", "worker", "auth"))]
        return clean_list(fallback, max_items=12)

    def _important_apis(self, intelligence_result, prd_result) -> list[str]:
        rows = []
        for endpoint in getattr(intelligence_result, "api_endpoints", []) or []:
            method = safe_str(getattr(endpoint, "method", ""), "").upper()
            route = safe_str(getattr(endpoint, "path", ""), "")
            file_path = safe_str(getattr(endpoint, "file", ""), "")
            if method and route:
                rows.append(f"{method} {route} - defined in {file_path}" if file_path else f"{method} {route}")
        for endpoint in getattr(prd_result, "api_endpoints", []) if prd_result is not None else []:
            method = safe_str(getattr(endpoint, "method", ""), "").upper()
            route = safe_str(getattr(endpoint, "path", ""), "")
            file_path = safe_str(getattr(endpoint, "source_file", ""), "")
            if method and route:
                rows.append(f"{method} {route} - defined in {file_path}" if file_path else f"{method} {route}")
        return clean_list(rows, max_items=12)

    def _test_gap_result(self, session_id: str, scan_result, intelligence_result):
        try:
            return TestGapDetector().detect(
                session_id=session_id,
                scan_result=scan_result,
                intelligence_result=intelligence_result,
                include_low_priority=False,
            )
        except Exception:
            return None

    def _gotchas(
        self,
        intelligence_result,
        graph_result,
        prd_result,
        test_gap_result,
        scan_result,
        entry_points: list[str],
        config_files: list[str],
        api_routes: list[str],
        all_paths: list[str],
    ) -> list[str]:
        gotchas = []
        if test_gap_result is not None:
            for gap in getattr(test_gap_result, "gaps", [])[:4]:
                gotchas.append(clean_sentence(f"{gap.target} in {gap.path}: {gap.reason}"))
        if api_routes and not any(safe_str(getattr(module, "category", ""), "").lower() == "auth" for module in getattr(intelligence_result, "modules", []) or []):
            gotchas.append("Public API routes are present, but no clear auth/session module was detected from the analyzed evidence.")
        if (api_routes or entry_points) and not getattr(intelligence_result, "databases", []):
            gotchas.append("Runtime entry points and APIs were detected, but database/storage evidence is limited or absent in the scan.")
        if not any("docker" in path.lower() or "compose" in path.lower() for path in config_files):
            gotchas.append("Deployment configuration evidence looks limited because no Docker or compose files were detected.")
        for warning in getattr(intelligence_result, "warnings", []) or []:
            gotchas.append(clean_sentence(warning))
        for warning in getattr(graph_result, "warnings", []) if graph_result is not None else []:
            gotchas.append(clean_sentence(warning))
        for warning in getattr(prd_result, "warnings", []) if prd_result is not None else []:
            gotchas.append(clean_sentence(warning))
        for path in all_paths:
            if path in getattr(scan_result, "contents", {}) and self._line_count(getattr(scan_result, "contents", {}).get(path, "")) >= 200:
                if path.endswith(("main.py", "app.py", "server.js", "server.ts")) or "/api/" in path.replace("\\", "/").lower():
                    gotchas.append(f"{path} is a large entrypoint or route file, so change it carefully after you understand its call paths.")
                    break
        return clean_list(gotchas, max_items=10)

    def _safe_first_tasks(self, test_gap_result, readme_files, important_apis, config_files, service_files) -> list[str]:
        tasks = []
        if readme_files:
            tasks.append(f"Improve or clarify {readme_files[0]} with setup and architecture notes.")
        if test_gap_result is not None and getattr(test_gap_result, "gaps", []):
            first_gap = test_gap_result.gaps[0]
            tasks.append(f"Add tests around {first_gap.target} in {first_gap.path}.")
        if important_apis:
            tasks.append("Document one important API contract with request, response, and failure cases.")
        if service_files:
            tasks.append(f"Add validation or failure-path tests for {service_files[0]}.")
        if config_files:
            tasks.append("Improve deployment or environment documentation for the current runtime setup.")
        tasks.append("Clean up one small isolated module only after confirming it is not on a critical startup path.")
        return tasks

    def _avoid_first(self, all_paths: list[str], critical_modules: list[str]) -> list[str]:
        rows = []
        auth_paths = [path for path in all_paths if any(token in path.lower() for token in ("auth", "session", "token"))]
        if auth_paths:
            rows.append(f"Auth/session logic ({auth_paths[0]}).")
        db_paths = [path for path in all_paths if any(token in path.lower() for token in ("database", "schema", "migration", "model", "db"))]
        if db_paths:
            rows.append(f"Database or schema changes ({db_paths[0]}).")
        scan_paths = [path for path in all_paths if any(token in path.lower() for token in ("scanner", "scan_worker", "streaming_scanner"))]
        if scan_paths:
            rows.append(f"Core scan pipeline ({scan_paths[0]}).")
        validation_paths = [path for path in all_paths if any(token in path.lower() for token in ("validation", "schema", "validator"))]
        if validation_paths:
            rows.append(f"Strict validation logic ({validation_paths[0]}).")
        export_paths = [path for path in all_paths if any(token in path.lower() for token in ("pdf", "export", "latex"))]
        if export_paths:
            rows.append(f"PDF/export pipeline ({export_paths[0]}).")
        mcp_paths = [path for path in all_paths if "/mcp/" in path.replace("\\", "/").lower()]
        if mcp_paths:
            rows.append(f"MCP tool contract ({mcp_paths[0]}).")
        if not rows and critical_modules:
            rows.append(f"Any critical module in the first pass, starting with {critical_modules[0]}.")
        return rows

    def _reading_order(
        self,
        audience: str,
        budget: int,
        readme_files: list[str],
        entry_points: list[str],
        api_routes: list[str],
        service_files: list[str],
        model_files: list[str],
        workflow_files: list[str],
        config_files: list[str],
        test_files: list[str],
        gotchas: list[str],
    ) -> list[OnboardingStep]:
        audience_titles = {
            "new_engineer": {
                "docs": "Start With README And Docs",
                "entry": "Trace The Main Entry Points",
                "api": "Read The Public API Surface",
                "services": "Follow Core Business Logic",
                "models": "Understand Schemas And Storage",
                "workflow": "Map The Main Workflows",
                "config": "Check Runtime And Deployment Config",
                "tests": "See How The Project Is Verified",
                "risks": "Finish With Risks And Gaps",
            },
            "backend": {
                "docs": "Skim Setup And Product Context",
                "entry": "Read Backend Startup Files",
                "api": "Study API Routes First",
                "services": "Trace Service And Auth Logic",
                "models": "Review Database And Schemas",
                "workflow": "Trace Request And Worker Flows",
                "config": "Inspect Runtime Configuration",
                "tests": "Read Backend Tests",
                "risks": "Note High-Risk Areas",
            },
            "frontend": {
                "docs": "Skim Product And Docs",
                "entry": "Find Frontend Entrypoints",
                "api": "Understand Backend Contract",
                "services": "Read State And Data Flow Files",
                "models": "Review Shared Schemas",
                "workflow": "Trace User-Facing Flows",
                "config": "Check Frontend Runtime Config",
                "tests": "Inspect UI Or Contract Tests",
                "risks": "Note Integration Risks",
            },
            "qa": {
                "docs": "Skim Scope And Setup",
                "entry": "Find Core Execution Paths",
                "api": "Inventory Important Endpoints",
                "services": "Identify Risky Business Logic",
                "models": "Review Validation Boundaries",
                "workflow": "Map Testable Workflows",
                "config": "Check Env And Deployment Surfaces",
                "tests": "Read Existing Test Coverage",
                "risks": "Start With Test Gaps And Risks",
            },
            "devops": {
                "docs": "Skim Project And Setup Docs",
                "entry": "Find Runtime Entry Points",
                "api": "Identify Health And Public APIs",
                "services": "Note Background Services",
                "models": "Check Stateful Components",
                "workflow": "Map Runtime Workflows",
                "config": "Read Docker And Config First",
                "tests": "Inspect Operational Tests",
                "risks": "Review Deployment Risks",
            },
        }[audience]

        descriptors = [
            ("docs", readme_files, "Use these files to understand what the project is and how it is expected to run.", "They provide the fastest orientation before diving into code.", "high"),
            ("entry", [self._strip_detail(item) for item in entry_points], "Read the startup path next so you know how execution begins.", "Entry points show where requests, jobs, or app boot flow starts.", "high"),
            ("api", [self._path_from_api(item) for item in api_routes], "Study the externally visible API surface and route handlers.", "This tells you which contracts other systems or clients depend on.", "high"),
            ("services", service_files, "Follow the service and business-logic layer after you know the routes.", "This is usually where the core behavior and decisions live.", "high"),
            ("models", model_files, "Review data models, schemas, and storage-facing code.", "These files explain validation boundaries and persistence assumptions.", "medium"),
            ("workflow", workflow_files, "Read workflow and pipeline files to connect modules into end-to-end behavior.", "They show how requests, jobs, or state transitions move through the system.", "medium"),
            ("config", config_files, "Check runtime, deployment, and environment configuration.", "This helps you avoid missing setup assumptions during onboarding.", "medium"),
            ("tests", test_files, "Read tests to see expected behavior, examples, and safety rails.", "Tests often explain intended behavior faster than implementation alone.", "medium"),
            ("risks", [], "End with explicit risks, warnings, and test gaps.", "This helps you avoid changing unstable areas too early.", "low"),
        ]

        available = []
        for key, files, description, reason, priority in descriptors:
            if key == "risks" or files:
                available.append((key, files, description, reason, priority))

        total_weight = sum(_READING_WEIGHTS[key] for key, *_ in available)
        remaining = budget
        steps = []
        for index, (key, files, description, reason, priority) in enumerate(available, start=1):
            if index == len(available):
                minutes = max(1, remaining)
            else:
                minutes = max(1, round((budget * _READING_WEIGHTS[key]) / max(total_weight, 1)))
                remaining -= minutes
                if remaining < (len(available) - index):
                    minutes = max(1, minutes + remaining - (len(available) - index))
                    remaining = len(available) - index
            evidence = self._step_evidence(key, files[:3], gotchas[:2] if key == "risks" else [])
            steps.append(
                OnboardingStep(
                    title=audience_titles[key],
                    description=clean_sentence(description),
                    files_to_read=clean_list(files, max_items=5),
                    reason=clean_sentence(reason),
                    estimated_minutes=max(1, minutes),
                    priority=priority,
                    evidence=evidence,
                )
            )
        return steps

    def _project_context(self, intelligence_result, prd_result, entry_points: list[str], api_routes: list[str], workflow_descriptions: list[str]) -> str:
        project_type = safe_str(getattr(intelligence_result, "project_type", ""), "")
        architecture = safe_str(getattr(getattr(intelligence_result, "architecture", None), "type", ""), "")
        stack = summarize_stack(
            getattr(intelligence_result, "frameworks", []) or [],
            getattr(intelligence_result, "databases", []) or [],
            getattr(intelligence_result, "languages", []) or [],
        )
        overview = ""
        if prd_result is not None:
            overview = safe_str(getattr(getattr(prd_result, "overview", None), "content", ""), "")
        if overview:
            return clean_sentence(f"{overview} Detected architecture: {architecture or project_type or 'unknown'}. Key startup files: {', '.join(self._strip_detail(item) for item in entry_points[:2]) or 'limited evidence'}. Important APIs: {', '.join(api_routes[:2]) or 'limited evidence'}.")
        parts = [
            f"The codebase is organized as a {architecture or project_type or 'software'} project.",
        ]
        if stack:
            parts.append(f"Detected stack: {stack}.")
        if workflow_descriptions:
            parts.append(f"Main workflow evidence starts with {workflow_descriptions[0]}.")
        if api_routes:
            parts.append(f"Public API surface includes {api_routes[0]}.")
        return clean_sentence(" ".join(parts))

    def _summary(self, audience: str, project_context: str, reading_order: list[OnboardingStep], gotchas: list[str], important_apis: list[str]) -> str:
        first_step = reading_order[0].title if reading_order else "Start with the highest-confidence docs and entry points"
        audience_focus = {
            "new_engineer": "balanced first-pass overview",
            "backend": "API, services, and storage behavior",
            "frontend": "UI entrypoints, API surface, and contract boundaries",
            "qa": "workflow risk, endpoint coverage, and missing tests",
            "devops": "runtime, config, health, and deployment dependencies",
        }[audience]
        parts = [
            f"This onboarding guide is tuned for a {audience_focus}.",
            f"Start with {first_step.lower()}.",
        ]
        if important_apis:
            parts.append(f"One important API to understand early is {important_apis[0]}.")
        if gotchas:
            parts.append(f"Watch for this early risk: {gotchas[0]}")
        return clean_sentence(" ".join(parts))

    def _warnings(self, intelligence_result, graph_result, prd_result, test_gap_result) -> list[str]:
        warnings = []
        warnings.extend(getattr(intelligence_result, "warnings", []) or [])
        warnings.extend(getattr(graph_result, "warnings", []) if graph_result is not None else [])
        warnings.extend(getattr(prd_result, "warnings", []) if prd_result is not None else [])
        warnings.extend(getattr(test_gap_result, "warnings", []) if test_gap_result is not None else [])
        return [clean_sentence(item) for item in clean_list(warnings, max_items=12)]

    def _confidence(self, intelligence_result, reading_order: list[OnboardingStep], gotchas: list[str]) -> str:
        evidence_count = sum(len(step.evidence) for step in reading_order)
        if evidence_count >= 8 and getattr(intelligence_result, "api_endpoints", []) and getattr(intelligence_result, "entry_points", []):
            return "high"
        if evidence_count >= 4 or gotchas:
            return "medium"
        return "low"

    def _step_evidence(self, key: str, files: list[str], gotchas: list[str]) -> list[DocEvidence]:
        evidence = []
        for path in files:
            if not path or is_ignored_path(path):
                continue
            evidence.append(
                DocEvidence(
                    source_type="file",
                    source_id=path,
                    file=path,
                    reason=clean_sentence(f"AHAL selected {path} as {key} onboarding evidence"),
                    snippet=None,
                    confidence="medium",
                )
            )
        for item in gotchas:
            evidence.append(
                DocEvidence(
                    source_type="analysis",
                    source_id=key,
                    file=None,
                    reason=clean_sentence(item),
                    snippet=None,
                    confidence="low",
                )
            )
        return evidence[:4]

    def _is_doc_path(self, path: str) -> bool:
        lowered = path.lower()
        name = os.path.basename(lowered)
        return name.startswith("readme") or lowered.endswith((".md", ".rst")) or "/docs/" in f"/{lowered.replace('\\', '/')}"

    def _strip_detail(self, value: str) -> str:
        return safe_str(value.split(" - ", 1)[0] if " - " in value else value, "")

    def _path_from_api(self, value: str) -> str:
        match = re.search(r"\(([^)]+)\)$", value)
        if match:
            return match.group(1)
        return value

    def _line_count(self, content: str) -> int:
        return len(str(content or "").splitlines())


def render_onboarding_markdown(report: OnboardingReport) -> str:
    lines = [
        "# New Engineer Onboarding Guide",
        "",
        report.summary,
        "",
        "## Project Context",
        "",
        report.project_context,
        "",
        "## First 30-Minute Reading Plan",
        "",
    ]
    for index, step in enumerate(report.reading_order, start=1):
        lines.append(f"{index}. {step.title} ({step.estimated_minutes} min)")
        lines.append(f"   {step.description}")
        if step.files_to_read:
            lines.append(f"   Files: {', '.join(step.files_to_read)}")
        lines.append(f"   Why: {step.reason}")
    sections = [
        ("Key Entry Points", report.key_entry_points),
        ("Critical Modules", report.critical_modules),
        ("Important APIs", report.important_apis),
        ("Main Workflows", report.main_workflows),
        ("Gotchas", report.gotchas),
        ("Safe First Tasks", report.safe_first_tasks),
        ("Avoid First", report.avoid_first),
    ]
    for title, items in sections:
        lines.extend(["", f"## {title}", ""])
        if items:
            lines.extend([f"- {item}" for item in items])
        else:
            lines.append("- Insufficient evidence from codebase.")
    lines.extend(["", "## Evidence Notes", ""])
    if report.reading_order:
        for step in report.reading_order:
            for item in step.evidence:
                note = item.file or item.source_id
                lines.append(f"- {step.title}: {note} - {item.reason}")
    else:
        lines.append("- Insufficient evidence from codebase.")
    return "\n".join(lines).strip() + "\n"
