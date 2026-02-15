"""Report generator — writes JSON report and prints rich terminal summary."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import ScanReport, Severity

console = Console()

# Severity colors for terminal output
SEVERITY_COLORS = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "dim cyan",
}

SEVERITY_EMOJI = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "🔵",
}


def write_report(report: ScanReport, output_path: Path) -> None:
    """Write the scan report to a JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report_data = report.model_dump(mode="json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, default=str)

    console.print(f"\n📄 Report written to [bold cyan]{output_path}[/]")


def print_summary(report: ScanReport) -> None:
    """Print a rich terminal summary of the scan results."""
    console.print()

    # Header
    duration = "N/A"
    if report.scan_started_at and report.scan_completed_at:
        delta = report.scan_completed_at - report.scan_started_at
        minutes = int(delta.total_seconds() // 60)
        seconds = int(delta.total_seconds() % 60)
        duration = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

    header = Text()
    header.append("Tech Debt Scan Complete", style="bold white")
    console.print(Panel(header, border_style="bright_blue", padding=(0, 2)))

    # Overview stats
    stats_table = Table(show_header=False, box=None, padding=(0, 2))
    stats_table.add_column("Label", style="dim")
    stats_table.add_column("Value", style="bold")
    stats_table.add_row("📁 Files scanned", str(report.total_files_scanned))
    stats_table.add_row("🐛 Issues found", str(report.total_issues))
    stats_table.add_row("⏱  Duration", duration)
    if report.config:
        stats_table.add_row("🤖 Model", report.config.model)
    console.print(stats_table)
    console.print()

    if report.total_issues == 0:
        console.print("[bold green]✨ No tech debt issues found! Great codebase![/]")
        return

    # Severity breakdown
    all_issues = [issue for result in report.results for issue in result.issues]
    severity_counts = Counter(issue.severity for issue in all_issues)

    sev_table = Table(title="Severity Breakdown", border_style="dim")
    sev_table.add_column("Severity", style="bold")
    sev_table.add_column("Count", justify="right")
    sev_table.add_column("Bar")

    max_count = max(severity_counts.values()) if severity_counts else 1
    for sev in Severity:
        count = severity_counts.get(sev, 0)
        bar_len = int((count / max_count) * 30) if max_count else 0
        bar = "█" * bar_len
        emoji = SEVERITY_EMOJI.get(sev, "")
        color = SEVERITY_COLORS.get(sev, "white")
        sev_table.add_row(
            f"{emoji} {sev.value.capitalize()}",
            str(count),
            Text(bar, style=color),
        )

    console.print(sev_table)
    console.print()

    # Category breakdown
    category_counts = Counter(issue.category.value for issue in all_issues)

    cat_table = Table(title="Category Breakdown", border_style="dim")
    cat_table.add_column("Category", style="bold")
    cat_table.add_column("Count", justify="right")

    for cat, count in category_counts.most_common():
        cat_table.add_row(cat.replace("_", " ").title(), str(count))

    console.print(cat_table)
    console.print()

    # Top problematic files
    file_issue_counts = [
        (result.file_path, len(result.issues))
        for result in report.results
        if result.issues
    ]
    file_issue_counts.sort(key=lambda x: x[1], reverse=True)

    if file_issue_counts:
        file_table = Table(title="Top Problematic Files", border_style="dim")
        file_table.add_column("File", style="cyan")
        file_table.add_column("Issues", justify="right", style="bold yellow")

        for file_path, count in file_issue_counts[:10]:
            file_table.add_row(file_path, str(count))

        console.print(file_table)
        console.print()

    # Parse failures (LLM responded but we couldn't parse; debug file written)
    unparseable_results = [result for result in report.results if getattr(result, "parse_failed", False)]
    if unparseable_results:
        console.print(
            f"[dim yellow]⚠ {len(unparseable_results)} file(s) had unparseable LLM response (see tech_debt_debug/)[/]"
        )
        for result in unparseable_results[:5]:
            console.print(f"  [dim]{result.file_path}[/]")
        if len(unparseable_results) > 5:
            console.print(f"  [dim]... and {len(unparseable_results) - 5} more[/]")
        console.print()

    # Errors
    error_results = [result for result in report.results if result.error]
    if error_results:
        console.print(f"[dim red]⚠ {len(error_results)} file(s) had errors during scanning[/]")
        for result in error_results[:5]:
            console.print(f"  [dim]{result.file_path}: {result.error}[/]")
        if len(error_results) > 5:
            console.print(f"  [dim]... and {len(error_results) - 5} more[/]")
