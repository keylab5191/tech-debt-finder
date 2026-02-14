"""Pydantic data models for tech debt issues and scan reports."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Issue severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Category(str, Enum):
    """Issue category types."""
    CODE_SMELL = "code_smell"
    COMPLEXITY = "complexity"
    NAMING = "naming"
    STRUCTURE = "structure"
    DUPLICATION = "duplication"
    ERROR_HANDLING = "error_handling"
    SECURITY = "security"
    PERFORMANCE = "performance"
    READABILITY = "readability"
    BEST_PRACTICES = "best_practices"


class Issue(BaseModel):
    """A single tech debt issue found in a file."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    file_path: str
    line_range: Optional[str] = None
    severity: Severity
    category: Category
    title: str
    description: str
    suggestion: str
    status: str = "open"


class ScanResult(BaseModel):
    """Result of scanning a single file."""
    file_path: str
    issues: list[Issue] = Field(default_factory=list)
    scanned_at: datetime = Field(default_factory=datetime.now)
    model_used: str = ""
    performance_metrics: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    # True when the LLM returned text but we could not parse it (debug file written)
    parse_failed: bool = False


class ScanConfig(BaseModel):
    """Configuration used for the scan."""
    model: str
    ollama_url: str
    target_directory: str
    extensions: list[str]
    max_file_size_kb: int


class ScanReport(BaseModel):
    """Complete scan report containing all results."""
    target_directory: str
    total_files_scanned: int = 0
    total_issues: int = 0
    results: list[ScanResult] = Field(default_factory=list)
    scan_started_at: datetime = Field(default_factory=datetime.now)
    scan_completed_at: Optional[datetime] = None
    config: Optional[ScanConfig] = None

    def finalize(self) -> None:
        """Calculate totals and set completion time."""
        self.scan_completed_at = datetime.now()
        self.total_files_scanned = len(self.results)
        self.total_issues = sum(len(r.issues) for r in self.results)
