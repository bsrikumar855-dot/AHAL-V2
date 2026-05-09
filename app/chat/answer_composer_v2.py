from __future__ import annotations

from app.chat.constants import INSUFFICIENT_EVIDENCE_MESSAGE
from app.chat.models import ChatAnswer, ChatAnswerSection, ChatContextPack
from app.chat.utils import build_followups, evidence_display_label, filter_chat_evidence, sanitize_chat_answer, sanitize_chat_path, sanitize_chat_text
from app.intelligence.output_guard import CanonicalOutputGuard
from app.intelligence.repository_type_classifier import is_documentation_repo_type, is_package_like_repo_type


class AnswerComposerV2:
    def compose(self, question, intent, context_pack: ChatContextPack, llm_result=None) -> ChatAnswer:
        if llm_result:
            return self._compose_from_llm(intent, context_pack, llm_result)
        return self._compose_deterministic(question, intent, context_pack)

    def _compose_deterministic(self, question, intent, context_pack: ChatContextPack) -> ChatAnswer:
        sections: list[ChatAnswerSection] = []
        intent_name = intent.intent if hasattr(intent, "intent") else str(intent)
        evidence_limit = 5 if intent_name == "onboarding_question" else 6
        evidence = filter_chat_evidence(context_pack.selected_evidence, limit=evidence_limit)
        evidence_ids = list(context_pack.evidence_map.keys())[: min(3, len(context_pack.evidence_map))]
        confidence = context_pack.confidence

        if intent_name != "onboarding_question" and not evidence and not context_pack.relevant_apis and not context_pack.relevant_modules:
            return sanitize_chat_answer(ChatAnswer(
                answer=INSUFFICIENT_EVIDENCE_MESSAGE,
                short_answer="The analyzed evidence does not fully specify this.",
                confidence="low",
                warnings=list(context_pack.warnings),
                insufficient_context=True,
                suggested_followups=build_followups("general_repo_question"),
                intent=intent_name,
                used_llm=False,
                fallback_used=True,
            ))

        direct_answer = self._direct_answer(question, intent_name, context_pack)
        followup_intent = intent_name
        if intent_name == "project_overview":
            sections.extend(self._overview_sections(context_pack))
        elif intent_name == "api_explanation":
            sections.extend(self._api_sections(context_pack))
        elif intent_name == "architecture_explanation":
            sections.extend(self._architecture_sections(context_pack))
        elif intent_name == "workflow_explanation":
            sections.extend(self._workflow_sections(context_pack))
        elif intent_name == "test_gap_question":
            sections.extend(self._test_gap_sections(context_pack))
        elif intent_name == "onboarding_question":
            sections.extend(self._onboarding_sections(context_pack))
        elif intent_name in {"file_explanation", "module_explanation"}:
            sections.extend(self._module_sections(context_pack, include_files=True))
        elif intent_name == "risk_analysis":
            sections.extend(self._risk_sections(context_pack))
        elif intent_name == "how_to_run":
            sections.extend(self._run_sections(context_pack))
        elif intent_name == "what_remaining":
            sections.extend(self._remaining_sections(context_pack))
        else:
            sections.extend(self._overview_sections(context_pack))
            if intent_name == "general_repo_question":
                followup_intent = "project_overview"

        answer_parts = [direct_answer]
        for section in sections:
            block = [section.title]
            if section.content:
                block.append(section.content)
            if section.bullets:
                block.extend(f"- {item}" for item in section.bullets)
            answer_parts.append("\n".join(block))

        warnings = list(dict.fromkeys([sanitize_chat_text(item) for item in context_pack.warnings if sanitize_chat_text(item)]))
        if not warnings and confidence != "high":
            warnings.append("The analyzed evidence does not fully specify every detail, so some points remain conservative.")

        answer_text = "\n\n".join(part for part in answer_parts if part).strip()
        canonical = context_pack.canonical_intelligence
        answer_text = CanonicalOutputGuard.sanitize_text(answer_text, canonical)
        short_answer = CanonicalOutputGuard.sanitize_text(direct_answer, canonical)
        sanitized_sections = [
            ChatAnswerSection(
                title=CanonicalOutputGuard.sanitize_text(section.title, canonical),
                content=CanonicalOutputGuard.sanitize_text(section.content, canonical),
                bullets=[CanonicalOutputGuard.sanitize_text(item, canonical) for item in section.bullets],
                evidence_ids=section.evidence_ids,
            )
            for section in sections
        ]

        return sanitize_chat_answer(ChatAnswer(
            answer=answer_text,
            short_answer=short_answer,
            sections=sanitized_sections,
            confidence=confidence,
            evidence=evidence,
            related_files=sorted({ev.file for ev in evidence if ev.file}),
            related_nodes=[item["name"] for item in context_pack.relevant_modules[:4] if item.get("name")],
            warnings=warnings,
            insufficient_context=False,
            suggested_followups=build_followups(followup_intent, [item.get("path", "") for item in context_pack.relevant_apis if item.get("path")]),
            intent=intent_name,
            used_llm=False,
            fallback_used=True,
        ))

    def _compose_from_llm(self, intent, context_pack: ChatContextPack, llm_result) -> ChatAnswer:
        canonical = context_pack.canonical_intelligence
        sections = []
        for item in llm_result.get("sections", []) or []:
            sections.append(
                ChatAnswerSection(
                    title=CanonicalOutputGuard.sanitize_text(sanitize_chat_text(item.get("title"), "Answer"), canonical),
                    content=CanonicalOutputGuard.sanitize_text(sanitize_chat_text(item.get("content"), ""), canonical),
                    bullets=[CanonicalOutputGuard.sanitize_text(sanitize_chat_text(bullet), canonical) for bullet in item.get("bullets", []) if sanitize_chat_text(bullet)],
                    evidence_ids=[str(ev).replace("[", "").replace("]", "") for ev in item.get("evidence_ids", []) if str(ev).strip()],
                )
            )
        return sanitize_chat_answer(ChatAnswer(
            answer=CanonicalOutputGuard.sanitize_text(sanitize_chat_text(llm_result.get("answer"), INSUFFICIENT_EVIDENCE_MESSAGE), canonical),
            short_answer=CanonicalOutputGuard.sanitize_text(sanitize_chat_text(llm_result.get("short_answer"), ""), canonical),
            sections=sections,
            confidence=context_pack.confidence,
            evidence=filter_chat_evidence(context_pack.selected_evidence, limit=5 if (intent.intent if hasattr(intent, "intent") else str(intent)) == "onboarding_question" else 6),
            related_files=sorted({ev.file for ev in context_pack.selected_evidence if ev.file}),
            related_nodes=[item["name"] for item in context_pack.relevant_modules[:4] if item.get("name")],
            warnings=[sanitize_chat_text(item) for item in llm_result.get("warnings", []) if sanitize_chat_text(item)],
            insufficient_context=False,
            suggested_followups=[sanitize_chat_text(item) for item in llm_result.get("suggested_followups", []) if sanitize_chat_text(item)],
            intent=intent.intent if hasattr(intent, "intent") else str(intent),
            used_llm=True,
            fallback_used=False,
        ))

    def _direct_answer(self, question: str, intent_name: str, context_pack: ChatContextPack) -> str:
        identity_summary = context_pack.project_identity.get("summary") or ""
        canonical = context_pack.canonical_intelligence
        architecture_type = context_pack.architecture_summary.get("type", "unknown")
        uncertainty = self._uncertainty_sentence(context_pack)
        normalized_question = str(question or "").strip().lower()
        repo_type = str(getattr(canonical, "repo_type", "") if canonical is not None else "").lower()
        def _polish_summary(text: str) -> str:
            cleaned = str(text or "").strip()
            if "appears to be" in cleaned.lower():
                cleaned = cleaned.replace("appears to be", "is organized as")
            if cleaned and not cleaned.endswith((".", "!", "?")):
                cleaned += "."
            return cleaned
        if intent_name == "project_goal":
            canonical_why = getattr(canonical, "why", "") if canonical is not None else ""
            if "why" in normalized_question and canonical_why:
                return canonical_why
            canonical_summary = getattr(canonical, "product_summary", "") if canonical is not None else ""
            if canonical_summary:
                return canonical_summary
            if identity_summary:
                return _polish_summary(identity_summary)
            return "The analyzed evidence supports a developer-facing code intelligence workflow that centralizes repository understanding, analysis, and follow-up actions."
        if intent_name in {"project_overview", "general_repo_question"}:
            canonical_summary = getattr(canonical, "product_summary", "") if canonical is not None else ""
            if canonical_summary:
                if uncertainty and uncertainty.lower() not in canonical_summary.lower():
                    return f"{canonical_summary.rstrip('.')}." + f" {uncertainty}"
                return canonical_summary
            if identity_summary:
                identity_summary = _polish_summary(identity_summary)
                if uncertainty and uncertainty.lower() not in identity_summary.lower():
                    return f"{identity_summary.rstrip('.')}." + f" {uncertainty}"
                return identity_summary
            fallback = "This project is organized around detected APIs, modules, and service structure."
            if uncertainty:
                return f"{fallback} {uncertainty}"
            return fallback
        if intent_name == "what_is_built":
            if repo_type == "dataset":
                return "The repository contains dataset assets and supporting metadata rather than executable application features."
            completed = list(getattr(canonical, "completed", []) or [])
            if completed:
                titles = ", ".join(item.title for item in completed[:4])
                return f"This project already includes {titles}."
            return "This repo has detected implementation evidence, but the full built surface is only partially specified."
        if intent_name == "api_explanation":
            if is_documentation_repo_type(repo_type) and not context_pack.relevant_apis:
                return "No API endpoints were identified in the analyzed evidence. The repository is organized around documentation or curriculum content rather than an API service."
            if is_package_like_repo_type(repo_type) and not context_pack.relevant_apis:
                return "No HTTP API endpoints were identified. This appears to expose package/library APIs instead."
            if repo_type in {"dataset", "design_assets"} and not context_pack.relevant_apis:
                return "No API endpoints were identified in the analyzed evidence. The repository is organized around content distribution or asset delivery rather than an API service."
            if repo_type == "cli_tool" and not context_pack.relevant_apis:
                return "No HTTP API endpoints were identified. The repository is organized around command-line workflows rather than an API service."
            if context_pack.relevant_apis:
                api = context_pack.relevant_apis[0]
                return f"{api['method']} {api['path']} is a detected API endpoint in this project."
            return "The analyzed evidence shows API-related structure, but the requested endpoint is only partially specified."
        if intent_name == "architecture_explanation":
            if is_documentation_repo_type(repo_type):
                return "This repository is primarily documentation/curriculum content. No executable application architecture was confirmed from the analyzed evidence."
            if is_package_like_repo_type(repo_type):
                return "This repository is primarily organized as a reusable package/library surface rather than a standalone application architecture."
            if repo_type == "dataset":
                return "This repository is primarily a dataset and metadata distribution surface rather than an executable application architecture."
            return f"This project uses a {architecture_type} architecture based on the detected frameworks, modules, and entry points."
        if intent_name == "workflow_explanation":
            if repo_type == "cli_tool":
                return "The main workflow is command-line driven: a user runs a command, arguments are parsed, command logic executes, and results are returned in the terminal."
            if is_package_like_repo_type(repo_type):
                return "The main workflow is package consumption: a developer installs the package, imports its public APIs, and the library returns functionality inside another application."
            if repo_type == "dataset":
                return "The main workflow is content consumption: a consumer downloads the dataset, reviews its metadata/schema, and uses the files in analysis or training workflows."
            return "The main workflow can be explained from the detected entry points, APIs, and inferred execution steps."
        if intent_name == "test_gap_question":
            return "The highest-priority gaps are the areas where detected workflows lack corresponding test coverage evidence."
        if intent_name == "onboarding_question":
            return "Start with the project overview, then follow the main entry points, then inspect the API/workflow layer."
        if intent_name == "how_to_run":
            return "The safest way to run this project is to follow detected setup artifacts and entry points only where evidence exists."
        if intent_name == "risk_analysis":
            return "The main issues are the areas with important behavior but weaker validation, coverage, or workflow certainty."
        if intent_name in {"file_explanation", "module_explanation"}:
            return "The requested file or module can be explained from its detected role, related APIs, and nearby evidence."
        if intent_name == "what_remaining":
            remaining = list(getattr(canonical, "remaining", []) or [])
            if remaining:
                return "Remaining work includes " + ", ".join(item.title for item in remaining[:4]) + "."
            return "Remaining work centers on unresolved areas that should be confirmed from docs and tests."
        if identity_summary:
            return identity_summary
        return "This project is organized as a codebase with detected APIs, modules, and workflow evidence, while some details remain conservatively interpreted."

    def _overview_sections(self, context_pack: ChatContextPack) -> list[ChatAnswerSection]:
        sections: list[ChatAnswerSection] = []
        evidence_ids = list(context_pack.evidence_map.keys())[:3]
        canonical = context_pack.canonical_intelligence
        canonical_what = sanitize_chat_text(getattr(canonical, "what", ""), "")
        if canonical_what:
            sections.append(ChatAnswerSection(title="What it is", content=canonical_what, evidence_ids=evidence_ids))
        what_it_is_bits = []
        project_type = sanitize_chat_text(context_pack.project_identity.get("project_type"), "")
        frameworks = [sanitize_chat_text(item, "") for item in context_pack.project_identity.get("frameworks", [])[:4] if sanitize_chat_text(item, "")]
        domain = sanitize_chat_text(context_pack.project_identity.get("domain"), "")
        if domain:
            what_it_is_bits.append(f"Product domain: {domain}.")
        if project_type and project_type != "unknown":
            what_it_is_bits.append(f"Project type: {project_type}.")
        if frameworks:
            what_it_is_bits.append(f"Frameworks: {', '.join(frameworks)}.")
        if what_it_is_bits:
            title = "Project signals" if canonical_what else "What it is"
            sections.append(ChatAnswerSection(title=title, bullets=what_it_is_bits, evidence_ids=evidence_ids))

        architecture_bits = []
        architecture_type = sanitize_chat_text(context_pack.architecture_summary.get("type"), "")
        if architecture_type and architecture_type != "unknown":
            architecture_bits.append(f"Architecture type: {architecture_type}.")
        entry_points = [item for item in context_pack.architecture_summary.get("entry_points", [])[:3] if item]
        if entry_points:
            architecture_bits.append(f"Entry points: {', '.join(entry_points)}.")
        if context_pack.relevant_modules:
            architecture_bits.append(f"Modules: {', '.join(item['name'] for item in context_pack.relevant_modules[:4])}.")
        if architecture_bits:
            sections.append(ChatAnswerSection(title="Detected architecture", bullets=architecture_bits, evidence_ids=evidence_ids))

        if context_pack.relevant_apis:
            api_bullets = []
            for item in context_pack.relevant_apis[:4]:
                detail = f"{item['method']} {item['path']}"
                if item.get("handler"):
                    detail += f": {item['handler']}"
                api_bullets.append(detail)
            sections.append(ChatAnswerSection(title="Key API", bullets=api_bullets, evidence_ids=evidence_ids))

        uncertainty = self._uncertainty_sentence(context_pack)
        if uncertainty:
            sections.append(ChatAnswerSection(title="What is uncertain", content=uncertainty, evidence_ids=evidence_ids))
        return sections

    def _api_sections(self, context_pack: ChatContextPack) -> list[ChatAnswerSection]:
        sections = []
        if context_pack.relevant_apis:
            api = context_pack.relevant_apis[0]
            bullets = [
                f"Handler: {api['handler'] or 'Not explicitly detected'}",
                f"Source: {api['file'] or 'Not explicitly detected'}",
                f"Framework: {api['framework'] or 'Not explicitly detected'}",
            ]
            sections.append(ChatAnswerSection(title="Endpoint", content=f"{api['method']} {api['path']}", bullets=bullets, evidence_ids=["E1"]))
        if context_pack.relevant_workflow:
            sections.append(ChatAnswerSection(title="Related Workflow", bullets=[item["action"] for item in context_pack.relevant_workflow[:3]], evidence_ids=["E2"]))
        return sections

    def _architecture_sections(self, context_pack: ChatContextPack) -> list[ChatAnswerSection]:
        bullets = []
        if context_pack.project_identity.get("frameworks"):
            bullets.append(f"Frameworks: {', '.join(context_pack.project_identity['frameworks'][:4])}")
        if context_pack.project_identity.get("databases"):
            bullets.append(f"Databases / storage: {', '.join(context_pack.project_identity['databases'][:4])}")
        if context_pack.relevant_modules:
            bullets.append(f"Important modules: {', '.join(item['name'] for item in context_pack.relevant_modules[:4])}")
        return [ChatAnswerSection(title="Architecture", bullets=bullets, evidence_ids=list(context_pack.evidence_map.keys())[:3])]

    def _workflow_sections(self, context_pack: ChatContextPack) -> list[ChatAnswerSection]:
        bullets = [f"{item['order']}. {item['source']}: {item['action']}" for item in context_pack.relevant_workflow[:6]]
        return [ChatAnswerSection(title="Workflow Steps", bullets=bullets, evidence_ids=list(context_pack.evidence_map.keys())[:3])]

    def _test_gap_sections(self, context_pack: ChatContextPack) -> list[ChatAnswerSection]:
        bullets = [
            f"{item['area']}: {item['reason'] or 'Missing targeted test coverage evidence.'}"
            for item in context_pack.relevant_test_gaps[:5]
        ]
        return [ChatAnswerSection(title="Highest-Priority Gaps", bullets=bullets, evidence_ids=list(context_pack.evidence_map.keys())[:3])]

    def _onboarding_sections(self, context_pack: ChatContextPack) -> list[ChatAnswerSection]:
        report = context_pack.project_identity.get("onboarding_report") if isinstance(context_pack.project_identity, dict) else None
        report = report if isinstance(report, dict) else {}
        repo_type = str(getattr(context_pack.canonical_intelligence, "repo_type", "") or "").lower()
        project_type = str(getattr(context_pack.canonical_intelligence, "project_type", "") or context_pack.project_identity.get("project_type", "") or "").lower()
        is_fullstack = repo_type == "fullstack_app" or project_type == "fullstack"

        key_files = self._onboarding_key_files(context_pack)
        first_10 = self._onboarding_first_10(context_pack, report, is_fullstack)
        next_20 = self._onboarding_next_20(context_pack, report, is_fullstack)
        avoid = self._onboarding_avoid_first(context_pack, report)
        followups = build_followups("onboarding_question")

        return [
            ChatAnswerSection(title="First 10 minutes", bullets=first_10, evidence_ids=[]),
            ChatAnswerSection(title="Next 20 minutes", bullets=next_20, evidence_ids=[]),
            ChatAnswerSection(title="Key files to inspect", bullets=key_files or ["README.md", "package.json"], evidence_ids=list(context_pack.evidence_map.keys())[:5]),
            ChatAnswerSection(title="What to avoid at first", bullets=avoid, evidence_ids=[]),
            ChatAnswerSection(title="Suggested next questions", bullets=followups, evidence_ids=[]),
        ]

    def _onboarding_first_10(self, context_pack: ChatContextPack, report: dict, is_fullstack: bool) -> list[str]:
        reading_order = report.get("reading_order") if isinstance(report.get("reading_order"), list) else []
        if reading_order:
            bullets = []
            for item in reading_order[:3]:
                if not isinstance(item, dict):
                    continue
                title = sanitize_chat_text(item.get("title"), "")
                detail = sanitize_chat_text(item.get("detail"), "")
                text = title if not detail else f"{title}: {detail}"
                if text:
                    bullets.append(text)
            if bullets:
                return bullets[:3]
        bullets = ["Read README.md or product metadata to understand the project purpose."]
        if is_fullstack:
            bullets.append("Identify the frontend and backend folders.")
        else:
            bullets.append("Identify the main source folder and entry points.")
        bullets.append("Open package/dependency files such as package.json, requirements.txt, or pyproject.toml when present.")
        return bullets

    def _onboarding_next_20(self, context_pack: ChatContextPack, report: dict, is_fullstack: bool) -> list[str]:
        entry_points = [sanitize_chat_text(item, "") for item in report.get("key_entry_points", []) if sanitize_chat_text(item, "")]
        apis = [sanitize_chat_text(item, "") for item in report.get("important_apis", []) if sanitize_chat_text(item, "")]
        workflows = [sanitize_chat_text(item, "") for item in report.get("workflow_notes", []) if sanitize_chat_text(item, "")]
        bullets: list[str] = []
        if entry_points:
            bullets.append(f"Follow the main entry points: {', '.join(entry_points[:2])}.")
        elif is_fullstack:
            bullets.append("Follow frontend entry points and page/component structure.")
        else:
            bullets.append("Follow the main app entry points before diving into internals.")
        if apis:
            bullets.append(f"Review backend route/API files, starting with {apis[0]}.")
        elif context_pack.relevant_apis:
            first_api = context_pack.relevant_apis[0]
            bullets.append(f"Review backend API routes, starting with {first_api.get('method', 'GET')} {first_api.get('path', '/')}.")
        else:
            bullets.append("Review the API/workflow layer only where endpoint evidence exists.")
        if workflows:
            bullets.append(f"Trace one workflow: {workflows[0]}.")
        elif is_fullstack:
            bullets.append("Trace one user workflow from the frontend UI to the backend API surface.")
        else:
            bullets.append("Trace one workflow from entry point to service logic and response.")
        return bullets[:3]

    def _onboarding_key_files(self, context_pack: ChatContextPack) -> list[str]:
        candidates: list[str] = []
        for evidence in context_pack.selected_evidence:
            label = evidence_display_label(evidence)
            if label:
                candidates.append(label)
        for item in getattr(context_pack.canonical_intelligence, "evidence", []) or []:
            label = sanitize_chat_path(getattr(item, "label", "") or "")
            if label:
                candidates.append(label)
        for api in context_pack.relevant_apis:
            file_label = sanitize_chat_path(api.get("file", "") or api.get("framework", "") or "")
            if file_label:
                candidates.append(file_label)
        preferred = ("readme.md", "package.json", "dockerfile", "docker-compose", "main.py", "app.py", "api/", "route", "page.tsx")
        ranked = sorted(
            candidates,
            key=lambda value: (
                next((index for index, token in enumerate(preferred) if token in value.lower()), len(preferred)),
                len(value),
                value.lower(),
            ),
        )
        result: list[str] = []
        seen: set[str] = set()
        for item in ranked:
            cleaned = sanitize_chat_path(item) or sanitize_chat_text(item, "")
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            result.append(cleaned)
            if len(result) >= 5:
                break
        return result

    def _onboarding_avoid_first(self, context_pack: ChatContextPack, report: dict) -> list[str]:
        avoid = [sanitize_chat_text(item, "") for item in report.get("avoid_first", []) if sanitize_chat_text(item, "")]
        gotchas = [sanitize_chat_text(item, "") for item in report.get("gotchas", []) if sanitize_chat_text(item, "")]
        bullets = avoid[:2] or [
            "Do not start with generated files or build artifacts.",
            "Do not start with deep configuration unless setup is failing.",
        ]
        bullets.append("Do not assume business purpose beyond the canonical evidence.")
        if gotchas:
            bullets.append(f"Keep this early caveat in mind: {gotchas[0]}.")
        if not self._has_confirmed_setup_evidence(context_pack):
            bullets.append("Setup commands were not fully confirmed from the selected evidence.")
        return bullets[:5]

    def _has_confirmed_setup_evidence(self, context_pack: ChatContextPack) -> bool:
        labels = " ".join(evidence_display_label(item).lower() for item in context_pack.selected_evidence)
        return any(token in labels for token in ("package.json", "pyproject.toml", "readme.md", "dockerfile", "docker-compose"))

    def _module_sections(self, context_pack: ChatContextPack, include_files: bool = False) -> list[ChatAnswerSection]:
        bullets = []
        for item in context_pack.relevant_modules[:4]:
            detail = f"{item['name']} ({item['category']})"
            if include_files and item.get("files"):
                detail += f" -> {', '.join(item['files'][:3])}"
            bullets.append(detail)
        return [ChatAnswerSection(title="Related Modules", bullets=bullets, evidence_ids=list(context_pack.evidence_map.keys())[:3])]

    def _risk_sections(self, context_pack: ChatContextPack) -> list[ChatAnswerSection]:
        bullets = []
        for item in context_pack.relevant_risks[:5]:
            label = item.get("title", "Detected risk")
            recommendation = item.get("recommendation", "")
            bullets.append(f"{label}{f' — {recommendation}' if recommendation else ''}")
        return [ChatAnswerSection(title="Detected Risks", bullets=bullets, evidence_ids=list(context_pack.evidence_map.keys())[:3])]

    def _run_sections(self, context_pack: ChatContextPack) -> list[ChatAnswerSection]:
        bullets = []
        entry_points = context_pack.architecture_summary.get("entry_points", [])
        if entry_points:
            bullets.append(f"Start by inspecting entry points such as {', '.join(entry_points[:3])}.")
        if context_pack.project_identity.get("frameworks"):
            bullets.append(f"Detected frameworks: {', '.join(context_pack.project_identity['frameworks'][:4])}.")
        if not bullets:
            bullets.append("The analyzed evidence does not include a reliable run command, so setup should be confirmed from README or manifest files.")
        return [ChatAnswerSection(title="Run Guidance", bullets=bullets, evidence_ids=list(context_pack.evidence_map.keys())[:3])]

    def _remaining_sections(self, context_pack: ChatContextPack) -> list[ChatAnswerSection]:
        bullets = [item.get("title", "") for item in context_pack.relevant_risks[:4] if item.get("title")]
        if not bullets:
            bullets = ["The analyzed evidence does not clearly enumerate remaining work, so unresolved areas should be confirmed from docs and tests."]
        return [ChatAnswerSection(title="Remaining Caveats", bullets=bullets, evidence_ids=list(context_pack.evidence_map.keys())[:3])]

    def _uncertainty_sentence(self, context_pack: ChatContextPack) -> str:
        summary = sanitize_chat_text(context_pack.project_identity.get("summary"), "")
        lowered = summary.lower()
        if "product purpose evidence is partial" in lowered:
            return "The evidence supports a detailed but conservative summary centered on the repository's core workflow and implementation boundaries."
        if context_pack.confidence != "high":
            return "The evidence supports a detailed but conservative summary centered on the repository's core workflow and implementation boundaries."
        return ""
