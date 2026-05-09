from __future__ import annotations

import hashlib
import hmac
import logging
import uuid

from fastapi import APIRouter, Header, HTTPException, Request

from app.changes.models import ChangedFileInput
from app.config import config
from app.indexing.models import DeltaChangedFile, DeltaScanRequest
from app.indexing.repo_indexer import repo_indexer
from app.pr import PullRequestAnalysisRequest, PullRequestAnalyzer
from app.sessions.models import utc_now_iso
from app.sessions.session_manager import session_manager
from app.storage import storage_backend
from app.utils.errors import INTERNAL_ERROR, INVALID_REQUEST, SESSION_NOT_FOUND, UNAUTHORIZED, err
from app.webhooks.models import GitHubWebhookEvent, WebhookProcessResult, WebhookTriggeredResult

logger = logging.getLogger("ahal.webhooks.github")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])
_EVENTS: list[GitHubWebhookEvent] = []


@router.post("/github", response_model=WebhookProcessResult)
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
):
    if not config.scanner.github_webhook_enabled:
        raise HTTPException(
            status_code=404,
            detail=err(SESSION_NOT_FOUND, "GitHub webhook listener is disabled."),
        )

    raw_body = await request.body()
    _verify_signature(raw_body, x_hub_signature_256)

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, "Malformed GitHub webhook payload."),
        ) from exc

    event_type = str(x_github_event or "").strip().lower()
    if not event_type:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, "Missing X-GitHub-Event header."),
        )

    try:
        if event_type == "ping":
            return _record_and_return(event_type, payload, warnings=[])
        if event_type == "push":
            return _handle_push(payload)
        if event_type == "pull_request":
            return _handle_pull_request(payload)
        return _record_and_return(event_type, payload, warnings=["Unsupported GitHub webhook event was accepted without action."])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("GitHub webhook processing failed safely")
        raise HTTPException(
            status_code=500,
            detail=err(INTERNAL_ERROR, "GitHub webhook processing failed."),
        ) from exc


def _verify_signature(raw_body: bytes, signature: str | None) -> None:
    secret = str(config.scanner.github_webhook_secret or "")
    if not secret:
        return
    if not signature:
        raise HTTPException(
            status_code=401,
            detail=err(UNAUTHORIZED, "Missing GitHub webhook signature."),
        )
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=401,
            detail=err(UNAUTHORIZED, "Invalid GitHub webhook signature."),
        )


def _handle_push(payload: dict) -> WebhookProcessResult:
    repo_url = _repo_url(payload)
    if not repo_url:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, "Push webhook payload is missing repository URL."),
        )
    index = repo_indexer.find_by_repo_url(repo_url)
    warnings = []
    triggered = WebhookTriggeredResult(delta_scan=False, pr_analysis=False)
    branch = str(payload.get("ref", "") or "").split("/")[-1] or None
    visibility = _repo_visibility(payload)
    if index is None:
        warnings.append("No repo index found for webhook repository.")
        return _record_and_return("push", payload, warnings=warnings, branch=branch)

    if visibility != "unknown":
        session_manager.set_session_metadata(index.last_scan_session_id, repo_visibility=visibility)

    changed_files = _push_changed_files(payload)
    session_manager.append_timeline_event(index.last_scan_session_id, "github_webhook_received", "completed", "GitHub push webhook received")
    session_manager.append_timeline_event(index.last_scan_session_id, "webhook_delta_scan_started", "scanning", "Webhook-triggered delta scan started")
    repo_indexer.run_delta(DeltaScanRequest(index_id=index.index_id, changed_files=changed_files, force_full_rescan=False))
    session_manager.append_timeline_event(index.last_scan_session_id, "webhook_delta_scan_completed", "completed", "Webhook-triggered delta scan completed")
    triggered.delta_scan = True
    event = _record_event("push", repo_url, payload.get("action"), branch, None, "processed", warnings)
    return WebhookProcessResult(ok=True, event_type=event.event_type, repo_url=repo_url, action=event.action, triggered=triggered, warnings=warnings)


