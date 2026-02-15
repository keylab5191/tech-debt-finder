from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

from web.backend.models.issue import IssueSeverity, IssueCategory, IssueStatus


class IssueBase(BaseModel):
    file_path: str
    line_range: Optional[str] = None
    severity: IssueSeverity
    category: IssueCategory
    title: str
    description: str
    suggestion: str
    status: IssueStatus = IssueStatus.open


class IssueCreate(IssueBase):
    scan_id: str


class IssueUpdate(BaseModel):
    severity: Optional[IssueSeverity] = None
    status: Optional[IssueStatus] = None
    title: Optional[str] = None
    description: Optional[str] = None
    suggestion: Optional[str] = None


class IssueResponse(IssueBase):
    id: str
    scan_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IssueListResponse(BaseModel):
    items: List[IssueResponse]
    total: int
