"""File scanner — walks directories, respects .gitignore, filters by extension."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pathspec


# Directories to always skip
SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".venv", "venv", "env", ".env",
    ".tox", ".nox",
    "dist", "build", ".next", ".nuxt",
    "vendor",
    ".idea", ".vscode",
    "coverage", ".nyc_output",
    "target",  # Rust / Java
    "bin", "obj",  # C# / .NET
}

# Default code file extensions
DEFAULT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".go", ".rs", ".java", ".cs",
    ".cpp", ".c", ".h", ".hpp",
    ".rb", ".php", ".swift", ".kt",
    ".scala", ".lua", ".ex", ".exs",
    ".vue", ".svelte",
}


def _load_gitignore(directory: Path) -> pathspec.PathSpec | None:
    """Load .gitignore patterns from the given directory."""
    gitignore_path = directory / ".gitignore"
    if gitignore_path.is_file():
        with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f)
    return None


def _is_binary(file_path: Path, sample_size: int = 8192) -> bool:
    """Quick heuristic to check if a file is binary."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(sample_size)
        # Check for null bytes — strong indicator of binary content
        if b"\x00" in chunk:
            return True
        return False
    except (OSError, PermissionError):
        return True


def scan_files(
    target_dir: Path,
    extensions: set[str] | None = None,
    max_file_size_kb: int = 100,
) -> Generator[Path, None, None]:
    """
    Recursively yield code file paths from target_dir.

    Skips:
    - Directories in SKIP_DIRS
    - Files not matching allowed extensions
    - Files larger than max_file_size_kb
    - Binary files
    - Files matched by .gitignore patterns
    """
    if extensions is None:
        extensions = DEFAULT_EXTENSIONS

    target_dir = target_dir.resolve()
    max_bytes = max_file_size_kb * 1024

    # Load root .gitignore
    gitignore = _load_gitignore(target_dir)

    def _walk(directory: Path) -> Generator[Path, None, None]:
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return

        for entry in entries:
            # Get path relative to target for .gitignore matching
            try:
                rel_path = entry.relative_to(target_dir)
            except ValueError:
                continue

            # Check .gitignore
            if gitignore and gitignore.match_file(str(rel_path)):
                continue

            if entry.is_dir():
                if entry.name in SKIP_DIRS:
                    continue
                yield from _walk(entry)

            elif entry.is_file():
                # Extension filter
                if entry.suffix.lower() not in extensions:
                    continue

                # Size filter
                try:
                    if entry.stat().st_size > max_bytes:
                        continue
                except OSError:
                    continue

                # Binary filter
                if _is_binary(entry):
                    continue

                yield entry

    yield from _walk(target_dir)
