from models import Category


def _slugify(name: str) -> str:
    normalized = " ".join(name.strip().lower().split())
    return normalized.replace(" ", "-")


def _build_category_path(category: Category) -> str:
    parts = []
    current = category
    while current:
        parts.append(_slugify(current.name))
        current = current.parent
    return "/".join(reversed(parts))