import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from web.backend.database import Base

if TYPE_CHECKING:
    from .scan import Scan


class IssueSeverity(str, PyEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class IssueCategory(str, PyEnum):
    code_smell = "code_smell"
    complexity = "complexity"
    naming = "naming"
    structure = "structure"
    duplication = "duplication"
    error_handling = "error_handling"
    security = "security"
    performance = "performance"
    readability = "readability"
    best_practices = "best_practices"


class IssueStatus(str, PyEnum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    ignored = "ignored"


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id: Mapped[str] = mapped_column(String, ForeignKey("scans.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    line_range: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[IssueSeverity] = mapped_column(Enum(IssueSeverity), nullable=False)
    category: Mapped[IssueCategory] = mapped_column(Enum(IssueCategory), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    suggestion: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[IssueStatus] = mapped_column(Enum(IssueStatus), default=IssueStatus.open, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    scan: Mapped["Scan"] = relationship("Scan", back_populates="issues")
