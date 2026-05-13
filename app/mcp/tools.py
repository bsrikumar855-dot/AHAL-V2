from __future__ import annotations

import logging
from typing import Any, Callable

from app.api.intelligence_schema import build_intelligence_schema
from app.chat.chat_engine import ChatEngine
from app.chat.code_answering import build_code_chat_answer
from app.chat.models import ChatAnswer
from app.code import CodeAnalyzer
from app.config import config
from app.docs.exporters.markdown_exporter import MarkdownExporter
from app.docs.prd_diff_engine import PRDDiffEngine
from app.docs.prd_engine import PRDEngine
from app.graph.graph_engine import KnowledgeGraphEngine
from app.indexing.models import DeltaScanRequest
from app.indexing.repo_indexer import repo_indexer
from app.intelligence.intelligence_engine import IntelligenceEngine
from app.onboarding import OnboardingGenerator, render_onboarding_markdown
from app.mcp.safety import sanitize_filename, sanitize_payload, validate_code_input
from app.mcp.schemas import (
    AnalyzePRToolInput,
    AnalyzeCodeToolInput,
    AskRepoToolInput,
    CreateRepoIndexToolInput,
    DeltaScanToolInput,
    DiffPRDToolInput,
    GeneratePRDToolInput,
    MCPToolDefinition,
    OnboardingToolInput,
    SessionToolInput,
    TestGapToolInput,
)
from app.models.file_schema import FileMetadata, Priority, ScanResult, ScanStats, ScanStatus
from app.pr import PullRequestAnalysisRequest, PullRequestAnalyzer
from app.sessions.session_manager import session_manager
from app.testing import TestGapDetector
from app.utils.errors import INTERNAL_ERROR, INVALID_REQUEST, SESSION_NOT_FOUND, UNAUTHORIZED

logger = logging.getLogger("ahal.mcp")


