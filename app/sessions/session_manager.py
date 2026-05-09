"""
AHAL AI — Session Manager  [HARDENED v4]

Fixes applied:
  Fix 1 — Atomic create_session_if_capacity() — single lock span
  Fix 2 — Lock-protected is_cancelled() — formally thread-safe
  Fix 5 — Per-session access_token via secrets.token_hex(32)
  Fix 7 — Metric counters: total/completed/failed/cancelled + rolling scan times
"""

from __future__ import annotations

import hmac
import logging
import secrets
import threading
import time
import uuid
from collections import deque
from typing import Deque, Dict, NamedTuple, Optional, Set

from app.config import config
from app.models.file_schema import ScanResult, ScanStage, ScanStatus, SessionInfo
from app.sessions.models import SessionTimelineEvent, SessionType, utc_now_iso
from app.storage import storage_backend
from app.storage.serialization import safe_model_dump
from app.utils.logger import log_error, log_info, log_stage

logger = logging.getLogger("ahal.sessions")

# Statuses that count as "active" (consuming a worker slot)
_ACTIVE_STATUSES = {ScanStatus.PENDING, ScanStatus.SCANNING}

# Rolling scan-time window cap
_MAX_SCAN_TIME_SAMPLES = 100


class SessionCreateResult(NamedTuple):
    """Return value of create_session_if_capacity()."""
    session_id: str
    access_token: str  # empty string when token mode is disabled


class _SessionEntry:
    """Internal session record."""

    __slots__ = (
        "session_id", "access_token", "status", "stage",
        "progress", "processed_files", "total_files",
        "result", "created_at", "message", "session_type",
        "source_name", "updated_at", "confidence", "repo_visibility", "warnings",
        "timeline", "artifacts",
    )

    def __init__(self, session_id: str, session_type: SessionType = "folder", source_name: str = "") -> None:
        self.session_id   = session_id
        self.access_token = secrets.token_hex(32)
        self.status       = ScanStatus.PENDING
        self.stage: str   = ScanStage.INITIALIZING.value
        self.progress     = 0
        self.processed_files = 0
        self.total_files  = 0
        self.result: Optional[ScanResult] = None
        self.created_at   = time.monotonic()
        self.message      = "Scan queued"
        self.session_type: SessionType = session_type
        self.source_name = source_name
        self.updated_at = utc_now_iso()
        self.confidence = "low"
        self.repo_visibility = "unknown"
        self.warnings = []
        self.timeline = [
            SessionTimelineEvent(
                timestamp=self.updated_at,
                stage="session_created",
                status=ScanStatus.PENDING.value,
                message="Session created",
                metadata={"session_type": session_type, "source_name": source_name},
            )
        ]
        self.artifacts = {}


