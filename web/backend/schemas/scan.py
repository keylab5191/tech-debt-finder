from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict

from web.backend.models.scan import ScanStatus


class ScanBase(BaseModel):
    target_directory: str
    model: str
    status: ScanStatus = ScanStatus.pending
    total_files: int = 0
    files_scanned: int = 0
    total_issues: int = 0
    config: Optional[dict[str, Any]] = None


class ScanCreate(BaseModel):
    target_directory: str
    model: str = "qwen2.5-coder:7b"
    categories: List[str] = []
    max_file_size_kb: int = 100
    clear_previous: bool = False


class ScanUpdate(BaseModel):
    status: Optional[ScanStatus] = None
    completed_at: Optional[datetime] = None
    files_scanned: Optional[int] = None
    total_issues: Optional[int] = None
    config: Optional[dict[str, Any]] = None


class ScanResponse(ScanBase):
    id: str
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ScanListResponse(BaseModel):
    items: List[ScanResponse]
    total: int
