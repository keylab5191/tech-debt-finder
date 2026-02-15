import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, JSON, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from web.backend.database import Base

if TYPE_CHECKING:
    from .issue import Issue


class ScanStatus(str, PyEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    target_directory: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[ScanStatus] = mapped_column(Enum(ScanStatus), default=ScanStatus.pending, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    files_scanned: Mapped[int] = mapped_column(Integer, default=0)
    total_issues: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    issues: Mapped[List["Issue"]] = relationship("Issue", back_populates="scan", cascade="all, delete-orphan")