class SessionManager:
    """
    Thread-safe scan session store.

    Public API:
      create_session_if_capacity(max_active) → SessionCreateResult | None  [atomic]
      create_session()                       → str  [internal / test use]
      cancel_session(session_id)             → bool
      is_cancelled(session_id)               → bool  [lock-protected, Fix 2]
      get_active_session_count()             → int   [for metrics]
      set_stage / update_progress / set_result / set_failed
      get_info / get_result
      get_access_token / validate_token      [Fix 5]
      get_metrics                            [Fix 7]
    """

    def __init__(self) -> None:
        self._lock     = threading.Lock()
        self._sessions: Dict[str, _SessionEntry] = {}
        self._cancelled: Set[str] = set()

        # ── Metric counters (Fix 7) ───────────────────────────────
        self._total_created:    int = 0
        self._total_completed:  int = 0
        self._total_failed:     int = 0
        self._total_cancelled:  int = 0
        self._scan_times: Deque[float] = deque(maxlen=_MAX_SCAN_TIME_SAMPLES)

    # ── Atomic session creation (Fix 1) ──────────────────────────

    def create_session_if_capacity(
        self,
        max_active: int | None = None,
        session_type: SessionType = "folder",
        source_name: str = "",
    ) -> Optional[SessionCreateResult]:
        """
        Atomically check capacity and create a session in one lock acquisition.
        Returns SessionCreateResult(session_id, access_token) on success.
        Returns None if capacity is exceeded — caller should return 'rejected'.

        The access_token is always generated internally; the API layer decides
        whether to surface it in the response based on config.
        """
        limit = max_active if max_active is not None else config.scanner.max_active_sessions

        sid = uuid.uuid4().hex
        entry = _SessionEntry(sid, session_type=session_type, source_name=source_name)

        with self._lock:
            # 1. Evict stale sessions first to free slots
            self._evict_stale_locked()

            # 2. Count active sessions
            active = sum(
                1 for e in self._sessions.values()
                if e.status in _ACTIVE_STATUSES
            )

            # 3. Reject if over limit
            if active >= limit:
                return None

            # 4. Insert new session
            self._sessions[sid] = entry
            self._total_created += 1

        log_info("Session created (atomic)", session_id=sid)
        self._persist_session_snapshot(sid, entry)
        return SessionCreateResult(
            session_id=sid,
            access_token=entry.access_token,
        )

    def create_session(self, session_type: SessionType = "folder", source_name: str = "") -> str:
        """
        Create a new session without capacity check.
        Preserved for internal use and tests.
        """
        sid = uuid.uuid4().hex
        entry = _SessionEntry(sid, session_type=session_type, source_name=source_name)
        with self._lock:
            self._sessions[sid] = entry
            self._evict_stale_locked()
            self._total_created += 1
        log_info("Session created", session_id=sid)
        self._persist_session_snapshot(sid, entry)
        return sid

    # ── Security — Access Token (Fix 5) ──────────────────────────

    def get_access_token(self, session_id: str) -> Optional[str]:
        """Return the raw access token for a session (for testing only)."""
        with self._lock:
            entry = self._sessions.get(session_id)
            return entry.access_token if entry else None

    def validate_token(self, session_id: str, token: str) -> bool:
        """
        Constant-time token comparison via hmac.compare_digest.
        Returns False if session not found or token does not match.
        """
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return False
            # compare_digest requires same-type strings
            return hmac.compare_digest(
                entry.access_token.encode(),
                token.encode(),
            )

    # ── Cancellation (Fix 2 — lock-protected read) ───────────────

    def cancel_session(self, session_id: str) -> bool:
        """
        Mark a session as cancelled.
        Returns True if session existed and was not already terminal.
        """
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return False
            if entry.status not in _ACTIVE_STATUSES:
                return False
            self._cancelled.add(session_id)
            entry.status  = ScanStatus.FAILED
            entry.stage   = ScanStage.FAILED.value
            entry.message = "Cancelled by user"
            entry.updated_at = utc_now_iso()
            entry.result  = ScanResult(
                session_id=session_id,
                status=ScanStatus.FAILED,
                progress=entry.progress,
                errors=["Cancelled by user"],
            )
            self._total_cancelled += 1
        log_info("Session cancelled", session_id=session_id)
        return True

    def is_cancelled(self, session_id: str) -> bool:
        """
        Lock-protected cancellation check (Fix 2).
        Called frequently in scan loops — lock overhead is negligible vs I/O.
        """
        with self._lock:
            return session_id in self._cancelled

    # ── Backpressure count (kept for metrics) ────────────────────

    def get_active_session_count(self) -> int:
        """Return number of PENDING + SCANNING sessions."""
        with self._lock:
            return sum(
                1 for e in self._sessions.values()
                if e.status in _ACTIVE_STATUSES
            )

    # ── Stage updates ────────────────────────────────────────────

    def set_stage(self, session_id: str, stage: ScanStage, message: str = "") -> None:
        """Advance the named pipeline stage."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return
            entry.stage  = stage.value
            entry.status = ScanStatus.SCANNING
            entry.updated_at = utc_now_iso()
            if message:
                entry.message = message
            entry.timeline.append(SessionTimelineEvent(
                timestamp=entry.updated_at,
                stage=stage.value.replace(" ", "_"),
                status=entry.status.value,
                message=message or stage.value,
                metadata={},
            ))
        log_stage(session_id, stage.value)
        self._persist_session(session_id)

    # ── Progress updates ─────────────────────────────────────────

    def update_progress(
        self,
        session_id: str,
        progress: int,
        message: str = "",
        processed_files: int = 0,
        total_files: int = 0,
    ) -> None:
        """Update progress (0–100) and optional file counters."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return
            entry.progress = max(0, min(100, progress))
            entry.status   = ScanStatus.SCANNING
            entry.updated_at = utc_now_iso()
            if processed_files:
                entry.processed_files = processed_files
            if total_files:
                entry.total_files = total_files
            if message:
                entry.message = message
        self._persist_session(session_id)

    def set_result(self, session_id: str, result: ScanResult) -> None:
        """Mark session as complete and store the result."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return
            duration = time.monotonic() - entry.created_at
            entry.result  = result
            entry.status  = result.status
            entry.stage   = ScanStage.COMPLETED.value
            entry.progress = 100
            entry.message = f"Scan {result.status.value}"
            entry.updated_at = utc_now_iso()
            entry.warnings = list(getattr(result, "errors", []) or [])
            entry.timeline.append(SessionTimelineEvent(
                timestamp=entry.updated_at,
                stage="completed",
                status=result.status.value,
                message=f"Scan {result.status.value}",
                metadata={},
            ))
            self._scan_times.append(duration)
            if result.status == ScanStatus.COMPLETED:
                self._total_completed += 1
            else:
                # PARTIAL counts as a non-full success
                self._total_completed += 1
        self._cancelled.discard(session_id)
        log_info(f"Scan completed → {result.status.value}", session_id=session_id)
        self._persist_session(session_id)
        storage_backend.set_result(session_id, safe_model_dump(result))

    def set_failed(self, session_id: str, error: str) -> None:
        """Mark session as failed with a minimal stored result."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return
            entry.status  = ScanStatus.FAILED
            entry.stage   = ScanStage.FAILED.value
            entry.message = error
            entry.updated_at = utc_now_iso()
            entry.warnings = [error]
            entry.result  = ScanResult(
                session_id=session_id,
                status=ScanStatus.FAILED,
                progress=entry.progress,
                errors=[error],
            )
            entry.timeline.append(SessionTimelineEvent(
                timestamp=entry.updated_at,
                stage="failed",
                status=ScanStatus.FAILED.value,
                message=error,
                metadata={},
            ))
            self._total_failed += 1
        self._cancelled.discard(session_id)
        log_error(f"Scan failed: {error}", session_id=session_id)
        self._persist_session(session_id)
        storage_backend.set_result(session_id, safe_model_dump(self.get_result(session_id)))

    # ── Queries ──────────────────────────────────────────────────

    def get_info(self, session_id: str) -> Optional[SessionInfo]:
        """Get lightweight session info for polling."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return None
            return SessionInfo(
                session_id=entry.session_id,
                session_type=entry.session_type,
                status=entry.status,
                stage=entry.stage,
                progress=entry.progress,
                processed_files=entry.processed_files,
                total_files=entry.total_files,
                message=entry.message,
                source_name=entry.source_name,
                created_at=entry.timeline[0].timestamp if entry.timeline else "",
                updated_at=entry.updated_at,
                confidence=entry.confidence,
                repo_visibility=entry.repo_visibility,
                warnings=list(entry.warnings),
            )

    def get_result(self, session_id: str) -> Optional[ScanResult]:
        """Get the full scan result. Returns None if not yet complete."""
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return None
            return entry.result

    def append_timeline_event(self, session_id: str, stage: str, status: str, message: str, metadata: Optional[dict] = None) -> None:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return
            entry.updated_at = utc_now_iso()
            entry.timeline.append(SessionTimelineEvent(
                timestamp=entry.updated_at,
                stage=stage,
                status=status,
                message=message,
                metadata=metadata or {},
            ))
        self._persist_session(session_id)

    def get_timeline(self, session_id: str) -> list[SessionTimelineEvent]:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return []
            return list(entry.timeline)

    def set_artifact(self, session_id: str, key: str, value) -> None:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return
            entry.artifacts[key] = value
            entry.updated_at = utc_now_iso()
        self._persist_session(session_id)

    def get_artifact(self, session_id: str, key: str, default=None):
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return default
            return entry.artifacts.get(key, default)

    def set_session_metadata(self, session_id: str, **kwargs) -> None:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return
            for key, value in kwargs.items():
                if hasattr(entry, key):
                    setattr(entry, key, value)
            entry.updated_at = utc_now_iso()
        self._persist_session(session_id)

    # ── Metrics (Fix 7) ──────────────────────────────────────────

    def get_metrics(self) -> dict:
        """
        Return a snapshot of runtime metrics for GET /metrics.
        All reads happen under one lock acquisition.
        """
        with self._lock:
            active = sum(
                1 for e in self._sessions.values()
                if e.status in _ACTIVE_STATUSES
            )
            total = len(self._sessions)
            total_created   = self._total_created
            total_completed = self._total_completed
            total_failed    = self._total_failed
            total_cancelled = self._total_cancelled
            scan_times      = list(self._scan_times)

        avg = (sum(scan_times) / len(scan_times)) if scan_times else None

        return {
            "active_sessions":         active,
            "total_sessions":          total_created,
            "completed_sessions":      total_completed,
            "failed_sessions":         total_failed,
            "cancelled_sessions":      total_cancelled,
            "average_scan_time_seconds": round(avg, 3) if avg is not None else None,
        }

    # ── Eviction (internal — must be called under lock) ───────────

    def _evict_stale_locked(self) -> None:
        """
        Remove sessions older than TTL.
        MUST be called while holding self._lock.
        """
        ttl = config.scanner.session_ttl_seconds
        now = time.monotonic()
        stale = [
            sid for sid, e in self._sessions.items()
            if (now - e.created_at) > ttl
        ]
        for sid in stale:
            del self._sessions[sid]
            self._cancelled.discard(sid)
        if stale:
            logger.info("Evicted %d stale sessions", len(stale))

    def _persist_session(self, session_id: str) -> None:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return
        self._persist_session_snapshot(session_id, entry)

    def _persist_session_snapshot(self, session_id: str, entry: _SessionEntry) -> None:
        payload = {
            "session_id": session_id,
            "status": entry.status.value if hasattr(entry.status, "value") else str(entry.status),
            "stage": entry.stage,
            "progress": entry.progress,
            "processed_files": entry.processed_files,
            "total_files": entry.total_files,
            "message": entry.message,
            "session_type": entry.session_type,
            "source_name": entry.source_name,
            "created_at": entry.timeline[0].timestamp if entry.timeline else "",
            "updated_at": entry.updated_at,
            "confidence": entry.confidence,
            "repo_visibility": entry.repo_visibility,
            "warnings": list(entry.warnings),
            "timeline": [item.model_dump() for item in entry.timeline],
        }
        if storage_backend.get_session(session_id) is None:
            storage_backend.create_session(session_id, payload)
        else:
            storage_backend.update_session(session_id, payload)


# ── Singleton ────────────────────────────────────────────────────

session_manager = SessionManager()