class MCPToolRegistry:
    def __init__(self) -> None:
        self._chat_engine = ChatEngine()
        self._tools: dict[str, tuple[MCPToolDefinition, Callable[[dict[str, Any]], Any]]] = {
            "ahal_analyze_code": (
                MCPToolDefinition(
                    name="ahal_analyze_code",
                    description="Analyze a code snippet deterministically and return a normalized intelligence summary.",
                    input_schema=AnalyzeCodeToolInput.model_json_schema(),
                ),
                self._analyze_code,
            ),
            "ahal_get_project_intelligence": (
                MCPToolDefinition(
                    name="ahal_get_project_intelligence",
                    description="Return the frontend-safe intelligence schema for a completed AHAL session.",
                    input_schema=SessionToolInput.model_json_schema(),
                ),
                self._get_project_intelligence,
            ),
            "ahal_ask_repo": (
                MCPToolDefinition(
                    name="ahal_ask_repo",
                    description="Ask a question about a code, folder, or repo session and receive an evidence-backed answer.",
                    input_schema=AskRepoToolInput.model_json_schema(),
                ),
                self._ask_repo,
            ),
            "ahal_generate_prd": (
                MCPToolDefinition(
                    name="ahal_generate_prd",
                    description="Generate deterministic PRD output in JSON or markdown format.",
                    input_schema=GeneratePRDToolInput.model_json_schema(),
                ),
                self._generate_prd,
            ),
            "ahal_diff_prd": (
                MCPToolDefinition(
                    name="ahal_diff_prd",
                    description="Compare two completed sessions and return a deterministic PRD diff in JSON or markdown format.",
                    input_schema=DiffPRDToolInput.model_json_schema(),
                ),
                self._diff_prd,
            ),
            "ahal_create_repo_index": (
                MCPToolDefinition(
                    name="ahal_create_repo_index",
                    description="Create a reusable repository index from a completed folder or repo session.",
                    input_schema=CreateRepoIndexToolInput.model_json_schema(),
                ),
                self._create_repo_index,
            ),
            "ahal_delta_scan": (
                MCPToolDefinition(
                    name="ahal_delta_scan",
                    description="Run deterministic delta scan analysis against an existing AHAL repository index.",
                    input_schema=DeltaScanToolInput.model_json_schema(),
                ),
                self._delta_scan,
            ),
            "ahal_detect_test_gaps": (
                MCPToolDefinition(
                    name="ahal_detect_test_gaps",
                    description="Detect important APIs, modules, and workflows that appear to lack nearby test evidence.",
                    input_schema=TestGapToolInput.model_json_schema(),
                ),
                self._detect_test_gaps,
            ),
            "ahal_generate_onboarding_report": (
                MCPToolDefinition(
                    name="ahal_generate_onboarding_report",
                    description="Generate a practical onboarding guide for a completed folder or repo session in JSON or markdown format.",
                    input_schema=OnboardingToolInput.model_json_schema(),
                ),
                self._generate_onboarding_report,
            ),
            "ahal_analyze_pr": (
                MCPToolDefinition(
                    name="ahal_analyze_pr",
                    description="Analyze a pull request style diff and return review-focused intelligence.",
                    input_schema=AnalyzePRToolInput.model_json_schema(),
                ),
                self._analyze_pr,
            ),
        }

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.model_dump() for tool, _ in self._tools.values()]

    def call_tool(self, name: str, arguments: dict[str, Any] | None):
        record = self._tools.get(name)
        if record is None:
            return self._error(INVALID_REQUEST, f"Unknown MCP tool: {name}")
        _, handler = record
        try:
            result = handler(arguments or {})
            return {"ok": True, "result": sanitize_payload(result)}
        except MCPToolError as exc:
            return exc.to_payload()
        except Exception:
            logger.exception("MCP tool failed safely", extra={"tool": name})
            return self._error(INTERNAL_ERROR, "MCP tool execution failed.")

    def _analyze_code(self, arguments: dict[str, Any]):
        payload = AnalyzeCodeToolInput.model_validate(arguments)
        valid, message = validate_code_input(payload.code)
        if not valid:
            raise MCPToolError(INVALID_REQUEST, message)

        filename = sanitize_filename(payload.filename)
        result = CodeAnalyzer().analyze(code=payload.code, filename=filename, language=(payload.language or "").strip().lower())
        return result.model_dump()

    def _get_project_intelligence(self, arguments: dict[str, Any]):
        payload = SessionToolInput.model_validate(arguments)
        info, result = self._require_completed_session(payload.session_id, payload.session_token)
        return build_intelligence_schema(payload.session_id, info.session_type, result)

    def _ask_repo(self, arguments: dict[str, Any]):
        payload = AskRepoToolInput.model_validate(arguments)
        info = session_manager.get_info(payload.session_id)
        if info is None:
            raise MCPToolError(SESSION_NOT_FOUND, "Session not found")
        self._check_token(payload.session_id, payload.session_token)
        if info.status != ScanStatus.COMPLETED:
            raise MCPToolError("IN_PROGRESS", "Session scan is still in progress.")

        if info.session_type == "code":
            artifact = session_manager.get_artifact(payload.session_id, "code_result")
            if artifact is None:
                raise MCPToolError(INTERNAL_ERROR, "Code session result is missing.")
            return self._code_chat_answer(payload.question, artifact).model_dump()

        result = session_manager.get_result(payload.session_id)
        if result is None:
            raise MCPToolError("IN_PROGRESS", "Session scan is still in progress.")
        intelligence = IntelligenceEngine().analyze(scan_result=result, session_id=payload.session_id, include_llm_explanation=False)
        graph = KnowledgeGraphEngine().build(scan_result=result, intelligence_result=intelligence, session_id=payload.session_id)
        answer = self._chat_engine.answer(
            question=payload.question,
            scan_result=result,
            intelligence_result=intelligence,
            graph_result=graph,
            session_id=payload.session_id,
            include_history=False,
        )
        return answer.model_dump()

    def _generate_prd(self, arguments: dict[str, Any]):
        payload = GeneratePRDToolInput.model_validate(arguments)
        _, result, intelligence, graph, prd = self._build_prd_for_session(payload.session_id, payload.session_token)
        if payload.format == "markdown":
            return MarkdownExporter().export(prd)
        return prd.model_dump()

    def _diff_prd(self, arguments: dict[str, Any]):
        payload = DiffPRDToolInput.model_validate(arguments)
        if payload.base_session_id == payload.target_session_id:
            raise MCPToolError(INVALID_REQUEST, "Base and target session ids must be different.")
        _, _, _, _, base_prd = self._build_prd_for_session(payload.base_session_id, payload.session_token)
        _, _, _, _, target_prd = self._build_prd_for_session(payload.target_session_id, payload.session_token)
        diff = PRDDiffEngine().compare(base_prd, target_prd, payload.base_session_id, payload.target_session_id)
        if payload.format == "markdown":
            return PRDDiffEngine().to_markdown(diff)
        return diff.model_dump()

    def _create_repo_index(self, arguments: dict[str, Any]):
        payload = CreateRepoIndexToolInput.model_validate(arguments)
        info, result = self._require_completed_session(payload.session_id, payload.session_token)
        if info.session_type not in {"folder", "repo"}:
            raise MCPToolError(INVALID_REQUEST, "Only completed folder or repo sessions can be indexed.")
        return repo_indexer.create_index(payload.session_id, info, result).model_dump()

    def _delta_scan(self, arguments: dict[str, Any]):
        payload = DeltaScanToolInput.model_validate(arguments)
        index = repo_indexer.get_index(payload.index_id)
        if index is None:
            raise MCPToolError(SESSION_NOT_FOUND, "Repository index not found")
        self._check_token(index.last_scan_session_id, payload.session_token)
        result = repo_indexer.run_delta(
            DeltaScanRequest(
                index_id=payload.index_id,
                changed_files=payload.changed_files,
                force_full_rescan=False,
            )
        )
        return result.model_dump()

    def _detect_test_gaps(self, arguments: dict[str, Any]):
        payload = TestGapToolInput.model_validate(arguments)
        info, result = self._require_completed_session(payload.session_id, payload.session_token)
        if info.session_type not in {"folder", "repo"}:
            raise MCPToolError(INVALID_REQUEST, "Test gap detection currently supports folder and repo sessions only.")
        intelligence = IntelligenceEngine().analyze(
            scan_result=result,
            session_id=payload.session_id,
            include_llm_explanation=False,
        )
        gap_result = TestGapDetector().detect(
            session_id=payload.session_id,
            scan_result=result,
            intelligence_result=intelligence,
            include_low_priority=payload.include_low_priority,
        )
        return gap_result.model_dump()

    def _generate_onboarding_report(self, arguments: dict[str, Any]):
        payload = OnboardingToolInput.model_validate(arguments)
        audience = str(payload.audience or "new_engineer").strip().lower()
        if audience not in {"new_engineer", "frontend", "backend", "qa", "devops"}:
            raise MCPToolError(INVALID_REQUEST, "Unsupported audience. Allowed: new_engineer, frontend, backend, qa, devops")
        if int(payload.time_budget_minutes) <= 0:
            raise MCPToolError(INVALID_REQUEST, "time_budget_minutes must be greater than 0.")
        info, result = self._require_completed_session(payload.session_id, payload.session_token)
        if info.session_type not in {"folder", "repo"}:
            raise MCPToolError(INVALID_REQUEST, "Onboarding report currently supports folder and repo sessions only.")
        intelligence = IntelligenceEngine().analyze(
            scan_result=result,
            session_id=payload.session_id,
            include_llm_explanation=False,
        )
        graph = KnowledgeGraphEngine().build(
            scan_result=result,
            intelligence_result=intelligence,
            session_id=payload.session_id,
        )
        prd = PRDEngine().generate(
            scan_result=result,
            intelligence_result=intelligence,
            graph_result=graph,
            session_id=payload.session_id,
        )
        report = OnboardingGenerator().generate(
            session_id=payload.session_id,
            scan_result=result,
            intelligence_result=intelligence,
            graph_result=graph,
            prd_result=prd,
            audience=audience,
            time_budget_minutes=payload.time_budget_minutes,
        )
        if payload.format == "markdown":
            return render_onboarding_markdown(report)
        return report.model_dump()

    def _analyze_pr(self, arguments: dict[str, Any]):
        payload = AnalyzePRToolInput.model_validate(arguments)
        if not str(payload.diff_text or "").strip() and not payload.changed_files:
            raise MCPToolError(INVALID_REQUEST, "Provide diff_text or changed_files for PR analysis.")
        if str(payload.diff_text or "") and len(str(payload.diff_text or "")) > config.scanner.change_max_diff_chars:
            raise MCPToolError(INVALID_REQUEST, f"Diff exceeds maximum length of {config.scanner.change_max_diff_chars} characters.")

        scan_result = None
        intelligence = None
        graph = None
        repo_index = None
        session_id = payload.session_id
        if payload.index_id:
            repo_index = repo_indexer.get_index(payload.index_id)
            if repo_index is None:
                raise MCPToolError(SESSION_NOT_FOUND, "Repository index not found")
            session_id = session_id or repo_index.last_scan_session_id
        if session_id:
            info, scan_result = self._require_completed_session(session_id, payload.session_token)
            if info.session_type not in {"folder", "repo"}:
                raise MCPToolError(INVALID_REQUEST, "PR analysis currently supports folder and repo sessions only.")
            intelligence = IntelligenceEngine().analyze(
                scan_result=scan_result,
                session_id=session_id,
                include_llm_explanation=False,
            )
            graph = KnowledgeGraphEngine().build(
                scan_result=scan_result,
                intelligence_result=intelligence,
                session_id=session_id,
            )
        result = PullRequestAnalyzer().analyze(
            PullRequestAnalysisRequest(**payload.model_dump(exclude={"session_token"})),
            scan_result=scan_result,
            intelligence_result=intelligence,
            graph_result=graph,
            repo_index=repo_index,
        )
        return result.model_dump()

    def _require_completed_session(self, session_id: str, token: str | None):
        info = session_manager.get_info(session_id)
        if info is None:
            raise MCPToolError(SESSION_NOT_FOUND, "Session not found")
        self._check_token(session_id, token)
        if info.status != ScanStatus.COMPLETED:
            raise MCPToolError("IN_PROGRESS", "Session scan is still in progress.")
        result = session_manager.get_result(session_id)
        if result is None:
            raise MCPToolError("IN_PROGRESS", "Session scan is still in progress.")
        return info, result

    def _check_token(self, session_id: str, token: str | None) -> None:
        if not config.scanner.require_session_token:
            return
        if not token:
            raise MCPToolError(UNAUTHORIZED, "session_token is required for this tool call.")
        if not session_manager.validate_token(session_id, token):
            raise MCPToolError(UNAUTHORIZED, "Invalid or expired session token.")

    def _build_prd_for_session(self, session_id: str, token: str | None):
        info, result = self._require_completed_session(session_id, token)
        intelligence = IntelligenceEngine().analyze(scan_result=result, session_id=session_id, include_llm_explanation=False)
        graph = KnowledgeGraphEngine().build(scan_result=result, intelligence_result=intelligence, session_id=session_id)
        prd = PRDEngine().generate(scan_result=result, intelligence_result=intelligence, graph_result=graph, session_id=session_id)
        return info, result, intelligence, graph, prd

    def _code_chat_answer(self, question: str, code_result) -> ChatAnswer:
        return build_code_chat_answer(question, code_result)

    def _error(self, code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "error_code": code, "message": message}


class MCPToolError(Exception):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message

    def to_payload(self) -> dict[str, Any]:
        return {"ok": False, "error_code": self.error_code, "message": self.message}
