from datetime import datetime
from typing import Optional, List, Any, TypedDict

from pydantic import BaseModel, ConfigDict
from pydantic.types import TypeAdapter

from web.backend.models.scan import ScanStatus


class ScanConfiguration(TypedDict, total=False):
    """
    Configuration parameters for a scan operation.

    This TypedDict defines the configuration options that can be passed
    when creating a new scan. It allows for flexible customization of
    the scanning process.
    """

    model: str
    categories: List[str]
    max_file_size_kb: int
    clear_previous: bool


class ScanBase(BaseModel):
    """
    Base model for a scan entity.

    Contains the common attributes shared between create, update, and response models.
    """

    target_directory: str
    model: str
    status: ScanStatus = ScanStatus.pending
    total_files: int = 0
    files_scanned: int = 0
    total_issues: int = 0
    config: Optional[dict[str, Any]] = None


class ScanCreate(BaseModel):
    """
    Model for creating a new scan.

    This model is used when initiating a new scan operation. It defines
    the required and optional parameters for the scan creation.
    """

    target_directory: str
    model: str = "qwen2.5-coder:7b"
    categories: List[str] = []
    max_file_size_kb: int = 100
    clear_previous: bool = False


class ScanUpdate(BaseModel):
    """
    Model for updating an existing scan.

    This model is used to update the attributes of an existing scan.
    All fields are optional to allow partial updates.
    """

    status: Optional[ScanStatus] = None
    completed_at: Optional[datetime] = None
    files_scanned: Optional[int] = None
    total_issues: Optional[int] = None
    config: Optional[dict[str, Any]] = None


class ScanResponse(ScanBase):
    """
    Model for the scan response.

    This model represents the full scan object as returned by the API,
    including the ID and timestamps.
    """

    id: str
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ScanListResponse(BaseModel):
    """
    Model for a list of scans.

    This model is used to return a paginated list of scans.
    """

    items: List[ScanResponse]
    total: int
