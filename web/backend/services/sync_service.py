"""Service for syncing existing JSON reports into the database."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from web.backend.models import Scan, Issue, ScanStatus
from web.backend.models.issue import IssueSeverity, IssueCategory, IssueStatus


def sync_json_report(
    report_path: str | Path,
    db: Session,
    skip_duplicates: bool = True,
) -> dict[str, Any]:
    """
    Import a tech debt JSON report into the database.
    
    Args:
        report_path: Path to the JSON report file
        db: Database session
        skip_duplicates: If True, skip files that already exist in a scan
        
    Returns:
        Dict with import statistics
    """
    report_path = Path(report_path)
    
    if not report_path.exists():
        raise FileNotFoundError(f"Report file not found: {report_path}")
    
    # Load and parse the JSON report
    with open(report_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)
    
    return import_legacy_report(report_data, db, skip_duplicates)


def import_legacy_report(
    report_data: dict[str, Any],
    db: Session,
    skip_duplicates: bool = True,
) -> dict[str, Any]:
    """
    Import a legacy report (already parsed dict) into the database.
    
    Args:
        report_data: The parsed report JSON data
        db: Database session
        skip_duplicates: If True, skip files that already exist
        
    Returns:
        Dict with import statistics
    """
    stats = {
        "scans_created": 0,
        "issues_created": 0,
        "files_processed": 0,
        "duplicates_skipped": 0,
        "errors": [],
    }
    
    try:
        # Extract report metadata
        target_directory = report_data.get("target_directory", "unknown")
        scan_started_at = report_data.get("scan_started_at")
        scan_completed_at = report_data.get("scan_completed_at")
        total_files = report_data.get("total_files_scanned", 0)
        total_issues = report_data.get("total_issues", 0)
        config = report_data.get("config", {})
        results = report_data.get("results", [])
        
        # Check for existing scan with same target and timestamp
        if skip_duplicates:
            existing = db.query(Scan).filter(
                Scan.target_directory == target_directory,
            ).first()
            
            if existing:
                # Check if this is the same scan by comparing file paths
                existing_files = {
                    issue.file_path for issue in existing.issues
                }
                new_files = {
                    result.get("file_path", "") for result in results
                }
                
                if existing_files == new_files:
                    stats["duplicates_skipped"] += 1
                    return stats
        
        # Create new scan record
        scan = Scan(
            target_directory=target_directory,
            model=config.get("model", "unknown"),
            status=ScanStatus.completed,
            total_files=total_files,
            files_scanned=total_files,
            total_issues=total_issues,
            config=config,
        )
        
        # Parse timestamps if available
        if scan_started_at:
            try:
                scan.started_at = datetime.fromisoformat(scan_started_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                scan.started_at = datetime.utcnow()
        
        if scan_completed_at:
            try:
                scan.completed_at = datetime.fromisoformat(scan_completed_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                scan.completed_at = datetime.utcnow()
        
        db.add(scan)
        db.flush()  # Get the scan ID
        stats["scans_created"] = 1
        
        # Process each result (file)
        for result in results:
            try:
                file_path = result.get("file_path", "")
                issues = result.get("issues", [])
                
                stats["files_processed"] += 1
                
                # Create issues for this file
                for issue_data in issues:
                    try:
                        issue = _create_issue_from_data(
                            issue_data, scan.id, file_path
                        )
                        if issue:
                            db.add(issue)
                            stats["issues_created"] += 1
                    except Exception as e:
                        stats["errors"].append(
                            f"Error creating issue for {file_path}: {e}"
                        )
                
            except Exception as e:
                stats["errors"].append(f"Error processing result: {e}")
        
        db.commit()
        
    except Exception as e:
        db.rollback()
        stats["errors"].append(f"Failed to import report: {e}")
        raise
    
    return stats


def _create_issue_from_data(
    issue_data: dict[str, Any],
    scan_id: str,
    file_path: str,
) -> Issue | None:
    """Create an Issue model from parsed JSON data."""
    # Map severity
    severity_map = {
        "critical": IssueSeverity.critical,
        "high": IssueSeverity.high,
        "medium": IssueSeverity.medium,
        "low": IssueSeverity.low,
    }
    severity = severity_map.get(
        issue_data.get("severity", "medium").lower(),
        IssueSeverity.medium
    )
    
    # Map category
    category_map = {
        "code_smell": IssueCategory.code_smell,
        "complexity": IssueCategory.complexity,
        "naming": IssueCategory.naming,
        "structure": IssueCategory.structure,
        "duplication": IssueCategory.duplication,
        "error_handling": IssueCategory.error_handling,
        "security": IssueCategory.security,
        "performance": IssueCategory.performance,
        "readability": IssueCategory.readability,
        "best_practices": IssueCategory.best_practices,
    }
    category = category_map.get(
        issue_data.get("category", "code_smell").lower(),
        IssueCategory.code_smell
    )
    
    # Get file path from issue data or use the parent file_path
    issue_file_path = issue_data.get("file_path", file_path)
    
    return Issue(
        scan_id=scan_id,
        file_path=issue_file_path,
        line_range=issue_data.get("line_range"),
        severity=severity,
        category=category,
        title=issue_data.get("title", "Untitled Issue"),
        description=issue_data.get("description", ""),
        suggestion=issue_data.get("suggestion", ""),
        status=IssueStatus.open,
    )


def check_for_duplicates(
    target_directory: str,
    db: Session,
) -> list[Scan]:
    """
    Check if there are existing scans for a target directory.
    
    Args:
        target_directory: The directory to check
        db: Database session
        
    Returns:
        List of existing scans
    """
    return db.query(Scan).filter(
        Scan.target_directory == target_directory
    ).order_by(Scan.started_at.desc()).all()
