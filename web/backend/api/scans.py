from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
import os

from web.backend.database import get_db
from web.backend.models import Scan, ScanStatus, Issue
from web.backend.schemas import ScanCreate, ScanResponse, ScanListResponse
from web.backend.api.websocket import manager
from web.backend.services.scan_manager import run_scan_in_background

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("", response_model=ScanResponse)
async def create_scan(
    scan_data: ScanCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create and trigger a new scan."""
    if not os.path.exists(scan_data.target_directory):
        raise HTTPException(status_code=400, detail="Target directory does not exist")
    
    # Clear previous scans if requested
    if scan_data.clear_previous:
        db.query(Issue).delete()
        db.query(Scan).delete()
        db.commit()
    
    # Build config object from parameters
    config = {
        "categories": scan_data.categories,
        "max_file_size_kb": scan_data.max_file_size_kb
    }
    
    scan = Scan(
        target_directory=scan_data.target_directory,
        model=scan_data.model,
        config=config
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    
    # Start scan in background using the real scan manager
    background_tasks.add_task(
        run_scan_in_background,
        scan.id,
        scan.target_directory,
        scan.model,
        ollama_url="http://localhost:11434",
        extensions=None,  # Use default extensions
        max_file_size_kb=scan_data.max_file_size_kb,
        categories=scan_data.categories if scan_data.categories else None,
    )
    
    return scan


@router.get("", response_model=ScanListResponse)
async def list_scans(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List all scans with pagination."""
    total = db.query(Scan).count()
    scans = db.query(Scan).order_by(Scan.started_at.desc()).offset(skip).limit(limit).all()
    
    return ScanListResponse(items=scans, total=total)


@router.get("/active", response_model=List[ScanResponse])
async def get_active_scans(db: Session = Depends(get_db)):
    """Get currently running scans."""
    scans = db.query(Scan).filter(
        Scan.status.in_([ScanStatus.pending, ScanStatus.running])
    ).order_by(Scan.started_at.desc()).all()
    
    return scans


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: str, db: Session = Depends(get_db)):
    """Get single scan details."""
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    return scan


@router.delete("/{scan_id}")
async def delete_scan(scan_id: str, db: Session = Depends(get_db)):
    """Delete scan and all its issues."""
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    db.delete(scan)
    db.commit()
    
    # Notify clients that scan was deleted
    await manager.broadcast_scan_deleted(scan_id)
    
    return {"message": "Scan deleted successfully"}


@router.delete("/clear-all")
async def clear_all_scans(db: Session = Depends(get_db)):
    """Delete all scans and their issues."""
    # Delete all issues first (cascade should handle this, but being explicit)
    db.query(Issue).delete()
    db.query(Scan).delete()
    db.commit()
    
    return {"message": "All scans cleared successfully"}


@router.post("/import")
async def import_scan_report(
    report_path: str,
    skip_duplicates: bool = True,
    db: Session = Depends(get_db)
):
    """Import an existing JSON report into the database."""
    from web.backend.services.sync_service import sync_json_report
    
    if not os.path.exists(report_path):
        raise HTTPException(status_code=400, detail=f"Report file not found: {report_path}")
    
    try:
        stats = sync_json_report(report_path, db, skip_duplicates)
        return {
            "message": "Report imported successfully",
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import report: {str(e)}")
