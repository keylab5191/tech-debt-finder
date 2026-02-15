from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
import asyncio
import os

from web.backend.database import get_db
from web.backend.models import Issue, IssueSeverity, IssueCategory, IssueStatus, Scan
from web.backend.schemas import IssueResponse, IssueListResponse, IssueUpdate
from web.backend.schemas.issue import FixRequest, FixResponse, FixResult
from web.backend.api.websocket import manager

router = APIRouter(prefix="/issues", tags=["issues"])

FIX_WORKTREE_DIR = "fix"
OPENCODE_MODEL = None  # Set a specific model if needed, e.g., "openai/gpt-4o"

# Model pricing per 1M tokens (approximate)
MODEL_PRICING = {
    "openai/gpt-4o": {"input": 2.5, "output": 10.0},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "openai/o1": {"input": 15.0, "output": 60.0},
    "anthropic/claude-3.5-sonnet": {"input": 3.0, "output": 15.0},
    "anthropic/claude-3-opus": {"input": 15.0, "output": 75.0},
    "google/gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    "google/gemini-1.5-flash": {"input": 0.075, "output": 0.3},
    "big-pickle": {"input": 0.0, "output": 0.0},  # Free for now
    "gpt-5-nano": {"input": 0.0, "output": 0.0},  # Free for now
}

def estimate_cost(model: str, input_tokens: int = 1000, output_tokens: int = 500) -> float:
    """Estimate cost based on model and token usage."""
    pricing = MODEL_PRICING.get(model, {"input": 1.0, "output": 5.0})
    return (input_tokens / 1_000_000 * pricing["input"]) + (output_tokens / 1_000_000 * pricing["output"])


def _get_scan_id(db: Session, scan_id: Optional[str], all_scans: bool) -> Optional[str]:
    if all_scans or scan_id:
        return scan_id
    
    latest_scan = db.query(Scan).order_by(Scan.started_at.desc()).first()
    if latest_scan:
        return latest_scan.id
    return None


