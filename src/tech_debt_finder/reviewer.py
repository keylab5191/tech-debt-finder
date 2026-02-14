"""LLM Reviewer — sends code to Ollama for tech debt analysis."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console

from .models import Category, Issue, ScanResult, Severity

console = Console(stderr=True)

# The system prompt instructs the LLM to return structured JSON issues
SYSTEM_PROMPT = """You are a senior software engineer performing a tech debt review.
Analyze the provided source code and identify ANY technical debt, code smells, or improvement opportunities.

Look for:
- Code smells (dead code, magic numbers, overly long functions, god classes)
- Complexity issues (deeply nested logic, complex conditionals)
- Poor naming (unclear variable/function/class names)
- Structural problems (poor file organization, tight coupling, missing abstractions)
- Code duplication
- Missing or poor error handling
- Security concerns (hardcoded secrets, SQL injection, XSS)
- Performance issues (N+1 queries, unnecessary loops, memory leaks)
- Readability problems (missing docs, unclear intent, overly clever code)
- Best practices violations (not following language idioms, anti-patterns)

Respond ONLY with a JSON array of issues. Each issue must be an object with these exact keys:
- "title": short descriptive title (string)
- "severity": one of "critical", "high", "medium", "low" (string)
- "category": one of "code_smell", "complexity", "naming", "structure", "duplication", "error_handling", "security", "performance", "readability", "best_practices" (string)
- "description": detailed explanation of the issue (string)
- "suggestion": how to fix it (string)
- "line_range": approximate line range like "10-25" or null if not applicable (string or null)

If the code is clean and has no issues, respond with an empty array: []

IMPORTANT: Respond with ONLY the JSON array, no other text, no markdown fences, nothing else."""


def _build_prompt(file_path: str, content: str) -> str:
    """Build the user prompt with file context."""
    return f"""Review the following file for tech debt issues.

File: {file_path}

```
{content}
```

Respond with a JSON array of issues found."""


def _parse_issues(response_text: str, file_path: str) -> list[Issue]:
    """Parse LLM response into structured Issue objects."""
    # Try to extract JSON from the response
    text = response_text.strip()

    # Remove markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Try to find a JSON array in the text
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)

    try:
        raw_issues: list[dict[str, Any]] = json.loads(text)
    except json.JSONDecodeError:
        # If we can't parse JSON, return empty — don't crash
        console.print(f"  [dim yellow]⚠ Could not parse LLM response for {file_path}[/]")
        return []

    if not isinstance(raw_issues, list):
        return []

    issues: list[Issue] = []
    for raw in raw_issues:
        if not isinstance(raw, dict):
            continue
        try:
            # Map severity and category, falling back to defaults
            severity_str = str(raw.get("severity", "medium")).lower()
            category_str = str(raw.get("category", "code_smell")).lower()

            try:
                severity = Severity(severity_str)
            except ValueError:
                severity = Severity.MEDIUM

            try:
                category = Category(category_str)
            except ValueError:
                category = Category.CODE_SMELL

            issue = Issue(
                file_path=file_path,
                title=str(raw.get("title", "Untitled Issue")),
                severity=severity,
                category=category,
                description=str(raw.get("description", "")),
                suggestion=str(raw.get("suggestion", "")),
                line_range=raw.get("line_range"),
            )
            issues.append(issue)
        except Exception:
            # Skip malformed issues
            continue

    return issues


def review_file(
    file_path: Path,
    target_dir: Path,
    model: str = "codellama",
    ollama_url: str = "http://localhost:11434",
    max_retries: int = 3,
) -> ScanResult:
    """
    Send a single file to the Ollama LLM for tech debt review.

    Returns a ScanResult with any issues found.
    """
    rel_path = str(file_path.relative_to(target_dir))

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return ScanResult(
            file_path=rel_path,
            model_used=model,
            error=f"Could not read file: {e}",
        )

    # Skip very small files (likely empty or just imports)
    if len(content.strip()) < 50:
        return ScanResult(file_path=rel_path, model_used=model)

    prompt = _build_prompt(rel_path, content)

    for attempt in range(max_retries):
        try:
            response = httpx.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "system": SYSTEM_PROMPT,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 4096,
                    },
                },
                timeout=300.0,  # Local LLMs can be slow
            )
            response.raise_for_status()
            result = response.json()
            response_text = result.get("response", "")

            issues = _parse_issues(response_text, rel_path)

            return ScanResult(
                file_path=rel_path,
                issues=issues,
                model_used=model,
            )

        except httpx.ConnectError:
            error_msg = (
                f"Cannot connect to Ollama at {ollama_url}. "
                "Is Ollama running? Start it with: ollama serve"
            )
            return ScanResult(
                file_path=rel_path,
                model_used=model,
                error=error_msg,
            )

        except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                console.print(
                    f"  [dim yellow]⚠ Retry {attempt + 1}/{max_retries} for {rel_path} "
                    f"(waiting {wait}s)[/]"
                )
                time.sleep(wait)
            else:
                return ScanResult(
                    file_path=rel_path,
                    model_used=model,
                    error=f"Failed after {max_retries} attempts: {e}",
                )

        except Exception as e:
            return ScanResult(
                file_path=rel_path,
                model_used=model,
                error=f"Unexpected error: {e}",
            )

    # Should not reach here, but just in case
    return ScanResult(file_path=rel_path, model_used=model, error="Unknown error")
