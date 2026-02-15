"""Category-specific prompts for tech debt analysis."""

from pathlib import Path

from ..models import Category

CATEGORY_PROMPTS: dict[Category, str] = {}


def _load_prompts() -> dict[Category, str]:
    """Lazy-load all category prompts."""
    prompts: dict[Category, str] = {}
    prompts_dir = Path(__file__).parent
    for category in Category:
        prompt_file = prompts_dir / f"{category.value}.txt"
        if prompt_file.exists():
            prompts[category] = prompt_file.read_text(encoding="utf-8").strip()
    return prompts


def get_prompt(category: Category) -> str:
    """Get the system prompt for a specific category."""
    if not CATEGORY_PROMPTS:
        CATEGORY_PROMPTS.update(_load_prompts())
    return CATEGORY_PROMPTS.get(category, "")


def get_all_prompts() -> dict[Category, str]:
    """Get all category prompts."""
    if not CATEGORY_PROMPTS:
        CATEGORY_PROMPTS.update(_load_prompts())
    return CATEGORY_PROMPTS
