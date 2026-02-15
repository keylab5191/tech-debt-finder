from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List

from web.backend.database import get_db
from web.backend.models import Issue, IssueSeverity, IssueCategory, IssueStatus, Scan
from web.backend.schemas import IssueResponse, IssueListResponse, IssueUpdate
from web.backend.api.websocket import manager

router = APIRouter(prefix="/issues", tags=["issues"])


@router.get("", response_model=IssueListResponse)
async def list_issues(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    scan_id: Optional[str] = None,
    all_scans: bool = Query(False, description="Include issues from all scans"),
    severity: Optional[IssueSeverity] = None,
    category: Optional[IssueCategory] = None,
    status: Optional[IssueStatus] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all issues with filters."""
    query = db.query(Issue)
    
    # Default to latest scan if no scan_id provided and all_scans is False
    if not all_scans and not scan_id:
        latest_scan = db.query(Scan).order_by(Scan.started_at.desc()).first()
        if latest_scan:
            scan_id = latest_scan.id
    
    # Apply filters
    if scan_id:
        query = query.filter(Issue.scan_id == scan_id)
    if severity:
        query = query.filter(Issue.severity == severity)
    if category:
        query = query.filter(Issue.category == category)
    if status:
        query = query.filter(Issue.status == status)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (Issue.title.ilike(search_filter)) |
            (Issue.description.ilike(search_filter)) |
            (Issue.file_path.ilike(search_filter))
        )
    
    total = query.count()
    issues = query.order_by(Issue.created_at.desc()).offset(skip).limit(limit).all()
    
    return IssueListResponse(items=issues, total=total)


@router.get("/summary")
async def get_issues_summary(
    scan_id: Optional[str] = None,
    all_scans: bool = Query(False, description="Include stats from all scans"),
    db: Session = Depends(get_db)
):
    """Get stats by severity and category."""
    query = db.query(Issue)
    
    # Default to latest scan if no scan_id provided and all_scans is False
    if not all_scans and not scan_id:
        latest_scan = db.query(Scan).order_by(Scan.started_at.desc()).first()
        if latest_scan:
            scan_id = latest_scan.id
    
    if scan_id:
        query = query.filter(Issue.scan_id == scan_id)
    
    # Count by severity
    severity_counts = query.with_entities(
        Issue.severity,
        func.count(Issue.id)
    ).group_by(Issue.severity).all()
    
    # Count by category
    category_counts = query.with_entities(
        Issue.category,
        func.count(Issue.id)
    ).group_by(Issue.category).all()
    
    # Count by status
    status_counts = query.with_entities(
        Issue.status,
        func.count(Issue.id)
    ).group_by(Issue.status).all()
    
    total_issues = query.count()
    
    return {
        "total": total_issues,
        "by_severity": {severity.value: count for severity, count in severity_counts},
        "by_category": {category.value: count for category, count in category_counts},
        "by_status": {status.value: count for status, count in status_counts}
    }


@router.get("/{issue_id}", response_model=IssueResponse)
async def get_issue(issue_id: str, db: Session = Depends(get_db)):
    """Get single issue details."""
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    return issue


@router.patch("/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: str,
    update_data: IssueUpdate,
    db: Session = Depends(get_db)
):
    """Update issue status, notes, etc."""
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    # Update only provided fields
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(issue, field, value)
    
    db.commit()
    db.refresh(issue)
    
    # Notify clients of issue update
    await manager.broadcast_issue_updated(issue.scan_id, issue.id)
    
    return issue
