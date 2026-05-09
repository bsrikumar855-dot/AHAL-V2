"""
AHAL AI — File Schema Models
Pydantic models for file metadata, scan results, and session state.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from app.sessions.models import SessionType


class Priority(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ScanStatus(str, enum.Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ScanStage(str, enum.Enum):
    """Named pipeline stages for detailed progress reporting."""
    INITIALIZING   = "initializing"
    CLONING_REPO   = "cloning repo"
    EXTRACTING_ZIP = "extracting zip"
    SCANNING_FILES = "scanning files"
    LOADING_CONTENT = "loading content"
    COMPLETED      = "completed"
    FAILED         = "failed"


class InputType(str, enum.Enum):
    ZIP          = "zip"
    SINGLE_FILE  = "single_file"
    GITHUB_REPO  = "github_repo"


# ─── Request / Response ────────────────────────────────────────────


class ScanRequest(BaseModel):
    """Incoming scan request."""
    input_type: InputType
    github_url: Optional[str] = None
    # For ZIP / single‑file the upload is handled via multipart form.


class FileMetadata(BaseModel):
    """Metadata for a single discovered file."""
    path: str
    size_bytes: int
    extension: str = ""
    priority: Priority = Priority.LOW
    is_binary: bool = False
    skipped: bool = False
    skip_reason: Optional[str] = None


class ScanStats(BaseModel):
    """Aggregate statistics for a completed scan."""
    total_files_discovered: int = 0
    files_included: int = 0
    files_skipped: int = 0
    total_size_bytes: int = 0
    included_size_bytes: int = 0
    high_priority_count: int = 0
    medium_priority_count: int = 0
    low_priority_count: int = 0
    errors: List[str] = Field(default_factory=list)
    scan_duration_seconds: float = 0.0


class ScanResult(BaseModel):
    """Full scan result returned to the client."""
    session_id: str
    status: ScanStatus = ScanStatus.PENDING
    progress: int = 0  # 0‑100
    stats: ScanStats = Field(default_factory=ScanStats)
    files: List[FileMetadata] = Field(default_factory=list)
    contents: Dict[str, str] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)


class SessionInfo(BaseModel):
    """Lightweight session info for polling."""
    session_id: str
    session_type: SessionType = "folder"
    status: ScanStatus
    stage: str = "initializing"
    progress: int = 0
    processed_files: int = 0
    total_files: int = 0
    message: str = ""
    source_name: str = ""
    created_at: str = ""
    updated_at: str = ""
    confidence: str = "low"
    repo_visibility: str = "unknown"
    warnings: List[str] = Field(default_factory=list)
