"""BZ-shared — Buzón input guards.

Single module for cross-service validation that must not be duplicated.
Import from here; never redefine these checks in individual service files.
"""

from fastapi import HTTPException


def reject_newlines(field: str, value: str) -> None:
    """Raise HTTP 400 if *value* contains a newline character.

    Any field that ends up in the single-line buzón format must not contain
    ``\\n`` or ``\\r``.  A line-break would let a caller inject extra parseable
    lines — forging entries as if another user wrote them.
    This is the single validation point; do not duplicate per-field checks.
    """
    if "\n" in value or "\r" in value:
        raise HTTPException(
            status_code=400,
            detail={"message": f"{field} must be a single line (no newlines allowed)"},
        )
