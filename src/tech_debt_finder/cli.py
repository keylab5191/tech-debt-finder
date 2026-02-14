"""CLI entry point for Tech Debt Finder."""

from __future__ import annotations

import argparse
import sys
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

from . import __version__
from .models import ScanConfig, ScanReport
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
        default="codellama",
        help="Ollama model to use (default: codellama)",
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


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

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

    output_path = Path(args.output)

    # Print banner
    console.print()
    console.print("[bold bright_blue]🔍 Tech Debt Finder[/]", highlight=False)
    console.print(f"   Target:  [cyan]{target_dir}[/]")
    console.print(f"   Model:   [cyan]{args.model}[/]")
    console.print(f"   Output:  [cyan]{output_path}[/]")
    console.print()

    # Collect files
    console.print("[dim]Scanning for code files...[/]")
    files = list(scan_files(target_dir, extensions, args.max_file_size))

    if not files:
        console.print("[yellow]No code files found to scan.[/]")
        return 0

    console.print(f"[dim]Found [bold]{len(files)}[/bold] file(s) to review[/]")
    console.print()

    # Create report
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

    # Process files with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Reviewing files", total=len(files))

        for file_path in files:
            rel_path = file_path.relative_to(target_dir)
            progress.update(task, description=f"[cyan]{rel_path}[/]")

            result = review_file(
                file_path=file_path,
                target_dir=target_dir,
                model=args.model,
                ollama_url=args.ollama_url,
            )
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
    report.finalize()
    write_report(report, output_path)
    print_summary(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