def _handle_pull_request(payload: dict) -> WebhookProcessResult:
    repo_url = _repo_url(payload)
    if not repo_url:
        raise HTTPException(
            status_code=400,
            detail=err(INVALID_REQUEST, "Pull request webhook payload is missing repository URL."),
        )
    pr = payload.get("pull_request") or {}
    index = repo_indexer.find_by_repo_url(repo_url)
    warnings = []
    triggered = WebhookTriggeredResult(delta_scan=False, pr_analysis=False)
    changed_files = _pr_changed_files(payload)
    diff_text = str(pr.get("diff_text") or payload.get("diff_text") or "")
    branch = str(((pr.get("head") or {}).get("ref")) or "")
    pr_number = pr.get("number") or payload.get("number")
    visibility = _repo_visibility(payload)
    if not changed_files and not diff_text:
        warnings.append("Insufficient PR diff data was provided in the webhook payload.")
        return _record_and_return("pull_request", payload, warnings=warnings, branch=branch or None, pr_number=pr_number)

    scan_result = None
    intelligence = None
    graph = None
    session_id = None
    if index is not None:
        session_id = index.last_scan_session_id
        info = session_manager.get_info(session_id)
        scan_result = session_manager.get_result(session_id)
        if info is not None and scan_result is not None:
            if visibility != "unknown":
                session_manager.set_session_metadata(session_id, repo_visibility=visibility)
            from app.intelligence.intelligence_engine import IntelligenceEngine
            from app.graph.graph_engine import KnowledgeGraphEngine

            intelligence = IntelligenceEngine().analyze(scan_result=scan_result, session_id=session_id, include_llm_explanation=False)
            graph = KnowledgeGraphEngine().build(scan_result=scan_result, intelligence_result=intelligence, session_id=session_id)
            session_manager.append_timeline_event(session_id, "github_webhook_received", "completed", "GitHub pull_request webhook received")
            session_manager.append_timeline_event(session_id, "webhook_pr_analysis_started", "scanning", "Webhook-triggered PR analysis started")

    result = PullRequestAnalyzer().analyze(
        PullRequestAnalysisRequest(
            repo_url=repo_url,
            session_id=session_id,
            index_id=index.index_id if index is not None else None,
            pr_number=pr_number,
            title=pr.get("title") or payload.get("title"),
            description=pr.get("body") or payload.get("description"),
            diff_text=diff_text or None,
            changed_files=changed_files,
            base_ref=((pr.get("base") or {}).get("ref")) or payload.get("base_ref"),
            head_ref=((pr.get("head") or {}).get("ref")) or payload.get("head_ref"),
            include_llm_polish=False,
        ),
        scan_result=scan_result,
        intelligence_result=intelligence,
        graph_result=graph,
        repo_index=index,
    )
    storage_backend.save_pr_analysis_result(str(pr_number or uuid.uuid4().hex), result.model_dump())
    if session_id:
        session_manager.append_timeline_event(session_id, "webhook_pr_analysis_completed", "completed", "Webhook-triggered PR analysis completed")
    triggered.pr_analysis = True
    event = _record_event("pull_request", repo_url, payload.get("action"), branch or None, pr_number, "processed", warnings)
    return WebhookProcessResult(ok=True, event_type=event.event_type, repo_url=repo_url, action=event.action, triggered=triggered, warnings=warnings)


def _record_and_return(event_type: str, payload: dict, warnings: list[str], branch: str | None = None, pr_number: int | None = None) -> WebhookProcessResult:
    repo_url = _repo_url(payload)
    event = _record_event(event_type, repo_url, payload.get("action"), branch, pr_number, "accepted", warnings)
    return WebhookProcessResult(ok=True, event_type=event.event_type, repo_url=repo_url, action=event.action, triggered=WebhookTriggeredResult(), warnings=warnings)


def _record_event(event_type: str, repo_url: str | None, action, branch: str | None, pr_number: int | None, status: str, warnings: list[str]) -> GitHubWebhookEvent:
    event = GitHubWebhookEvent(
        event_id=uuid.uuid4().hex,
        event_type=event_type,
        repo_url=repo_url,
        action=str(action) if action is not None else None,
        branch=branch,
        pr_number=pr_number,
        status=status,
        warnings=warnings,
        created_at=utc_now_iso(),
    )
    _EVENTS.append(event)
    return event


def _repo_url(payload: dict) -> str | None:
    repo = payload.get("repository") or {}
    return repo.get("html_url") or repo.get("clone_url")


def _repo_visibility(payload: dict) -> str:
    repo = payload.get("repository") or {}
    if "private" not in repo:
        return "unknown"
    return "private" if bool(repo.get("private")) else "public"


def _push_changed_files(payload: dict) -> list[DeltaChangedFile]:
    rows: list[DeltaChangedFile] = []
    for commit in payload.get("commits", []) or []:
        for path in commit.get("added", []) or []:
            rows.append(DeltaChangedFile(path=path, status="added"))
        for path in commit.get("modified", []) or []:
            rows.append(DeltaChangedFile(path=path, status="modified"))
        for path in commit.get("removed", []) or []:
            rows.append(DeltaChangedFile(path=path, status="deleted"))
    deduped = {}
    for item in rows:
        deduped[item.path] = item
    return list(deduped.values())


def _pr_changed_files(payload: dict) -> list[ChangedFileInput]:
    raw = payload.get("changed_files") or (payload.get("pull_request") or {}).get("changed_files") or []
    rows = []
    for item in raw:
        if isinstance(item, str):
            rows.append(ChangedFileInput(path=item, status="modified"))
            continue
        if isinstance(item, dict):
            rows.append(
                ChangedFileInput(
                    path=str(item.get("path") or item.get("filename") or ""),
                    before=item.get("before"),
                    after=item.get("after"),
                    status=str(item.get("status") or "modified"),
                )
            )
    return [item for item in rows if item.path]
