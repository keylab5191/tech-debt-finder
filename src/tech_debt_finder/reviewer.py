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
from .prompts import get_prompt

console = Console(stderr=True)


def _get_system_prompt(category: Category | None = None) -> str:
    """Get the system prompt for a specific category, or the default if None."""
    if category is None:
        return SYSTEM_PROMPT
    return get_prompt(category)


# The system prompt instructs the LLM to return structured JSON issues
SYSTEM_PROMPT = """You are a senior software engineer performing a tech debt review.
Analyze the provided source code and identify the MOST IMPORTANT technical debt, code smells, or improvement opportunities.

Look for (prioritize higher-impact items):
- Code smells (dead code, meaningful magic numbers, overly long functions, god classes)
- Complexity issues (deeply nested logic, complex conditionals)
- Poor naming (unclear variable/function/class names)
- Structural problems (poor file organization, tight coupling, missing abstractions)
- Code duplication
- Missing or poor error handling
- Security concerns (hardcoded secrets, SQL injection, XSS)
- Performance issues (N+1 queries, unnecessary loops, memory leaks)
- Readability problems (missing docs, unclear intent, overly clever code)
- Best practices violations (not following language idioms, anti-patterns)

Do NOT report as magic numbers: format specifiers (e.g. .2f, .1f), padding widths in format strings, or numbers inside comments. Only report numbers that are configuration/business values (timeouts, limits, sizes) that would benefit from being named constants.
Report each distinct issue ONCE (one finding per logical issue, not one per occurrence). Prefer quality over quantity; 5–15 strong issues per file is better than many duplicates.

Respond ONLY with a JSON array of issues. Each issue must be an object with these exact keys:
- "title": short descriptive title (string)
- "severity": one of "critical", "high", "medium", "low" (string)
- "category": one of "code_smell", "complexity", "naming", "structure", "duplication", "error_handling", "security", "performance", "readability", "best_practices" (string)
- "description": detailed explanation of the issue (string)
- "suggestion": how to fix it (string)
- "line_range": approximate line range like "10-25" or null if not applicable (string or null)

If the code is clean and has no issues, respond with an empty array: []

IMPORTANT: Respond with ONLY the JSON array, no other text, no markdown fences, nothing else."""


def _build_prompt(file_path: str, content: str, category: Category | None = None) -> str:
    """Build the user prompt with file context."""
    category_context = f" focusing on {category.value}" if category else ""
    return f"""Review the following file for tech debt issues{category_context}.

File: {file_path}

```
{content}
```

Respond with a JSON array of issues found."""


def _extract_json_array(text: str) -> str | None:
    """Extract the first complete JSON array using bracket matching (ignores ] inside strings)."""
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    quote_char = None
    i = start
    while i < len(text):
        c = text[i]
        if escape:
            escape = False
            i += 1
            continue
        if in_string:
            if c == "\\":
                escape = True
            elif c == quote_char:
                in_string = False
            i += 1
            continue
        if c in ('"', "'"):
            in_string = True
            quote_char = c
            i += 1
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return None


def _repair_json(s: str) -> str:
    """Fix trailing comma only at the very end of the string (safe for strings containing ', ]')."""
    s = re.sub(r",\s*\]\s*$", "]", s)
    s = re.sub(r",\s*\}\s*$", "}", s)
    return s


def _extract_json_objects(text: str) -> list[dict[str, Any]]:
    """Extract complete {...} JSON objects from text (for truncated response fallback)."""
    objects: list[dict[str, Any]] = []
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        depth = 0
        in_string = False
        escape = False
        quote_char = None
        j = start
        while j < len(text):
            c = text[j]
            if escape:
                escape = False
                j += 1
                continue
            if in_string:
                if c == "\\":
                    escape = True
                elif c == quote_char:
                    in_string = False
                j += 1
                continue
            if c in ('"', "'"):
                in_string = True
                quote_char = c
                j += 1
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    chunk = text[start : j + 1]
                    try:
                        obj = json.loads(chunk)
                        if isinstance(obj, dict) and "title" in obj:
                            objects.append(obj)
                    except json.JSONDecodeError:
                        pass
                    j += 1
                    break
            j += 1
        i = j if j > start else start + 1
    return objects


def _write_debug_response(response_text: str, file_path: str, debug_dir: Path) -> None:
    """Write raw LLM response to a debug file when parsing fails."""
    safe_name = re.sub(r'[<>:"/\\|?*]', "_", file_path).strip() or "unknown"
    debug_dir.mkdir(parents=True, exist_ok=True)
    out = debug_dir / f"{safe_name}.txt"
    out.write_text(response_text, encoding="utf-8")
    console.print(f"  [dim]Debug response written to {out}[/]")