def _apply_filters(query, scan_id=None, severity=None, category=None, status=None, search=None):
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
    return query


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
    resolved_scan_id = _get_scan_id(db, scan_id, all_scans)
    
    query = _apply_filters(
        db.query(Issue),
        scan_id=resolved_scan_id,
        severity=severity,
        category=category,
        status=status,
        search=search
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
    resolved_scan_id = _get_scan_id(db, scan_id, all_scans)
    
    query = _apply_filters(db.query(Issue), scan_id=resolved_scan_id)
    
    severity_counts = query.with_entities(
        Issue.severity,
        func.count(Issue.id)
    ).group_by(Issue.severity).all()
    
    category_counts = query.with_entities(
        Issue.category,
        func.count(Issue.id)
    ).group_by(Issue.category).all()
    
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


@router.post("/fix")
async def fix_issues(
    fix_request: FixRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Fix multiple issues using OpenCode."""
    issues = db.query(Issue).filter(Issue.id.in_(fix_request.issue_ids)).all()
    
    if not issues:
        raise HTTPException(status_code=404, detail="No issues found")
    
    # Get the scan to determine the base directory
    scan_ids = list(set([i.scan_id for i in issues]))
    scans = db.query(Scan).filter(Scan.id.in_(scan_ids)).all()
    
    # Default to first scan's directory
    base_dir = scans[0].target_directory if scans else "."
    
    # Use the configured worktree directory for fixes
    base_dir = FIX_WORKTREE_DIR
    
    # Prepare task arguments
    issue_ids = [i.id for i in issues]
    
    # Add background task
    background_tasks.add_task(
        run_fix_background,
        issue_ids,
        base_dir
    )
    
    return {"message": "Fix process started in background", "total_issues": len(issue_ids)}


async def run_fix_background(issue_ids: List[str], base_dir: str):
    """Background task to run the fixes."""
    import time
    # Create a new DB session for the background task
    from web.backend.database import SessionLocal
    db = SessionLocal()
    
    try:
        issues = db.query(Issue).filter(Issue.id.in_(issue_ids)).all()
        
        # Group issues by file
        files_to_fix = {}
        for issue in issues:
            if issue.file_path not in files_to_fix:
                files_to_fix[issue.file_path] = []
            files_to_fix[issue.file_path].append(issue)
        
        for file_path, file_issues in files_to_fix.items():
            # Construct prompt (single line for CLI)
            descriptions = " | ".join([f"{i+1}. {issue.description}" for i, issue in enumerate(file_issues)])
            prompt = f"Fix issues in {file_path}: {descriptions}"
            
            # Update status to in_progress
            for issue in file_issues:
                issue.status = IssueStatus.in_progress
            db.commit()
            
            # Broadcast fix start
            scan_ids = list(set([i.scan_id for i in file_issues]))
            if scan_ids:
                await manager.broadcast_fix_progress(
                    scan_ids[0], 
                    [i.id for i in file_issues], 
                    "in_progress", 
                    f"Starting fix for {file_path}",
                    model=OPENCODE_MODEL or "default"
                )
            
            try:
                # Run opencode asynchronously from the fix worktree directory
                opencode_cmd = r"C:\Users\Caleb\AppData\Roaming\npm\opencode.cmd"
                
                # Get absolute path to fix directory
                import pathlib
                import time
                fix_path = pathlib.Path(base_dir).resolve()
                
                # Use run_in_executor to run subprocess in thread pool (Windows compatibility)
                import concurrent.futures
                import subprocess
                
                start_time = time.time()
                
                try:
                    cmd_str = f'"{opencode_cmd}" run {prompt}'
                    
                    loop = asyncio.get_event_loop()
                    
                    def run_subprocess():
                        result = subprocess.run(
                            cmd_str,
                            shell=True,
                            capture_output=True,
                            cwd=str(fix_path),
                            encoding='utf-8',
                            errors='replace'
                        )
                        return result
                    
                    result = await loop.run_in_executor(None, run_subprocess)
                    
                    duration = time.time() - start_time
                    
                    print(f"[FIX BG] stdout: {result.stdout[:500]}...")
                    print(f"[FIX BG] returncode: {result.returncode}, duration: {duration:.1f}s")
                    
                    returncode = result.returncode
                    stdout = result.stdout
                    
                except Exception as e:
                    import traceback
                    print(f"[FIX BG] Error running fix: {e}")
                    print(f"[FIX BG] Traceback: {traceback.format_exc()}")
                    raise
                
                print(f"[FIX BG] returncode: {returncode}")
                
                if returncode == 0:
                    for issue in file_issues:
                        issue.status = IssueStatus.resolved
                    status_msg = "completed"
                else:
                    for issue in file_issues:
                        issue.status = IssueStatus.open
                    status_msg = "failed"
                    
                # Broadcast fix result
                if scan_ids:
                    # Estimate tokens and cost based on prompt/output length
                    input_tokens = len(prompt) // 4  # rough estimate
                    output_tokens = len(stdout) // 4 if stdout else 0
                    estimated_cost = estimate_cost(OPENCODE_MODEL or "big-pickle", input_tokens, output_tokens)
                    
                    # Get first line of result for display
                    result_preview = stdout.strip().split('\n')[0][:200] if stdout else ""
                    
                    await manager.broadcast_fix_progress(
                        scan_ids[0], 
                        [i.id for i in file_issues], 
                        status_msg, 
                        f"Fix {status_msg} for {file_path}",
                        model=OPENCODE_MODEL or "default",
                        duration=duration,
                        result=result_preview,
                        cost=estimated_cost,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens
                    )
                    
            except Exception as e:
                print(f"[FIX BG] Error: {e}")
                duration_val = None
                try:
                    duration_val = time.time() - start_time
                except:
                    pass
                for issue in file_issues:
                    issue.status = IssueStatus.open
                
                # Broadcast fix error
                if scan_ids:
                    await manager.broadcast_fix_progress(
                        scan_ids[0], 
                        [i.id for i in file_issues], 
                        "error", 
                        str(e),
                        duration=duration_val
                    )
            
            db.commit()
            
    finally:
        db.close()
