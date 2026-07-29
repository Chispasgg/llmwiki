"""Pure text-match helper for str_replace. No DB, no state."""


def validate_single_match(content: str, old_text: str) -> str | None:
    """Return an error string if old_text doesn't match exactly once, else None."""
    count = content.count(old_text)
    if count == 0:
        return "Error: no match found for old_text."
    if count > 1:
        return (
            f"Error: found {count} matches for old_text. "
            "Provide more context to match exactly once."
        )
    return None
