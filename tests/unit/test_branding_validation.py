"""Unit tests for branding PUT validation.

Tests the pure `validate_branding_input` function extracted from superadmin.py.
No database or HTTP layer involved.
"""

import base64

import pytest
from fastapi import HTTPException

from routes._branding_helpers import validate_branding_input


# ── org_name ─────────────────────────────────────────────────────


def test_org_name_stripped():
    name, _, _ = validate_branding_input("  Acme  ", None, None)
    assert name == "Acme"


def test_org_name_empty_becomes_none():
    name, _, _ = validate_branding_input("", None, None)
    assert name is None


def test_org_name_whitespace_only_becomes_none():
    name, _, _ = validate_branding_input("   ", None, None)
    assert name is None


def test_org_name_exactly_60_chars_ok():
    name, _, _ = validate_branding_input("A" * 60, None, None)
    assert name == "A" * 60


def test_org_name_61_chars_raises_422():
    with pytest.raises(HTTPException) as exc_info:
        validate_branding_input("A" * 61, None, None)
    assert exc_info.value.status_code == 422
    assert "60" in exc_info.value.detail["message"]


def test_org_name_none_ok():
    name, logo, mime = validate_branding_input(None, None, None)
    assert name is None
    assert logo is None
    assert mime is None


# ── logo_data_uri — mime allowlist ────────────────────────────────


def _make_data_uri(mime: str, size_bytes: int = 100) -> str:
    data = b"x" * size_bytes
    b64 = base64.b64encode(data).decode()
    return f"data:{mime};base64,{b64}"


@pytest.mark.parametrize(
    "mime", ["image/svg+xml", "image/png", "image/jpeg", "image/webp"]
)
def test_allowed_mime_ok(mime: str):
    uri = _make_data_uri(mime)
    _, logo, logo_mime = validate_branding_input(None, uri, mime)
    assert logo == uri
    assert logo_mime == mime


@pytest.mark.parametrize(
    "bad_mime",
    [
        "image/gif",
        "image/bmp",
        "text/html",
        "application/octet-stream",
        "image/PNG",  # allowlist is case-sensitive; uppercase must be rejected
    ],
)
def test_disallowed_mime_raises_422(bad_mime: str):
    uri = _make_data_uri(bad_mime)
    with pytest.raises(HTTPException) as exc_info:
        validate_branding_input(None, uri, bad_mime)
    assert exc_info.value.status_code == 422
    assert bad_mime in exc_info.value.detail["message"]


# ── logo_data_uri — size ─────────────────────────────────────────


def test_logo_exactly_512kb_ok():
    uri = _make_data_uri("image/png", 512 * 1024)
    _, logo, _ = validate_branding_input(None, uri, "image/png")
    assert logo is not None


def test_logo_over_512kb_raises_422():
    uri = _make_data_uri("image/png", 512 * 1024 + 1)
    with pytest.raises(HTTPException) as exc_info:
        validate_branding_input(None, uri, "image/png")
    assert exc_info.value.status_code == 422
    assert "512" in exc_info.value.detail["message"]


# ── logo_data_uri — mime mismatch ─────────────────────────────────


def test_mime_mismatch_raises_422():
    uri = _make_data_uri("image/png")
    with pytest.raises(HTTPException) as exc_info:
        validate_branding_input(None, uri, "image/jpeg")
    assert exc_info.value.status_code == 422
    assert "coincide" in exc_info.value.detail["message"]


# ── logo_data_uri — malformed ─────────────────────────────────────


def test_missing_comma_raises_422():
    with pytest.raises(HTTPException) as exc_info:
        validate_branding_input(None, "data:image/png;base64NOCOMMA", "image/png")
    assert exc_info.value.status_code == 422


def test_missing_base64_tag_raises_422():
    with pytest.raises(HTTPException) as exc_info:
        validate_branding_input(None, "data:image/png,abc123", "image/png")
    assert exc_info.value.status_code == 422


def test_invalid_base64_raises_422():
    # Valid header but invalid base64 characters
    with pytest.raises(HTTPException) as exc_info:
        validate_branding_input(
            None, "data:image/png;base64,!!!not-base64!!!", "image/png"
        )
    assert exc_info.value.status_code == 422


# ── logo None → logo_mime forced None ────────────────────────────


def test_logo_none_forces_mime_none():
    _, logo, logo_mime = validate_branding_input(None, None, "image/png")
    assert logo is None
    assert logo_mime is None