def _parse_issues(
    response_text: str, file_path: str, debug_dir: Path | None = None
) -> tuple[list[Issue], bool]:
    """Parse LLM response into structured Issue objects. Returns (issues, parse_failed)."""
    text = response_text.strip()

    # Remove markdown code fences (case-insensitive: ```json, ```JSON, etc.)
    text = re.sub(r"^```(?i:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()

    # Extract the first complete JSON array (bracket-matched)
    extracted = _extract_json_array(text)
    if extracted is not None:
        text = extracted

    # Try parsing; if it fails, try with trailing-comma repair (end of string only)
    raw_issues: list[dict[str, Any]] | None = None
    parsed_as_json = False
    for candidate in (text, _repair_json(text)):
        try:
            raw_issues = json.loads(candidate)
            if isinstance(raw_issues, list):
                parsed_as_json = True
            break
        except json.JSONDecodeError:
            continue

    # Fallback: extract complete {...} objects (handles truncated or malformed response)
    if raw_issues is None:
        raw_issues = _extract_json_objects(text)
    if raw_issues is None:
        raw_issues = []

    if not isinstance(raw_issues, list):
        raw_issues = []

    # Empty list from successful JSON parse means "no issues" (valid); only warn on actual parse failure
    if not raw_issues and not parsed_as_json:
        snippet = response_text.strip()[:500]
        console.print(f"  [dim yellow]⚠ Could not parse LLM response for {file_path}[/]")
        console.print(f"  [dim]Response snippet: {snippet!r}[/]")
        if debug_dir is not None:
            _write_debug_response(response_text, file_path, debug_dir)
        return [], True

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

    return issues, False


def review_file(
    file_path: Path,
    target_dir: Path,
    model: str = "qwen2.5-coder:7b",
    ollama_url: str = "http://localhost:11434",
    max_retries: int = 3,
    client: httpx.Client | None = None,
    category: Category | None = None,
) -> ScanResult:
    """
    Send a single file to the Ollama LLM for tech debt review.

    Returns a ScanResult with any issues found.
    """
    rel_path = str(file_path.relative_to(target_dir))

    try:
        file_read_start = time.perf_counter()
        content = file_path.read_text(encoding="utf-8", errors="replace")
        console.print(f"    [dim]{time.perf_counter() - file_read_start:.2f}s read file[/]")
    except Exception as e:
        return ScanResult(
            file_path=rel_path,
            model_used=model,
            error=f"Could not read file: {e}",
        )

    # Skip very small files (boilerplate, small __init__.py, etc.)
    if len(content.strip()) < 150:
        return ScanResult(file_path=rel_path, model_used=model)

    prompt_build_start = time.perf_counter()
    prompt = _build_prompt(rel_path, content, category)
    console.print(f"    [dim]{time.perf_counter() - prompt_build_start:.2f}s build prompt ({len(prompt)} chars)[/]")

    console.print(f"  [dim]Analyzing {rel_path} for {category.value if category else 'all categories'}...[/]")

    system_prompt = _get_system_prompt(category)

    for attempt in range(max_retries):
        try:
            console.print(f"    [dim]Calling Ollama (attempt {attempt + 1})...[/]")
            ollama_call_start = time.perf_counter()
            # keep_alive: keep model loaded (in GPU memory) for run duration so GPU usage is visible
            post_kw = dict(
                json={
                    "model": model,
                    "prompt": prompt,
                    "system": system_prompt,
                    "stream": False,
                    "keep_alive": "30m",
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1024,   # cap to reduce duplicate/low-value issues
                        "num_ctx": 8192,       # context window (prompt + response)
                    },
                },
                timeout=300.0,  # Local LLMs can be slow
            )
            if client is not None:
                response = client.post(f"{ollama_url.rstrip('/')}/api/generate", **post_kw)
            else:
                response = httpx.post(f"{ollama_url.rstrip('/')}/api/generate", **post_kw)
            response.raise_for_status()
            console.print(f"    [dim]{time.perf_counter() - ollama_call_start:.2f}s Ollama returned[/]")

            response_parse_start = time.perf_counter()
            result = response.json()
            response_text = result.get("response", "")

            # Extract performance metrics
            # Ollama returns durations in nanoseconds
            eval_count = result.get("eval_count", 0)
            eval_duration_ns = result.get("eval_duration", 0)
            load_duration_ns = result.get("load_duration", 0)
            prompt_eval_count = result.get("prompt_eval_count", 0)
            prompt_eval_duration_ns = result.get("prompt_eval_duration", 0)

            # Calculate tokens per second (avoid division by zero)
            eval_duration_s = eval_duration_ns / 1_000_000_000
            load_duration_s = load_duration_ns / 1_000_000_000
            prompt_eval_duration_s = prompt_eval_duration_ns / 1_000_000_000
            tokens_per_second = 0.0
            if eval_duration_s > 0:
                tokens_per_second = eval_count / eval_duration_s

            # Log metrics (load + prompt eval often dominate first-file time)
            load_str = ""
            if load_duration_s > 0.1:
                load_str = f"Loaded in {load_duration_s:.1f}s. "
            prompt_str = ""
            if prompt_eval_duration_s > 0.5:
                prompt_str = f"Prompt eval {prompt_eval_duration_s:.1f}s. "
            console.print(
                f"  [dim]LLM: {load_str}{prompt_str}{eval_count} tokens in {eval_duration_s:.2f}s "
                f"({tokens_per_second:.2f} t/s)[/]"
            )

            debug_dir = Path.cwd() / "tech_debt_debug"
            issues, parse_failed = _parse_issues(response_text, rel_path, debug_dir=debug_dir)
            console.print(f"    [dim]{time.perf_counter() - response_parse_start:.2f}s parse response[/]")

            metrics = {
                "eval_count": eval_count,
                "eval_duration_ns": eval_duration_ns,
                "load_duration_ns": load_duration_ns,
                "prompt_eval_count": prompt_eval_count,
                "prompt_eval_duration_ns": prompt_eval_duration_ns,
                "tokens_per_second": tokens_per_second,
            }

            return ScanResult(
                file_path=rel_path,
                issues=issues,
                model_used=model,
                performance_metrics=metrics,
                parse_failed=parse_failed,
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

        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                console.print(f"  [dim yellow]⚠ Timeout - Retrying {attempt + 1}...[/]")
                continue
            return ScanResult(
                file_path=rel_path,
                model_used=model,
                error=f"Timeout after {max_retries} attempts",
            )

        except httpx.HTTPStatusError as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                console.print(
                    f"  [dim yellow]⚠ Error {e.response.status_code} - Retry {attempt + 1}/{max_retries} "
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

    return ScanResult(file_path=rel_path, model_used=model, error="Unknown error")
