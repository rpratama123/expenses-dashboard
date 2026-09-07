CATEGORY_LABELS = {"food_drink": "Food"}


def category_label(key: str) -> str:
    if key in CATEGORY_LABELS:
        return CATEGORY_LABELS[key]
    words = key.replace("_", " ").replace("-", " ").split()
    return " ".join(word.capitalize() for word in words) or "Uncategorized"
