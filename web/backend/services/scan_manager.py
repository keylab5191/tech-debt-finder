"""Background scan runner that integrates with CLI scanner."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from web.backend.database import SessionLocal
from web.backend.models import Scan, Issue, ScanStatus
from web.backend.models.issue import IssueSeverity, IssueCategory, IssueStatus
from web.backend.api.websocket import manager


# Import CLI scanner modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from tech_debt_finder.scanner import scan_files, DEFAULT_EXTENSIONS
from tech_debt_finder.reviewer import review_file
from tech_debt_finder.models import Category as CLICategory, ScanConfig


class ScanManager:
    """Manages background scan execution with progress tracking."""
    
    def __init__(self, scan_id: str, db: Session):
        self.scan_id = scan_id
        self.db = db
        self._stop_requested = False
    
    async def run_scan(
        self,
        target_directory: str,
        model: str,
        ollama_url: str = "http://localhost:11434",
        extensions: set[str] | None = None,
        max_file_size_kb: int = 100,
        categories: list[str] | None = None,
    ) -> None:
        """Run a scan in the background with progress updates."""
        scan = self.db.query(Scan).filter(Scan.id == self.scan_id).first()
        if not scan:
            return
        
        try:
            # Update status to running
            scan.status = ScanStatus.running
            self.db.commit()
            await manager.broadcast_scan_update(self.scan_id, "running")
            
            # Parse extensions
            if extensions is None:
                extensions = DEFAULT_EXTENSIONS
            
            # Parse categories
            scan_categories: list[CLICategory | None] = [None]
            if categories:
                scan_categories = []
                for name in categories:
                    try:
                        scan_categories.append(CLICategory(name.lower()))
                    except ValueError:
                        pass
                if not scan_categories:
                    scan_categories = [None]
            
            target_path = Path(target_directory).resolve()
            
            # Collect files to scan
            files = list(scan_files(target_path, extensions, max_file_size_kb))
            total_files = len(files)
            total_work = total_files * len(scan_categories)
            
            scan.total_files = total_work
            scan.config = {
                "model": model,
                "ollama_url": ollama_url,
                "extensions": list(extensions),
                "max_file_size_kb": max_file_size_kb,
                "categories": [c.value if c else "all" for c in scan_categories],
            }
            self.db.commit()
            
            # Broadcast initial progress
            await manager.broadcast_scan_progress(self.scan_id, 0, total_work)
            
            # Create HTTP client for reuse
            async with httpx.AsyncClient(timeout=300.0) as client:
                files_scanned = 0
                total_issues = 0
                
                for category in scan_categories:
                    if self._stop_requested:
                        break
                    
                    category_name = category.value if category else "all"
                    
                    for file_path in files:
                        if self._stop_requested:
                            break
                        
                        try:
                            # Run the file review
                            result = await self._review_file_async(
                                file_path=file_path,
                                target_dir=target_path,
                                model=model,
                                ollama_url=ollama_url,
                                client=client,
                                category=category,
                            )
                            
                            files_scanned += 1
                            scan.files_scanned = files_scanned
                            
                            # Save issues to database
                            if result.issues:
                                for cli_issue in result.issues:
                                    issue = self._create_issue_from_cli(cli_issue)
                                    issue.scan_id = self.scan_id
                                    self.db.add(issue)
                                    total_issues += 1
                                    scan.total_issues = total_issues
                                    
                                    # Notify about new issue
                                    await manager.broadcast_new_issue(
                                        self.scan_id, issue.id
                                    )
                            
                            # Update progress every file
                            if files_scanned % 1 == 0:
                                self.db.commit()
                                await manager.broadcast_scan_progress(
                                    self.scan_id, files_scanned, total_work
                                )
                            
                        except Exception as e:
                            # Log error but continue scanning
                            print(f"Error scanning {file_path}: {e}")
                            files_scanned += 1
                            scan.files_scanned = files_scanned
                
                # Finalize scan
                if self._stop_requested:
                    scan.status = ScanStatus.failed
                    await manager.broadcast_scan_failed(
                        self.scan_id, "Scan was stopped"
                    )
                else:
                    scan.status = ScanStatus.completed
                    scan.completed_at = datetime.utcnow()
                    await manager.broadcast_scan_completed(
                        self.scan_id, scan.total_issues
                    )
                
                self.db.commit()
                
        except Exception as e:
            # Handle scan failure
            scan.status = ScanStatus.failed
            self.db.commit()
            await manager.broadcast_scan_failed(self.scan_id, str(e))
            raise
    
    async def _review_file_async(
        self,
        file_path: Path,
        target_dir: Path,
        model: str,
        ollama_url: str,
        client: httpx.AsyncClient,
        category: CLICategory | None = None,
    ) -> Any:
        """Run review_file in a thread pool to make it async-friendly."""
        loop = asyncio.get_event_loop()
        
        # Create a synchronous HTTP client wrapper
        class AsyncClientWrapper:
            def __init__(self, async_client: httpx.AsyncClient):
                self._client = async_client
            
            def post(self, url: str, **kwargs) -> Any:
                # Run async post in sync context
                future = asyncio.run_coroutine_threadsafe(
                    self._client.post(url, **kwargs),
                    loop
                )
                response = future.result(timeout=300.0)
                
                # Wrap response to provide .json() method
                class ResponseWrapper:
                    def __init__(self, response):
                        self._response = response
                        self.status_code = response.status_code
                        self.text = response.text
                    
                    def json(self):
                        return self._response.json()
                    
                    def raise_for_status(self):
                        self._response.raise_for_status()
                
                return ResponseWrapper(response)
        
        # Run the synchronous review_file function in executor
        def run_review():
            # Note: review_file expects httpx.Client, not AsyncClient
            # We'll create a sync client for each call since mixing is complex
            with httpx.Client(timeout=300.0) as sync_client:
                return review_file(
                    file_path=file_path,
                    target_dir=target_dir,
                    model=model,
                    ollama_url=ollama_url,
                    client=sync_client,
                    category=category,
                )
        
        return await loop.run_in_executor(None, run_review)
    
    def _create_issue_from_cli(self, cli_issue: Any) -> Issue:
        """Convert a CLI Issue model to a database Issue model."""
        # Map severity
        severity_map = {
            "critical": IssueSeverity.critical,
            "high": IssueSeverity.high,
            "medium": IssueSeverity.medium,
            "low": IssueSeverity.low,
        }
        severity = severity_map.get(
            cli_issue.severity.value.lower(),
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
            cli_issue.category.value.lower(),
            IssueCategory.code_smell
        )
        
        return Issue(
            scan_id=self.scan_id,
            file_path=cli_issue.file_path,
            line_range=cli_issue.line_range,
            severity=severity,
            category=category,
            title=cli_issue.title,
            description=cli_issue.description,
            suggestion=cli_issue.suggestion,
            status=IssueStatus.open,
        )
    
    def stop(self) -> None:
        """Request to stop the scan."""
        self._stop_requested = True


async def run_scan_in_background(
    scan_id: str,
    target_directory: str,
    model: str,
    **kwargs: Any,
) -> None:
    """Helper function to run a scan in background with its own DB session."""
    db = SessionLocal()
    try:
        manager_instance = ScanManager(scan_id, db)
        await manager_instance.run_scan(
            target_directory=target_directory,
            model=model,
            **kwargs
        )
    finally:
        db.close()
