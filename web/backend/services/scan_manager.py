"""Background scan runner that integrates with CLI scanner."""

from __future__ import annotations

import asyncio
import os
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
    """Manages background scan execution with progress tracking.
    
    This class is responsible for orchestrating the scanning process,
    including initializing the database session, managing the scan lifecycle,
    and broadcasting updates to connected clients via WebSocket.
    
    Attributes:
        scan_id: Unique identifier for the scan.
        db: SQLAlchemy database session.
        _stop_requested: Flag to signal the scan to stop.
    """
    
    def __init__(self, scan_id: str, db: Session):
        """Initialize the ScanManager.
        
        Args:
            scan_id: The unique identifier for the scan.
            db: The database session to use for persistence.
        """
        self.scan_id = scan_id
        self.db = db
        self._stop_requested = False
    
    async def run_scan(
        self,
        target_directory: str,
        model: str,
        ollama_url: str = os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        extensions: set[str] | None = None,
        max_file_size_kb: int = 100,
        categories: list[str] | None = None,
    ) -> None:
        """Run a scan in the background with progress updates.
        
        This method orchestrates the entire scanning workflow:
        1. Loads or creates the scan record in the database.
        2. Collects all files to be scanned.
        3. Initializes an async HTTP client for Ollama communication.
        4. Iterates through files and categories, performing reviews.
        5. Saves results to the database and broadcasts progress.
        
        Args:
            target_directory: Path to the directory to scan.
            model: The Ollama model to use for analysis.
            ollama_url: URL of the Ollama service.
            extensions: File extensions to include in the scan.
            max_file_size_kb: Maximum file size in kilobytes.
            categories: List of categories to scan for.
        """
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
                "extensions": list(extensions or set()),
                "max_file_size_kb": max_file_size_kb,
                "categories": [c.value if c else "all" for c in scan_categories],
            }
            self.db.commit()
            
            # Broadcast initial progress
            await manager.broadcast_scan_progress(self.scan_id, 0, total_work)
            
            files_scanned = 0
            total_issues = 0
            
            # Create ONE async HTTP client for ALL files - reused across all files
            # This improves performance by reusing connections and keeping the model loaded
            print("[PERF] Creating shared async HTTP client for all files...")
            async with httpx.AsyncClient(timeout=300.0) as shared_async_client:
                
                # Pre-warm Ollama by sending a dummy request to ensure model stays loaded
                print("[PERF] Pre-warming Ollama to keep model in GPU memory...")
                try:
                    warm_up_response = await shared_async_client.post(
                        f"{ollama_url.rstrip('/')}/api/generate",
                        json={
                            "model": model,
                            "prompt": "Hello",
                            "stream": False,
                            "keep_alive": "60m",  # Keep model loaded for entire scan
                        },
                        timeout=60.0
                    )
                    warm_up_response.raise_for_status()
                    print("[PERF] Ollama warmed up and model is in GPU memory")
                except Exception as e:
                    print(f"[WARN] Failed to pre-warm Ollama: {e}")
                
                try:
                    for category in scan_categories:
                        if self._stop_requested:
                            break
                        
                        category_name = category.value if category else "all"
                        print(f"[PERF] Starting category: {category_name}")
                        
                        for file_path in files:
                            if self._stop_requested:
                                break
                            
                            file_start_time = time.perf_counter()
                            
                            # Broadcast progress every 10 files
                            if files_scanned % 10 == 0:
                                await manager.broadcast_scan_progress(
                                    self.scan_id, files_scanned, total_work
                                )
                                review_time = time.perf_counter() - review_start
                                print(f"[SCAN] Completed review of: {file_path.name} in {review_time:.2f}s - Found {len(result.issues)} issues")
                                
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
                                
                                # Batch commit every 5 files instead of every file
                                if files_scanned % 5 == 0:
                                    self.db.commit()
                                
                                # Broadcast progress every file
                                if files_scanned % 1 == 0:
                                    await manager.broadcast_scan_progress(
                                        self.scan_id, files_scanned, total_work
                                    )
                                
                                total_file_time = time.perf_counter() - file_start_time
                                
                                # Print timing every 10 files
                                if files_scanned % 10 == 0:
                                    print(f"[PERF] File {files_scanned}/{total_work}: Review={review_time:.2f}s, Total={total_file_time:.2f}s - {file_path.name}")
                                
                            except Exception as e:
                                # Log error but continue scanning
                                print(f"[ERROR] Error scanning {file_path}: {e}")
                                import traceback
                                traceback.print_exc()
                                files_scanned += 1
                                scan.files_scanned = files_scanned
                        
                        # Final commit for this category
                        self.db.commit()
                        print(f"[PERF] Finished category: {category_name}")
                finally:
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
        async_client: httpx.AsyncClient,
        category: CLICategory | None = None,
    ) -> Any:
        """Run review_file in a thread pool to make it async-friendly.
        
        This method wraps the synchronous review_file function in an executor
        to prevent blocking the event loop. It passes the shared async client
        to the review function for making HTTP requests.
        
        Args:
            file_path: Path to the file to review.
            target_dir: Base directory of the scan.
            model: The model to use.
            ollama_url: The Ollama URL.
            async_client: The shared async HTTP client.
            category: Optional category to filter issues.
            
        Returns:
            The ScanResult from the review.
        """
        loop = asyncio.get_event_loop()
        
        # Run the synchronous review_file function in executor with timeout
        # Use the SHARED async client - no more creating new clients!
        def run_review():
            try:
                return review_file(
                    file_path=file_path,
                    target_dir=target_dir,
                    model=model,
                    ollama_url=ollama_url,
                    client=async_client,
                    category=category,
                )
            except Exception as e:
                print(f"[ERROR] review_file failed for {file_path}: {e}")
                raise
        
        # Use wait_for to add timeout
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, run_review),
                timeout=60.0  # 60 second timeout per file
            )
        except asyncio.TimeoutError:
            print(f"[TIMEOUT] File review timed out after 60s: {file_path}")
            # Return empty result on timeout
            from tech_debt_finder.models import ScanResult
            return ScanResult(
                file_path=str(file_path.relative_to(target_dir)),
                model_used=model,
                error="Timeout - Ollama took too long"
            )
    
    def _create_issue_from_cli(self, cli_issue: Any) -> Issue:
        """Convert a CLI Issue model to a database Issue model.
        
        This method maps the lightweight CLI Issue object to the database
        Issue model, translating enums for severity and category into the
        database-compatible formats.
        
        Args:
            cli_issue: The CLI issue object to convert.
            
        Returns:
            An Issue model instance ready to be added to the database.
        """
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
        """Request to stop the scan.
        
        Sets an internal flag that the run_scan method checks periodically.
        This allows for graceful shutdown of the scanning process.
        """
        self._stop_requested = True


async def run_scan_in_background(
    scan_id: str,
    target_directory: str,
    model: str,
    **kwargs: Any,
) -> None:
    """Helper function to run a scan in background with its own DB session.
    
    This function creates a new database session, instantiates a ScanManager,
    and runs the scan. It ensures proper cleanup of the database session
    regardless of the scan outcome.
    
    Prerequisites:
        - Ollama must be running and accessible at the URL specified in kwargs or environment variable.
        - The specified model must be available in Ollama.
        - The target directory must exist and be accessible.
        - Database must be accessible.
    
    Args:
        scan_id: Unique identifier for the scan.
        target_directory: Directory to scan.
        model: The LLM model to use.
        **kwargs: Additional arguments passed to ScanManager.run_scan.
    """
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
