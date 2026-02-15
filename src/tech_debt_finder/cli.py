"""CLI entry point for Tech Debt Finder."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

import httpx

from . import __version__
from .models import Category, ScanConfig, ScanReport
from .report import print_summary, write_report
from .reviewer import review_file
from .scanner import DEFAULT_EXTENSIONS, scan_files

console = Console(stderr=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="tech-debt-finder",
        description="🔍 AI-powered tech debt scanner — review your codebase with a local LLM",
    )
    parser.add_argument(
        "target",
        type=str,
        help="Target directory to scan",
    )
    parser.add_argument(
        "--model", "-m",
        default="qwen2.5-coder:7b",
        help="Ollama model to use (default: qwen2.5-coder:7b)",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama API URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--output", "-o",
        default="tech_debt_report.json",
        help="Output JSON report path (default: tech_debt_report.json)",
    )
    parser.add_argument(
        "--extensions", "-e",
        default=None,
        help="Comma-separated file extensions to scan (e.g. .py,.js,.ts)",
    )
    parser.add_argument(
        "--max-file-size",
        type=int,
        default=100,
        help="Max file size in KB to scan (default: 100)",
    )
    parser.add_argument(
        "--categories", "-c",
        default=None,
        help="Comma-separated categories to scan (e.g. security,complexity,naming). "
             "Available: code_smell, complexity, naming, structure, duplication, "
             "error_handling, security, performance, readability, best_practices. "
             "Default: all",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args(argv)


def calculate_elapsed_time(start_time: float) -> str:
    return f"[{time.perf_counter() - start_time:.2f}s]"


def verify_ollama_connection(ollama_url: str, model: str) -> bool:
    """
    Run a quick Ollama connectivity and model test with debug output.
    Returns True if OK, False if test failed (caller should exit 1).
    """
    base = ollama_url.rstrip("/")
    console.print("[bold]Ollama pre-flight check[/]")
    console.print(f"  URL:   [cyan]{base}[/]")
    console.print(f"  Model: [cyan]{model}[/]")
    console.print()

    with httpx.Client(timeout=30.0) as client:
        # 1) List models
        try:
            console.print("  [dim]GET /api/tags ...[/]")
            r = client.get(f"{base}/api/tags")
            r.raise_for_status()
            data = r.json()
            models = data.get("models", [])
            names = [m.get("name", m.get("model", "")) for m in models]
            console.print(f"  [green]✓[/] Ollama reachable. Models: [dim]{', '.join(names) or '(none)'}[/]")
            if model not in names and not any(m.startswith(model) or model in m for m in names):
                console.print(f"  [yellow]⚠[/] Requested model [cyan]{model}[/] not in list; Ollama may pull it on first use.")
        except httpx.ConnectError:
            console.print(f"  [red]✗[/] Cannot connect to [cyan]{base}[/]. Is Ollama running? (e.g. [dim]ollama serve[/])")
            return False
        except httpx.HTTPStatusError as e:
            console.print(f"  [red]✗[/] HTTP error: [red]{e.response.status_code}[/]")
            return False
        except Exception as e:
            console.print(f"  [red]✗[/] Error: [red]{e}[/]")
            return False

        # 2) Minimal generate to confirm model loads and responds
        try:
            console.print("  [dim]POST /api/generate (minimal prompt) ...[/]")
            test_start_time = time.perf_counter()
            r = client.post(
                f"{base}/api/generate",
                json={
                    "model": model,
                    "prompt": "Reply with exactly: OK",
                    "stream": False,
                    "options": {"num_predict": 10, "temperature": 0},
                },
                timeout=60.0,
            )
            elapsed = time.perf_counter() - test_start_time
            r.raise_for_status()
            out = r.json()
            load_ns = out.get("load_duration", 0)
            eval_ns = out.get("eval_duration", 0)
            eval_count = out.get("eval_count", 0)
            load_s = load_ns / 1e9
            eval_s = eval_ns / 1e9
            response = (out.get("response") or "").strip()[:80]
            console.print(
                f"  [green]✓[/] Generate OK in [cyan]{elapsed:.2f}s[/] "
                f"(load: [cyan]{load_s:.2f}s[/], eval: [cyan]{eval_s:.2f}s[/], tokens: [cyan]{eval_count}[/])"
            )
            console.print(f"  [dim]Response snippet: {response!r}[/]")
        except httpx.ConnectError:
            console.print(f"  [red]✗[/] Connection lost during generate.")
            return False
        except httpx.TimeoutException:
            console.print(f"  [red]✗[/] Generate timed out (model may be loading or slow).")
            return False
        except httpx.HTTPStatusError as e:
            console.print(f"  [red]✗[/] Generate failed: [red]{e.response.status_code}[/] [dim]{e.response.text[:200]}[/]")
            return False
        except Exception as e:
            console.print(f"  [red]✗[/] Error: [red]{e}[/]")
            return False

    console.print()
    return True


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    scan_start_time = time.perf_counter()
    args = parse_args(argv)
    console.print(f"  {calculate_elapsed_time(scan_start_time)} parse args done")

    target_dir = Path(args.target).resolve()
    if not target_dir.is_dir():
        console.print(f"[bold red]Error:[/] '{args.target}' is not a valid directory")
        return 1

    # Parse extensions
    extensions = DEFAULT_EXTENSIONS
    if args.extensions:
        extensions = set()
        for ext in args.extensions.split(","):
            ext = ext.strip()
            if not ext.startswith("."):
                ext = f".{ext}"
            extensions.add(ext.lower())

    # Parse categories
    categories: list[Category | None] = [None]  # None means "all categories" (legacy behavior)
    if args.categories:
        category_names = [c.strip().lower() for c in args.categories.split(",")]
        categories = []
        for name in category_names:
            try:
                categories.append(Category(name))
            except ValueError:
                console.print(f"[bold red]Error:[/] Invalid category '{name}'. Valid categories: {[c.value for c in Category]}")
                return 1

    output_path = Path(args.output)

    # Print banner
    console.print()
    console.print("[bold bright_blue]🔍 Tech Debt Finder[/]", highlight=False)
    console.print(f"   Target:  [cyan]{target_dir}[/]")
    console.print(f"   Model:   [cyan]{args.model}[/]")
    console.print(f"   Output:  [cyan]{output_path}[/]")
    if categories and categories[0] is None:
        console.print(f"   Categories: [cyan]all[/]")
    else:
        console.print(f"   Categories: [cyan]{', '.join(c.value for c in categories)}[/]")
    console.print()

    # Pre-flight: test Ollama connectivity and model
    if not verify_ollama_connection(args.ollama_url, args.model):
        console.print("[bold red]Ollama check failed. Fix the issue above and try again.[/]")
        return 1

    # Collect files
    console.print(f"  {calculate_elapsed_time(scan_start_time)} Scanning for code files...")
    scan_start_timestamp = time.perf_counter()
    files = list(scan_files(target_dir, extensions, args.max_file_size))
    console.print(f"  {calculate_elapsed_time(scan_start_time)} Scan done in {time.perf_counter() - scan_start_timestamp:.2f}s")

    if not files:
        console.print("[yellow]No code files found to scan.[/]")
        return 0

    console.print(f"[dim]Found [bold]{len(files)}[/bold] file(s) to review[/]")
    console.print()

    # Create report
    console.print(f"  {calculate_elapsed_time(scan_start_time)} Building report config...")
    config = ScanConfig(
        model=args.model,
        ollama_url=args.ollama_url,
        target_directory=str(target_dir),
        extensions=sorted(extensions),
        max_file_size_kb=args.max_file_size,
    )
    report = ScanReport(
        target_directory=str(target_dir),
        config=config,
        scan_started_at=datetime.now(),
    )
    console.print(f"  {calculate_elapsed_time(scan_start_time)} Config done")

    # Process files with progress bar; reuse one HTTP client so Ollama keeps the model loaded
    # If categories is [None], use None (legacy "all" behavior)
    scan_categories: list[Category | None] = categories if categories and categories[0] is not None else [None]
    
    # Calculate total work: files * categories
    total_work = len(files) * len(scan_categories)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Reviewing files", total=total_work)

        with httpx.Client(timeout=300.0) as http_client:
            for category in scan_categories:
                category_name = category.value if category else "all"
                console.print(f"\n[bold]Scanning for: {category_name}[/]")
                
                for file_path in files:
                    rel_path = file_path.relative_to(target_dir)
                    progress.update(task, description=f"[cyan]{rel_path}[/] ({category_name})")

                    console.print(f"  {calculate_elapsed_time(scan_start_time)} Reviewing {rel_path} for {category_name}...")
                    file_review_start = time.perf_counter()
                    result = review_file(
                        file_path=file_path,
                        target_dir=target_dir,
                        model=args.model,
                        ollama_url=args.ollama_url,
                        client=http_client,
                        category=category,
                    )
                    console.print(f"  {calculate_elapsed_time(scan_start_time)} {rel_path} done in {time.perf_counter() - file_review_start:.2f}s")
                    report.results.append(result)

                    if result.error:
                        if "Cannot connect to Ollama" in result.error:
                            console.print(f"\n[bold red]Error:[/] {result.error}")
                            return 1
                        if args.verbose:
                            console.print(f"  [dim red]✗ {rel_path}: {result.error}[/]")
                    elif result.issues and args.verbose:
                        console.print(
                            f"  [dim]Found {len(result.issues)} issue(s) in {rel_path}[/]"
                        )

                    progress.advance(task)

    # Finalize and write report
    console.print(f"  {calculate_elapsed_time(scan_start_time)} Finalizing report...")
    report_finalization_start = time.perf_counter()
    report.finalize()
    write_report(report, output_path)
    console.print(f"  {calculate_elapsed_time(scan_start_time)} Write report done in {time.perf_counter() - report_finalization_start:.2f}s")
    print_summary(report)
    console.print(f"  {calculate_elapsed_time(scan_start_time)} Total run: {time.perf_counter() - scan_start_time:.2f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
