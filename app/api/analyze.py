"""
AHAL AI — Analyze API  [HARDENED v4 + Phase 2]

Endpoints:
    POST /analyze/upload                — Upload a ZIP or single file
    POST /analyze/github                — Submit a GitHub URL for scanning
    GET  /analyze/status/{id}           — Poll session status
    GET  /analyze/result/{id}           — Fetch full scan result
    POST /analyze/cancel/{id}           — Stop a running scan
    GET  /analyze/intelligence/{id}     — Phase 2 intelligence analysis

Hardening applied:
    Fix 1 — Atomic create_session_if_capacity() replaces separate count+create
    Fix 5 — Optional X-Session-Token header validation
    Fix 6 — Per-IP rate limiting via RateLimiter dependency
    Fix 9 — All errors use AHALError structured contract
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import zipfile
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.analyze.router import analysis_router
from app.chat.chat_engine import ChatEngine
from app.chat.code_answering import build_code_chat_answer
from app.chat.models import ChatAnswer, ChatRequest
from app.changes import ChangeAnalysisRequest, ChangeImpactAnalyzer, ChangeImpactResult
from app.code import CodeAnalyzer
from app.config import config
from app.docs.diff_models import PRDDiffResult
from app.docs.template_engine import PRDTemplateEngine
from app.docs.template_models import PRDTemplate, RenderedTemplateResult
from app.graph.models import KnowledgeGraphResult
from app.indexing.models import DeltaScanRequest, DeltaScanResult, RepoIndex
from app.indexing.repo_indexer import repo_indexer
from app.llm.telemetry import llm_telemetry
from app.llm_orchestration import LLMOrchestrator, OrchestrationRequest
from app.models.file_schema import FileMetadata, InputType, Priority, ScanResult, ScanStats, ScanStatus, SessionInfo
from app.onboarding import OnboardingGenerator, OnboardingReport, render_onboarding_markdown
from app.pr import PullRequestAnalysisRequest, PullRequestAnalysisResult, PullRequestAnalyzer
from app.api.intelligence_schema import build_intelligence_schema
from app.sessions.session_manager import session_manager
from app.storage import storage_backend
from app.testing import TestGapDetector, TestGapResult
from app.utils.errors import (
    CAPACITY_EXCEEDED,
    INVALID_FILE,
    INVALID_URL,
    RATE_LIMITED,
    SCAN_IN_PROGRESS,
    SESSION_NOT_FOUND,
    UNAUTHORIZED,
    FILE_TOO_LARGE,
    INTERNAL_ERROR,
    INVALID_REQUEST,
    err,
)
from app.utils.rate_limiter import get_rate_limiter
from app.workers.scan_worker import submit_scan

logger = logging.getLogger("ahal.api.analyze")

router = APIRouter(prefix="/analyze", tags=["analyze"])
chat_engine = ChatEngine()
test_gap_detector = TestGapDetector()
template_engine = PRDTemplateEngine()
llm_orchestrator = LLMOrchestrator()

# Chunk size for streaming upload to disk
_UPLOAD_CHUNK = 1024 * 1024  # 1 MB


# ── Request / Response models ────────────────────────────────────

class GitHubRequest(BaseModel):
    github_url: str


class SubmitResponse(BaseModel):
    session_id: str
    session_type: str = "folder"
    status: str
    progress: int = 0
    message: str
    created_at: str = ""
    updated_at: str = ""
    access_token: Optional[str] = None  # Fix 5: present when AHAL_REQUIRE_SESSION_TOKEN=true


class CancelResponse(BaseModel):
    session_id: str
    session_type: str = "folder"
    status: str
    message: str


class CodeAnalysisRequest(BaseModel):
    code: str
    filename: Optional[str] = None
    language: Optional[str] = None
    include_llm: bool = False


class TimelineResponse(BaseModel):
    session_id: str
    events: list[dict]


_SUPPORTED_CODE_LANGUAGES = {"python", "javascript", "typescript", "java", "go", "text"}


@router.get("/llm/status")
async def get_llm_status() -> dict:
    snapshot = llm_telemetry.snapshot()
    return {
        "llm_enabled": config.scanner.llm_enabled,
        "chat_llm_enabled": config.scanner.chat_llm_enabled,
        "docs_llm_enabled": config.scanner.docs_llm_enabled,
        "model": config.scanner.llm_model,
        "provider": config.scanner.llm_provider,
        "key_present": bool(config.scanner.gemini_api_key),
        "last_error_type": snapshot.last_error_type,
        "fallback_count": snapshot.fallback_count,
        "rate_limited_until": snapshot.rate_limited_until,
        "not_found_count": snapshot.not_found_count,
        "rate_limit_count": snapshot.rate_limit_count,
        "timeout_count": snapshot.timeout_count,
        "warnings": list(config.scanner.llm_health_warnings()),
    }


# ── Dependency helpers ───────────────────────────────────────────

def _check_rate_limit(request: Request) -> None:
    """Fix 6: Raise 429 if IP exceeds rate limit. No-op when disabled."""
    rl = get_rate_limiter()
    if not rl.enabled:
        return
    ip = request.client.host if request.client else "unknown"
    if not rl.is_allowed(ip):
        raise HTTPException(
            status_code=429,
            detail=err(RATE_LIMITED, f"Rate limit exceeded. Max {config.scanner.rate_limit_max_requests} requests per {config.scanner.rate_limit_window_seconds}s."),
        )


def _check_session_token(session_id: str, x_session_token: Optional[str]) -> None:
    """
    Fix 5: Validate the session token when token mode is enabled.
    Raises 401 on missing or invalid token.
    No-op when AHAL_REQUIRE_SESSION_TOKEN=false.
    """
    if not config.scanner.require_session_token:
        return
    if not x_session_token:
        raise HTTPException(
            status_code=401,
            detail=err(UNAUTHORIZED, "X-Session-Token header is required"),
        )
    if not session_manager.validate_token(session_id, x_session_token):
        raise HTTPException(
            status_code=401,
            detail=err(UNAUTHORIZED, "Invalid or expired session token"),
        )


def _code_scan_result(session_id: str, filename: str, code: str) -> ScanResult:
    size_bytes = len(code.encode("utf-8"))
    return ScanResult(
        session_id=session_id,
        status=ScanStatus.COMPLETED,
        progress=100,
        stats=ScanStats(
            total_files_discovered=1,
            files_included=1,
            total_size_bytes=size_bytes,
            included_size_bytes=size_bytes,
        ),
        files=[
            FileMetadata(
                path=filename,
                size_bytes=size_bytes,
                extension=os.path.splitext(filename)[1],
                priority=Priority.HIGH,
            )
        ],
        contents={filename: code},
    )


def _sanitize_filename(filename: str | None) -> str:
    raw = str(filename or "snippet.txt").strip()
    if not raw:
        return "snippet.txt"
    if "\x00" in raw or ":" in raw:
        raise ValueError("Filename contains unsupported characters.")
    if ".." in raw:
        raise ValueError("Filename must not contain parent path traversal.")
    raw = raw.replace("\\", "/").split("/")[-1]
    raw = re.sub(r"[^A-Za-z0-9._ -]", "_", raw).strip(" .")
    raw = raw[: config.scanner.code_max_filename_chars]
    return raw or "snippet.txt"


def _normalize_language(language: str | None) -> str:
    normalized = str(language or "").strip().lower()
    return normalized if normalized in _SUPPORTED_CODE_LANGUAGES else ""


def _looks_binary_payload(code: str) -> bool:
    if not code:
        return False
    if "\x00" in code:
        return True
    sample = code[:200]
    weird = sum(1 for char in sample if ord(char) < 9 or (13 < ord(char) < 32))
    return weird > max(3, len(sample) // 20)


def _submit_response(session_id: str, session_type: str, status: str, progress: int, message: str, access_token: Optional[str] = None) -> SubmitResponse:
    info = session_manager.get_info(session_id)
    return SubmitResponse(
        session_id=session_id,
        session_type=session_type,
        status=status,
        progress=progress,
        message=message,
        created_at=getattr(info, "created_at", "") if info else "",
        updated_at=getattr(info, "updated_at", "") if info else "",
        access_token=access_token,
    )


def _sanitize_timeline_event(event) -> dict:
    message = str(getattr(event, "message", "") or "No message available.")
    lowered = message.lower()
    if any(token in lowered for token in ("traceback", "magicmock", "repr(", "object at 0x")):
        message = "Timeline event recorded."
    metadata = getattr(event, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    safe_metadata = {}
    for key, value in metadata.items():
        text = str(value or "")
        if any(token in text.lower() for token in ("api_key", "token", "secret", "password")):
            text = "[REDACTED]"
        safe_metadata[str(key)] = text
    return {
        "timestamp": str(getattr(event, "timestamp", "")),
        "stage": str(getattr(event, "stage", "")),
        "status": str(getattr(event, "status", "")),
        "message": message,
        "metadata": safe_metadata,
    }


def _validate_change_request(body: ChangeAnalysisRequest) -> None:
    diff_text = str(body.diff_text or "")
    changed_files = list(body.changed_files or [])
    if not diff_text.strip() and not changed_files:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", "Provide diff_text or changed_files for change impact analysis."),
        )
    if diff_text and len(diff_text) > config.scanner.change_max_diff_chars:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", f"Diff exceeds maximum length of {config.scanner.change_max_diff_chars} characters."),
        )
    if len(changed_files) > config.scanner.change_max_files:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", f"Changed files exceed maximum count of {config.scanner.change_max_files}."),
        )


def _require_completed_indexable_session(session_id: str, x_session_token: Optional[str] = None):
    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )
    _check_session_token(session_id, x_session_token)
    if info.status != ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress â€” stage: {info.stage} ({info.progress}%)",
                stage=info.stage,
                progress=info.progress,
            ),
        )
    if info.session_type not in {"folder", "repo"}:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", "Only completed folder or repo sessions can be indexed."),
        )
    result = session_manager.get_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Scan is marked complete but result is missing."),
        )
    return info, result


def _build_prd_for_session(session_id: str):
    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )
    if info.status != ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress â€” stage: {info.stage} ({info.progress}%)",
                stage=info.stage,
                progress=info.progress,
            ),
        )
    result = session_manager.get_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Scan is marked complete but result is missing."),
        )

    from app.graph.graph_engine import KnowledgeGraphEngine
    from app.intelligence.intelligence_engine import IntelligenceEngine
    from app.docs.prd_engine import PRDEngine

    intelligence = IntelligenceEngine().analyze(
        scan_result=result,
        session_id=session_id,
        include_llm_explanation=False,
    )
    graph = KnowledgeGraphEngine().build(
        scan_result=result,
        intelligence_result=intelligence,
        session_id=session_id,
    )
    prd = PRDEngine().generate(
        scan_result=result,
        intelligence_result=intelligence,
        graph_result=graph,
        session_id=session_id,
    )
    return info, result, intelligence, graph, prd


def _build_onboarding_for_session(session_id: str, audience: str, time_budget_minutes: int):
    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )
    if info.status != ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress â€” stage: {info.stage} ({info.progress}%)",
                stage=info.stage,
                progress=info.progress,
            ),
        )
    if info.session_type not in {"folder", "repo"}:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, "Onboarding report currently supports folder and repo sessions only."),
        )
    result = session_manager.get_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=500,
            detail=err(INTERNAL_ERROR, "Scan is marked complete but result is missing."),
        )
    from app.graph.graph_engine import KnowledgeGraphEngine
    from app.intelligence.intelligence_engine import IntelligenceEngine
    from app.docs.prd_engine import PRDEngine

    intelligence = IntelligenceEngine().analyze(
        scan_result=result,
        session_id=session_id,
        include_llm_explanation=False,
    )
    graph = KnowledgeGraphEngine().build(
        scan_result=result,
        intelligence_result=intelligence,
        session_id=session_id,
    )
    prd = PRDEngine().generate(
        scan_result=result,
        intelligence_result=intelligence,
        graph_result=graph,
        session_id=session_id,
    )
    report = OnboardingGenerator().generate(
        session_id=session_id,
        scan_result=result,
        intelligence_result=intelligence,
        graph_result=graph,
        prd_result=prd,
        audience=audience,
        time_budget_minutes=time_budget_minutes,
    )
    return info, report


def _build_pr_context(session_id: str):
    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )
    if info.status != ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress â€” stage: {info.stage} ({info.progress}%)",
                stage=info.stage,
                progress=info.progress,
            ),
        )
    if info.session_type not in {"folder", "repo"}:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, "PR analysis currently supports folder and repo sessions only."),
        )
    result = session_manager.get_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=500,
            detail=err(INTERNAL_ERROR, "Scan is marked complete but result is missing."),
        )
    from app.graph.graph_engine import KnowledgeGraphEngine
    from app.intelligence.intelligence_engine import IntelligenceEngine

    intelligence = IntelligenceEngine().analyze(
        scan_result=result,
        session_id=session_id,
        include_llm_explanation=False,
    )
    graph = KnowledgeGraphEngine().build(
        scan_result=result,
        intelligence_result=intelligence,
        session_id=session_id,
    )
    return info, result, intelligence, graph


def _code_chat_answer(question: str, code_result) -> ChatAnswer:
    return build_code_chat_answer(question, code_result)


# ── POST /analyze/upload ─────────────────────────────────────────

@router.post("/code", response_model=SubmitResponse)
async def analyze_code(
    request: Request,
    body: CodeAnalysisRequest,
) -> SubmitResponse:
    _check_rate_limit(request)

    code = str(body.code or "")
    if not code.strip():
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", "Code must not be empty"),
        )
    if len(code) > config.scanner.code_max_chars:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", f"Code exceeds maximum length of {config.scanner.code_max_chars} characters."),
        )
    if len(code.encode("utf-8")) > config.scanner.max_single_file_bytes:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", "Code payload exceeds the configured size limit."),
        )
    if _looks_binary_payload(code):
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", "Binary-looking payloads are not supported for code analysis."),
        )

    try:
        source_name = _sanitize_filename(body.filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", str(exc)),
        ) from exc

    normalized_language = _normalize_language(body.language)
    result = analysis_router.create_session(session_type="code", source_name=source_name)
    if result is None:
        active = session_manager.get_active_session_count()
        return _submit_response(
            session_id="",
            session_type="code",
            status="rejected",
            progress=0,
            message=f"Server busy ({active}/{config.scanner.max_active_sessions} scans active). Try again later.",
            access_token=None,
        )

    session_id = result.session_id
    try:
        session_manager.append_timeline_event(session_id, "scan_started", "scanning", "Code analysis started")
        scan_result = _code_scan_result(session_id, source_name, code)
        code_result = CodeAnalyzer().analyze(code=code, filename=source_name, language=normalized_language)
        session_manager.append_timeline_event(
            session_id,
            "smart_context_selected",
            "scanning",
            "Snippet context selected",
            {"selected_files": 1},
        )
        session_manager.set_artifact(session_id, "code_result", code_result)
        session_manager.set_result(session_id, scan_result)
        session_manager.set_session_metadata(
            session_id,
            confidence=getattr(code_result, "confidence", "low"),
            warnings=list(getattr(code_result, "warnings", [])),
        )
        session_manager.append_timeline_event(session_id, "chat_enabled", "completed", "Code session chat is ready")
        return _submit_response(
            session_id=session_id,
            session_type="code",
            status="completed",
            progress=100,
            message=f"Code analysis completed. Poll /analyze/status/{session_id} or use /analyze/chat/{session_id}.",
            access_token=result.access_token if config.scanner.require_session_token else None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Code analysis failed safely for session %s", session_id)
        session_manager.set_failed(session_id, "Code analysis failed.")
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Code analysis failed."),
        ) from exc


@router.post("/upload", response_model=SubmitResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
) -> SubmitResponse:
    """
    Accept a ZIP archive or a single source file.
    Returns immediately with a session_id for polling.
    """
    # Fix 6: rate limit check
    _check_rate_limit(request)

    filename = file.filename or "upload"
    is_zip = (
        filename.lower().endswith(".zip")
        or file.content_type == "application/zip"
    )

    # Stream upload to a temp file (never hold full file in memory)
    base = config.scanner.temp_base_dir or tempfile.gettempdir()
    suffix = ".zip" if is_zip else os.path.splitext(filename)[1]
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="ahal_upload_", dir=base)

    try:
        total_written = 0
        max_size = config.scanner.max_zip_size_bytes if is_zip else config.scanner.max_single_file_bytes

        with os.fdopen(tmp_fd, "wb") as fh:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK)
                if not chunk:
                    break
                total_written += len(chunk)
                if total_written > max_size:
                    fh.close()
                    os.unlink(tmp_path)
                    raise HTTPException(
                        status_code=413,
                        detail=err(
                            FILE_TOO_LARGE,
                            f"File exceeds maximum size ({max_size // (1024 * 1024)} MB)",
                            max_size_mb=max_size // (1024 * 1024),
                        ),
                    )
                fh.write(chunk)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Upload failed: %s", exc)
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Upload failed"),
        ) from exc

    # Validate ZIP integrity
    if is_zip:
        if not zipfile.is_zipfile(tmp_path):
            os.unlink(tmp_path)
            raise HTTPException(
                status_code=400,
                detail=err(INVALID_FILE, "File is not a valid ZIP archive"),
            )

    # Fix 1: Atomic capacity check + session creation in one lock
    result = analysis_router.create_session(session_type="folder", source_name=filename)
    if result is None:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        active = session_manager.get_active_session_count()
        return SubmitResponse(
            session_id="",
            session_type="folder",
            status="rejected",
            progress=0,
            message=f"Server busy ({active}/{config.scanner.max_active_sessions} scans active). Try again later.",
        )

    session_id = result.session_id
    session_manager.append_timeline_event(session_id, "upload_received", "pending", "Upload received", {"filename": filename})
    input_type = InputType.ZIP if is_zip else InputType.SINGLE_FILE

    submit_scan(
        session_id=session_id,
        input_type=input_type,
        file_path=tmp_path,
        display_name=filename,
    )

    return _submit_response(
        session_id=session_id,
        session_type="folder",
        status="accepted",
        progress=0,
        message=f"{'ZIP' if is_zip else 'File'} upload accepted. Poll /analyze/status/{session_id}",
        access_token=result.access_token if config.scanner.require_session_token else None,
    )


# ── POST /analyze/github ─────────────────────────────────────────

@router.post("/github", response_model=SubmitResponse)
async def scan_github(
    request: Request,
    body: GitHubRequest,
) -> SubmitResponse:
    """
    Submit a GitHub repo URL for scanning.
    Returns immediately with a session_id for polling.
    """
    # Fix 6: rate limit check
    _check_rate_limit(request)

    url = body.github_url.strip()
    if not url.startswith("https://github.com/"):
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_URL, "Only https://github.com/ URLs are supported"),
        )

    # Fix 1: Atomic capacity check + session creation in one lock
    result = analysis_router.create_session(session_type="repo", source_name=url)
    if result is None:
        active = session_manager.get_active_session_count()
        return SubmitResponse(
            session_id="",
            session_type="repo",
            status="rejected",
            progress=0,
            message=f"Server busy ({active}/{config.scanner.max_active_sessions} scans active). Try again later.",
        )

    session_id = result.session_id
    session_manager.append_timeline_event(session_id, "repo_download_started", "pending", "GitHub repository queued for download", {"github_url": url})
    submit_scan(
        session_id=session_id,
        input_type=InputType.GITHUB_REPO,
        github_url=url,
    )

    return _submit_response(
        session_id=session_id,
        session_type="repo",
        status="accepted",
        progress=0,
        message=f"GitHub scan accepted. Poll /analyze/status/{session_id}",
        access_token=result.access_token if config.scanner.require_session_token else None,
    )


# ── GET /analyze/status/{session_id} ─────────────────────────────

@router.get("/status/{session_id}", response_model=SessionInfo)
async def get_status(
    session_id: str,
    x_session_token: Optional[str] = Header(default=None),
) -> SessionInfo:
    """Poll scan progress."""
    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )
    # Fix 5: token validation (no-op when disabled)
    _check_session_token(session_id, x_session_token)
    return info


# ── GET /analyze/result/{session_id} ─────────────────────────────

@router.get("/result/{session_id}", response_model=ScanResult)
async def get_result(
    session_id: str,
    x_session_token: Optional[str] = Header(default=None),
) -> ScanResult:
    """Fetch the full scan result once the scan is complete."""
    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )
    # Fix 5: token validation
    _check_session_token(session_id, x_session_token)

    result = session_manager.get_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress — stage: {info.stage} ({info.progress}%, {info.processed_files}/{info.total_files} files)",
                stage=info.stage,
                progress=info.progress,
                processed_files=info.processed_files,
                total_files=info.total_files,
            ),
        )
    return result


# ── POST /analyze/cancel/{session_id} ────────────────────────────

@router.post("/cancel/{session_id}", response_model=CancelResponse)
async def cancel_scan(
    session_id: str,
    request: Request,
    x_session_token: Optional[str] = Header(default=None),
) -> CancelResponse:
    """
    Stop a running scan immediately.
    Returns status='already_done' if the scan has already completed.
    """
    # Fix 6: rate limit on cancel (prevents spamming)
    _check_rate_limit(request)

    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )
    # Fix 5: token validation
    _check_session_token(session_id, x_session_token)

    was_cancelled = session_manager.cancel_session(session_id)

    if was_cancelled:
        logger.info("Scan cancelled by user: %s", session_id)
        return CancelResponse(
            session_id=session_id,
            session_type=info.session_type,
            status="cancelled",
            message="Scan stopped successfully",
        )
    else:
        return CancelResponse(
            session_id=session_id,
            session_type=info.session_type,
            status="already_done",
            message=f"Scan is already in terminal state: {info.status.value}",
        )


# ── GET /analyze/intelligence/{session_id} (Phase 2) ─────────────

@router.get("/intelligence/{session_id}")
async def get_intelligence(
    session_id: str,
    include_llm_explanation: bool = False,
    x_session_token: Optional[str] = Header(default=None),
):
    """
    Phase 2: Run deterministic intelligence analysis on a completed scan.
    Returns IntelligenceResult with all detections, classifications, and scores.
    """
    # Session existence check
    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )

    # Token validation (no-op when disabled)
    _check_session_token(session_id, x_session_token)

    # Check scan completion
    result = session_manager.get_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress — stage: {info.stage} ({info.progress}%)",
                stage=info.stage,
                progress=info.progress,
            ),
        )

    # Run intelligence engine (synchronous — operates on in-memory ScanResult)
    try:
        schema = build_intelligence_schema(session_id, info.session_type, result)
        if include_llm_explanation:
            schema["warnings"] = list(schema.get("warnings", [])) + [
                "LLM explanation is not included in the normalized intelligence schema."
            ]
        return schema
    except Exception as exc:
        logger.error("Intelligence schema build failed safely for session %s", session_id)
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Intelligence schema generation failed."),
        ) from exc


@router.get("/timeline/{session_id}", response_model=TimelineResponse)
async def get_timeline(
    session_id: str,
    x_session_token: Optional[str] = Header(default=None),
) -> TimelineResponse:
    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )
    _check_session_token(session_id, x_session_token)
    try:
        events = [_sanitize_timeline_event(item) for item in session_manager.get_timeline(session_id)]
        events.sort(key=lambda item: item.get("timestamp", ""))
        return TimelineResponse(session_id=session_id, events=events)
    except Exception as exc:
        logger.error("Timeline retrieval failed safely for session %s", session_id)
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Timeline retrieval failed."),
        ) from exc


@router.get("/testgap/{session_id}", response_model=TestGapResult)
async def get_test_gap_report(
    session_id: str,
    include_low_priority: bool = False,
    x_session_token: Optional[str] = Header(default=None),
) -> TestGapResult:
    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )
    _check_session_token(session_id, x_session_token)
    if info.status != ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress — stage: {info.stage} ({info.progress}%)",
                stage=info.stage,
                progress=info.progress,
            ),
        )
    if info.session_type not in {"folder", "repo"}:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", "Test gap detection currently supports folder and repo sessions only."),
        )
    result = session_manager.get_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress — stage: {info.stage} ({info.progress}%)",
                stage=info.stage,
                progress=info.progress,
            ),
        )

    session_manager.append_timeline_event(session_id, "test_gap_started", "scanning", "Test gap detection started")
    try:
        from app.intelligence.intelligence_engine import IntelligenceEngine

        intelligence = IntelligenceEngine().analyze(
            scan_result=result,
            session_id=session_id,
            include_llm_explanation=False,
        )
        report = test_gap_detector.detect(
            session_id=session_id,
            scan_result=result,
            intelligence_result=intelligence,
            include_low_priority=include_low_priority,
        )
        session_manager.append_timeline_event(session_id, "test_gap_completed", "completed", "Test gap detection completed")
        storage_backend.save_test_gap_result(session_id, report.model_dump())
        return report
    except HTTPException:
        session_manager.append_timeline_event(session_id, "test_gap_failed", "failed", "Test gap detection failed")
        raise
    except Exception as exc:
        logger.error("Test gap detection failed safely for session %s", session_id)
        session_manager.append_timeline_event(session_id, "test_gap_failed", "failed", "Test gap detection failed")
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Test gap detection failed."),
        ) from exc


@router.post("/change-impact", response_model=ChangeImpactResult)
async def analyze_change_impact(
    body: ChangeAnalysisRequest,
    x_session_token: Optional[str] = Header(default=None),
) -> ChangeImpactResult:
    _validate_change_request(body)

    session_id = body.session_id
    info = None
    scan_result = None
    intelligence_result = None
    if session_id:
        info = session_manager.get_info(session_id)
        if info is None:
            raise HTTPException(
                status_code=404,
                detail=err(SESSION_NOT_FOUND, "Session not found"),
            )
        _check_session_token(session_id, x_session_token)
        session_manager.append_timeline_event(session_id, "change_impact_started", "scanning", "Change impact analysis started")
        scan_result = session_manager.get_result(session_id)
        if scan_result is not None:
            try:
                from app.intelligence.intelligence_engine import IntelligenceEngine

                intelligence_result = IntelligenceEngine().analyze(
                    scan_result=scan_result,
                    session_id=session_id,
                    include_llm_explanation=False,
                )
            except Exception:
                intelligence_result = None

    analyzer = ChangeImpactAnalyzer()
    try:
        result = analyzer.analyze(body, scan_result=scan_result, intelligence_result=intelligence_result)
        if session_id:
            session_manager.append_timeline_event(session_id, "change_impact_completed", "completed", "Change impact analysis completed")
        return result
    except HTTPException:
        if session_id:
            session_manager.append_timeline_event(session_id, "change_impact_failed", "failed", "Change impact analysis failed")
        raise
    except Exception as exc:
        logger.error("Change impact analysis failed safely")
        if session_id:
            session_manager.append_timeline_event(session_id, "change_impact_failed", "failed", "Change impact analysis failed")
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Change impact analysis failed."),
        ) from exc


@router.post("/pr", response_model=PullRequestAnalysisResult)
async def analyze_pull_request(
    body: PullRequestAnalysisRequest,
    x_session_token: Optional[str] = Header(default=None),
) -> PullRequestAnalysisResult:
    if not str(body.diff_text or "").strip() and not list(body.changed_files or []):
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, "Provide diff_text or changed_files for PR analysis."),
        )
    if str(body.diff_text or "") and len(str(body.diff_text or "")) > config.scanner.change_max_diff_chars:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, f"Diff exceeds maximum length of {config.scanner.change_max_diff_chars} characters."),
        )

    session_id = body.session_id
    info = None
    scan_result = None
    intelligence = None
    graph = None
    repo_index = None

    if body.index_id:
        repo_index = repo_indexer.get_index(body.index_id)
        if repo_index is None:
            raise HTTPException(
                status_code=404,
                detail=err(SESSION_NOT_FOUND, "Repository index not found"),
            )
        session_id = session_id or repo_index.last_scan_session_id

    if session_id:
        _check_session_token(session_id, x_session_token)
        session_manager.append_timeline_event(session_id, "pr_analysis_started", "scanning", "PR analysis started")
        try:
            info, scan_result, intelligence, graph = _build_pr_context(session_id)
        except HTTPException:
            session_manager.append_timeline_event(session_id, "pr_analysis_failed", "failed", "PR analysis failed")
            raise

    try:
        result = PullRequestAnalyzer().analyze(
            body,
            scan_result=scan_result,
            intelligence_result=intelligence,
            graph_result=graph,
            repo_index=repo_index,
        )
        if body.include_llm_polish:
            orchestration = llm_orchestrator.orchestrate(
                OrchestrationRequest(
                    task_type="pr_review",
                    deterministic_payload={
                        "text": result.summary,
                        "warnings": result.warnings,
                        "risks": [result.risk_level, result.breaking_change_risk],
                        "affected_apis": result.affected_apis,
                        "affected_modules": result.affected_modules,
                        "reviewer_focus": result.reviewer_focus,
                    },
                    prompt_context={
                        "fallback_text": result.summary,
                        "must_keep_warnings_in_text": False,
                        "must_keep_risks_in_text": True,
                    },
                    max_rounds=1,
                    require_citations=False,
                )
            )
            result.warnings = list(dict.fromkeys([*(result.warnings or []), *(orchestration.warnings or [])]))
            if not orchestration.fallback_used and orchestration.text:
                result.summary = orchestration.text
        if session_id:
            session_manager.append_timeline_event(session_id, "pr_analysis_completed", "completed", "PR analysis completed")
        storage_backend.save_pr_analysis_result(session_id or body.index_id or (body.repo_url or "standalone-pr"), result.model_dump())
        return result
    except HTTPException:
        if session_id:
            session_manager.append_timeline_event(session_id, "pr_analysis_failed", "failed", "PR analysis failed")
        raise
    except Exception as exc:
        logger.error("PR analysis failed safely")
        if session_id:
            session_manager.append_timeline_event(session_id, "pr_analysis_failed", "failed", "PR analysis failed")
        raise HTTPException(
            status_code=500,
            detail=err(INTERNAL_ERROR, "PR analysis failed."),
        ) from exc


@router.post("/index/{session_id}", response_model=RepoIndex)
async def create_repo_index(
    session_id: str,
    x_session_token: Optional[str] = Header(default=None),
) -> RepoIndex:
    info, result = _require_completed_indexable_session(session_id, x_session_token)
    try:
        index = repo_indexer.create_index(session_id, info, result)
        session_manager.append_timeline_event(session_id, "repo_index_created", "completed", "Repository index created", {"index_id": index.index_id})
        return index
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Repo index creation failed safely")
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Repository index creation failed."),
        ) from exc


@router.get("/index/{index_id}", response_model=RepoIndex)
async def get_repo_index(index_id: str) -> RepoIndex:
    index = repo_indexer.get_index(index_id)
    if index is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Repository index not found"),
        )
    return index


@router.post("/index/{index_id}/delta", response_model=DeltaScanResult)
async def run_delta_scan(
    index_id: str,
    body: DeltaScanRequest,
    x_session_token: Optional[str] = Header(default=None),
) -> DeltaScanResult:
    if body.index_id != index_id:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", "Index id in path and body must match."),
        )
    index = repo_indexer.get_index(index_id)
    if index is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Repository index not found"),
        )
    base_info = session_manager.get_info(index.last_scan_session_id)
    if base_info is not None:
        _check_session_token(index.last_scan_session_id, x_session_token)
        session_manager.append_timeline_event(index.last_scan_session_id, "delta_scan_started", "scanning", "Delta scan started", {"index_id": index_id})
    try:
        delta = repo_indexer.run_delta(body)
        if base_info is not None:
            session_manager.append_timeline_event(index.last_scan_session_id, "delta_scan_completed", "completed", "Delta scan completed", {"new_session_id": delta.new_session_id})
        return delta
    except KeyError:
        if base_info is not None:
            session_manager.append_timeline_event(index.last_scan_session_id, "delta_scan_failed", "failed", "Delta scan failed")
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Repository index not found"),
        )
    except HTTPException:
        if base_info is not None:
            session_manager.append_timeline_event(index.last_scan_session_id, "delta_scan_failed", "failed", "Delta scan failed")
        raise
    except Exception as exc:
        logger.error("Delta scan failed safely")
        if base_info is not None:
            session_manager.append_timeline_event(index.last_scan_session_id, "delta_scan_failed", "failed", "Delta scan failed")
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Delta scan failed."),
        ) from exc


@router.get("/index/{index_id}/history")
async def get_index_history(index_id: str):
    index = repo_indexer.get_index(index_id)
    if index is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Repository index not found"),
        )
    return {
        "index_id": index_id,
        "history": repo_indexer.get_history(index_id),
    }


@router.get("/prd/{base_session_id}/diff/{target_session_id}")
async def get_prd_diff(
    base_session_id: str,
    target_session_id: str,
    format: str = "json",
    include_llm_polish: bool = False,
    x_session_token: Optional[str] = Header(default=None),
):
    if base_session_id == target_session_id:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", "Base and target session ids must be different."),
        )

    format = format.lower()
    if format not in {"json", "markdown"}:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", "Unsupported format. Allowed: json, markdown"),
        )

    base_info = session_manager.get_info(base_session_id)
    target_info = session_manager.get_info(target_session_id)
    if base_info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )
    if target_info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )

    _check_session_token(base_session_id, x_session_token)
    _check_session_token(target_session_id, x_session_token)
    session_manager.append_timeline_event(target_session_id, "prd_diff_started", "scanning", "PRD diff started")

    try:
        _, _, _, _, base_prd = _build_prd_for_session(base_session_id)
        _, _, _, _, target_prd = _build_prd_for_session(target_session_id)

        from app.docs.prd_diff_engine import PRDDiffEngine
        from fastapi.responses import Response

        engine = PRDDiffEngine()
        diff = engine.compare(base_prd, target_prd, base_session_id, target_session_id)
        if include_llm_polish:
            diff.warnings.append("LLM PRD diff polish is disabled in this phase; returned deterministic diff.")
        session_manager.append_timeline_event(target_session_id, "prd_diff_completed", "completed", "PRD diff completed")
        storage_backend.save_prd_diff(f"{base_session_id}:{target_session_id}", diff.model_dump())

        if format == "markdown":
            md = engine.to_markdown(diff)
            return Response(
                content=md,
                media_type="text/markdown",
                headers={"Content-Disposition": f'attachment; filename="ahal_prd_diff_{base_session_id}_{target_session_id}.md"'},
            )
        return diff
    except HTTPException:
        session_manager.append_timeline_event(target_session_id, "prd_diff_failed", "failed", "PRD diff failed")
        raise
    except Exception as exc:
        logger.error("PRD diff failed safely")
        session_manager.append_timeline_event(target_session_id, "prd_diff_failed", "failed", "PRD diff failed")
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "PRD diff generation failed."),
        ) from exc


@router.get("/graph/{session_id}", response_model=KnowledgeGraphResult)
async def get_graph(
    session_id: str,
    x_session_token: Optional[str] = Header(default=None),
) -> KnowledgeGraphResult:
    """
    Phase 3: Build a deterministic in-memory knowledge graph from a completed
    scan and Phase 2 intelligence. Does not rescan and does not call an LLM.
    """
    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )

    _check_session_token(session_id, x_session_token)

    result = session_manager.get_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress â€” stage: {info.stage} ({info.progress}%)",
                stage=info.stage,
                progress=info.progress,
            ),
        )

    try:
        from app.graph.graph_engine import KnowledgeGraphEngine
        from app.intelligence.intelligence_engine import IntelligenceEngine

        intelligence = IntelligenceEngine().analyze(
            scan_result=result,
            session_id=session_id,
            include_llm_explanation=False,
        )
        return KnowledgeGraphEngine().build(
            scan_result=result,
            intelligence_result=intelligence,
            session_id=session_id,
        )
    except Exception as exc:
        logger.error("Knowledge graph build failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Knowledge graph build failed"),
        ) from exc


@router.get("/onboard/{session_id}")
async def get_onboarding_report(
    session_id: str,
    audience: str = "new_engineer",
    time_budget_minutes: int = 30,
    format: str = "json",
    include_llm_orchestration: bool = False,
    x_session_token: Optional[str] = Header(default=None),
):
    audience = str(audience or "new_engineer").strip().lower()
    if audience not in {"new_engineer", "frontend", "backend", "qa", "devops"}:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, "Unsupported audience. Allowed: new_engineer, frontend, backend, qa, devops"),
        )
    if int(time_budget_minutes) <= 0:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, "time_budget_minutes must be greater than 0."),
        )
    format = str(format or "json").strip().lower()
    if format not in {"json", "markdown"}:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, "Unsupported format. Allowed: json, markdown"),
        )

    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )
    _check_session_token(session_id, x_session_token)
    if info.status != ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress â€” stage: {info.stage} ({info.progress}%)",
                stage=info.stage,
                progress=info.progress,
            ),
        )
    if info.session_type not in {"folder", "repo"}:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, "Onboarding report currently supports folder and repo sessions only."),
        )

    session_manager.append_timeline_event(session_id, "onboarding_started", "scanning", "Onboarding report generation started")
    try:
        _, report = _build_onboarding_for_session(session_id, audience, int(time_budget_minutes))
        if include_llm_orchestration:
            orchestration = llm_orchestrator.orchestrate(
                OrchestrationRequest(
                    task_type="onboarding",
                    deterministic_payload={
                        "text": report.summary,
                        "warnings": report.warnings,
                        "risks": report.gotchas,
                        "key_entry_points": report.key_entry_points,
                        "important_apis": report.important_apis,
                        "critical_modules": report.critical_modules,
                    },
                    prompt_context={
                        "fallback_text": report.summary,
                        "audience": report.audience,
                        "must_keep_warnings_in_text": False,
                        "must_keep_risks_in_text": True,
                    },
                    max_rounds=1,
                    require_citations=False,
                )
            )
            report.warnings = list(dict.fromkeys([*(report.warnings or []), *(orchestration.warnings or [])]))
            if not orchestration.fallback_used and orchestration.text:
                report.summary = orchestration.text
        session_manager.append_timeline_event(session_id, "onboarding_completed", "completed", "Onboarding report generation completed")
        storage_backend.save_onboarding_report(session_id, report.model_dump())
        if format == "markdown":
            return Response(
                content=render_onboarding_markdown(report),
                media_type="text/markdown",
                headers={"Content-Disposition": f'attachment; filename="ahal_onboarding_{session_id}.md"'},
            )
        return report
    except HTTPException:
        session_manager.append_timeline_event(session_id, "onboarding_failed", "failed", "Onboarding report generation failed")
        raise
    except Exception as exc:
        logger.error("Onboarding report generation failed safely")
        session_manager.append_timeline_event(session_id, "onboarding_failed", "failed", "Onboarding report generation failed")
        raise HTTPException(
            status_code=500,
            detail=err(INTERNAL_ERROR, "Onboarding report generation failed."),
        ) from exc


@router.post("/chat/{session_id}", response_model=ChatAnswer)
async def analyze_chat(
    session_id: str,
    body: ChatRequest,
    include_llm_orchestration: bool = False,
    x_session_token: Optional[str] = Header(default=None),
) -> ChatAnswer:
    """
    Phase 4: Answer graph-aware questions about a completed scan using only
    deterministic retrieval context and optional Gemini generation.
    """
    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )

    _check_session_token(session_id, x_session_token)

    question = (body.question or "").strip()
    if not question:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", "Question must not be empty"),
        )
    
    max_chars = config.scanner.chat_max_question_chars
    if len(question) > max_chars:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", f"Question exceeds maximum length of {max_chars} characters"),
        )

    result = session_manager.get_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress — stage: {info.stage} ({info.progress}%)",
                stage=info.stage,
                progress=info.progress,
            ),
        )

    if info.session_type == "code":
        code_result = session_manager.get_artifact(session_id, "code_result")
        if code_result is None:
            raise HTTPException(
                status_code=500,
                detail=err("INTERNAL_ERROR", "Code session result is missing."),
            )
        if body.include_history:
            from app.chat.memory.chat_memory import chat_memory
            from app.chat.models import ChatMessage

            chat_memory.add_message(session_id, ChatMessage(role="user", content=question))
        answer = _code_chat_answer(question, code_result)
        if body.include_history:
            from app.chat.memory.chat_memory import chat_memory
            from app.chat.models import ChatMessage

            chat_memory.add_message(session_id, ChatMessage(role="assistant", content=answer.answer))
        return answer

    try:
        from app.graph.graph_engine import KnowledgeGraphEngine
        from app.intelligence.intelligence_engine import IntelligenceEngine

        intelligence = IntelligenceEngine().analyze(
            scan_result=result,
            session_id=session_id,
            include_llm_explanation=False,
        )
        graph = KnowledgeGraphEngine().build(
            scan_result=result,
            intelligence_result=intelligence,
            session_id=session_id,
        )
        max_context_items = min(body.max_context_items, config.scanner.chat_max_context_items)
        return chat_engine.answer(
            question=question,
            scan_result=result,
            intelligence_result=intelligence,
            graph_result=graph,
            session_id=session_id,
            include_history=body.include_history,
            max_context_items=max_context_items,
            include_llm_orchestration=include_llm_orchestration,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", str(exc)),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Chat analysis failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "Chat analysis failed"),
        ) from exc

# ── GET /analyze/prd/{session_id} (Phase 5) ──────────────────────

from fastapi.responses import Response

@router.get("/prd/{session_id}")
async def get_prd(
    session_id: str,
    format: str = "json",
    include_llm_polish: bool = False,
    x_session_token: Optional[str] = Header(default=None),
):
    """
    Phase 5: Generate PRD in requested format (json, markdown, latex).
    """
    format = format.lower()
    if format not in ("json", "markdown", "latex", "pdf"):
        raise HTTPException(
            status_code=400,
            detail=err("INVALID_REQUEST", f"Unsupported format: {format}. Allowed: json, markdown, latex, pdf"),
        )

    info = session_manager.get_info(session_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "Session not found"),
        )

    _check_session_token(session_id, x_session_token)

    if info.status != ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=202,
            detail=err(
                SCAN_IN_PROGRESS,
                f"Scan in progress — stage: {info.stage} ({info.progress}%)",
                stage=info.stage,
                progress=info.progress,
            ),
        )

    result = session_manager.get_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=500,
            detail=err(
                "INTERNAL_ERROR",
                "Scan is marked complete but result is missing."
            ),
        )

    try:
        from app.graph.graph_engine import KnowledgeGraphEngine
        from app.intelligence.intelligence_engine import IntelligenceEngine
        from app.docs.prd_engine import PRDEngine
        from app.docs.exporters.markdown_exporter import MarkdownExporter
        from app.docs.exporters.latex_exporter import LatexExporter
        from app.docs.exporters.pdf_exporter import PDFExporter

        intelligence = IntelligenceEngine().analyze(
            scan_result=result,
            session_id=session_id,
            include_llm_explanation=False,
        )
        graph = KnowledgeGraphEngine().build(
            scan_result=result,
            intelligence_result=intelligence,
            session_id=session_id,
        )
        prd_engine = PRDEngine()
        prd = prd_engine.generate(
            scan_result=result,
            intelligence_result=intelligence,
            graph_result=graph,
            session_id=session_id,
        )

        if format == "json":
            if include_llm_polish:
                prd.warnings.append("LLM polish is only applied to markdown output.")
            return prd
        elif format == "markdown":
            md = MarkdownExporter().export(prd)
            if include_llm_polish:
                from app.docs.llm.prd_polish_service import PRDPolishService
                md, warnings = PRDPolishService().polish(prd, md)
                if warnings:
                    md += "\n\n### Polish Warnings\n"
                    for w in warnings:
                        md += f"- {w}\n"
            return Response(
                content=md,
                media_type="text/markdown",
                headers={"Content-Disposition": f'attachment; filename="ahal_prd_{session_id}.md"'}
            )
        elif format == "latex":
            tex = LatexExporter().export(prd)
            if include_llm_polish:
                tex += "\n% LLM polish is only applied to markdown output.\n"
            return Response(
                content=tex,
                media_type="text/x-tex",
                headers={"Content-Disposition": f'attachment; filename="ahal_prd_{session_id}.tex"'}
            )
        elif format == "pdf":
            polished_text = None
            if include_llm_polish:
                try:
                    from app.docs.llm.pdf_polish_service import PDFPolishService
                    polished_text = PDFPolishService().polish_for_pdf(prd)
                except Exception:
                    logger.info("PDF LLM polish unavailable; using deterministic PDF.")
                    polished_text = None

            pdf_bytes = PDFExporter().export(prd, polished_text=polished_text)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="ahal_prd_{session_id}.pdf"'}
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("PRD generation failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=err("INTERNAL_ERROR", "PRD generation failed"),
        ) from exc


@router.post("/prd/templates/validate", response_model=PRDTemplate)
async def validate_prd_template(body: dict) -> PRDTemplate:
    try:
        return template_engine.validate_template(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, str(exc)),
        ) from exc
    except Exception as exc:
        logger.error("PRD template validation failed safely")
        raise HTTPException(
            status_code=500,
            detail=err(INTERNAL_ERROR, "PRD template validation failed."),
        ) from exc


@router.post("/prd/{session_id}/render-template", response_model=RenderedTemplateResult)
async def render_prd_template(
    session_id: str,
    body: dict,
    x_session_token: Optional[str] = Header(default=None),
) -> RenderedTemplateResult:
    _check_session_token(session_id, x_session_token)
    try:
        template = template_engine.validate_template(body)
        _info, result, intelligence, graph, prd = _build_prd_for_session(session_id)
        onboarding = OnboardingGenerator().generate(
            session_id=session_id,
            scan_result=result,
            intelligence_result=intelligence,
            graph_result=graph,
            prd_result=prd,
            audience="new_engineer",
            time_budget_minutes=30,
        )
        test_gaps = None
        if _info.session_type in {"folder", "repo"}:
            test_gaps = test_gap_detector.detect(
                session_id=session_id,
                scan_result=result,
                intelligence_result=intelligence,
                include_low_priority=False,
            )
        return template_engine.render_markdown(
            prd_result=prd,
            template=template,
            extra_context={"onboarding": onboarding, "test_gaps": test_gaps},
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, str(exc)),
        ) from exc
    except Exception as exc:
        logger.error("PRD template render failed safely")
        raise HTTPException(
            status_code=500,
            detail=err(INTERNAL_ERROR, "PRD template rendering failed."),
        ) from exc
