"""BZ-007 — Buzón create (mine) service (hosted only).

Creates the session user's buzón document in a KB, idempotently.

Public API
----------
``create_my_inbox`` — if the user already has a buzón whose frontmatter
``email`` matches the session email (case-insensitive), returns it unchanged
(HTTP 200).  Otherwise computes a slug, resolves any filename collision
against existing inboxes, and delegates the actual INSERT to
``HostedDocumentService.create_note`` (permission: editor+).

Email source
------------
The ``email`` written into the frontmatter always comes from the authenticated
session (``session_email`` parameter).  The ``name`` body parameter only
influences the slug and the displayed title — never the email field.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

import yaml
from fastapi import HTTPException

from services.buzon.guards import reject_newlines
from services.buzon.paths import BUZON_PATH
from services.buzon.read import list_inboxes
from services.hosted import HostedDocumentService


def _slugify(name: str) -> str:
    """Transliterate *name* to a URL-safe slug.

    Same algorithm as ``hosted._slugify`` (NFKD + ASCII + lowercase +
    collapse non-alphanumerics to hyphens) with a domain-appropriate fallback
    of ``"usuario"`` instead of ``"kb"``.

    DEUDA TÉCNICA (MENOR-1 / BZ-007): esta función duplica ``hosted._slugify``.
    Extraer a ``services/buzon/utils.py`` (o a ``shared/``) en una tarea
    dedicada, actualizando también el import en ``hosted.py``.  No mover ahora
    para no tocar un módulo no relacionado en este rework.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    slug = ascii_name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug or "usuario"


def _build_inbox_content(email: str, title: str, today: str) -> str:
    """Return the YAML frontmatter (plus empty body) for a new buzón document.

    ``email`` is always the authenticated session value — it is the canonical
    ownership key for the inbox and must never come from caller-supplied input.

    The frontmatter is built with ``yaml.safe_dump`` (never an f-string) so
    that any YAML-special characters in ``title`` (colons, brackets, newlines…)
    are properly quoted/escaped and cannot corrupt the structure or inject keys.
    """
    frontmatter = {
        "email": email,
        "title": title,
        "date": today,
        "tags": ["buzon"],
    }
    dumped = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
    return f"---\n{dumped}---\n"


async def create_my_inbox(
    pool,
    kb_id: str,
    user_id: str,
    session_email: str,
    display_name: str | None,
    name: str | None,
    is_superadmin: bool = False,
) -> dict:
    """Create the session user's buzón in the KB, or return the existing one.

    Idempotency
    -----------
    Keyed on ``session_email``.  If a buzón document already exists under
    ``BUZON_PATH`` whose frontmatter ``email`` matches ``session_email``
    (case-insensitive — handled by ``list_inboxes``), it is returned as-is
    (HTTP 200, no INSERT).

    Slug collision
    --------------
    If ``<base_slug>.md`` is already taken by another user's inbox, the
    filename becomes ``<base_slug>-2.md``, ``<base_slug>-3.md``, etc., until
    a free name is found.  Same suffix pattern as the native "create page"
    endpoint.

    Permissions
    -----------
    Delegated to ``HostedDocumentService.create_note``; callers without
    editor+ access receive the 404 that create_note raises.

    Parameters
    ----------
    pool:
        asyncpg pool.
    kb_id:
        UUID of the target knowledge base.
    user_id:
        Authenticated user's UUID (used for DB ownership in create_note).
    session_email:
        Email from the authenticated session — written into frontmatter.
        Must be non-empty; raises 422 otherwise.
    display_name:
        User's display_name; used as the slug/title source when ``name``
        is absent.
    name:
        Optional name from the request body; influences slug and title only.
        Must not contain newlines (raises 400 via reject_newlines).
    is_superadmin:
        Passed to HostedDocumentService for the superadmin permission path.

    Returns
    -------
    dict with keys: ``doc_id``, ``path``, ``filename``, ``email``.

    Note — TOCTOU slug race
    -----------------------
    Two concurrent requests for users whose slugs collide could both observe
    the slug as free and attempt to INSERT the same filename simultaneously.
    A UNIQUE(knowledge_base_id, path, filename) constraint at the DB level
    would close this window (the second INSERT would fail with a conflict
    error that could be retried).  This is out of scope for BZ-007.
    """
    # Guard: session must have a non-empty email or idempotency key is unusable
    if not session_email or not session_email.strip():
        raise HTTPException(
            status_code=422,
            detail={"message": "La cuenta no tiene email"},
        )

    # Guard: name must not contain newlines (YAML injection prevention, depth-in)
    if name:
        reject_newlines("name", name)

    # Step 1 — idempotency: check for an existing inbox owned by session_email
    inboxes = await list_inboxes(pool, kb_id, session_email)
    for inbox in inboxes:
        if inbox["is_mine"]:
            return {
                "doc_id": inbox["doc_id"],
                "path": inbox["path"],
                "filename": inbox["filename"],
                "email": inbox["email"],
            }

    # Step 2 — compute base slug from body name or session display_name
    raw_name = (name or display_name or "").strip()
    base_slug = _slugify(raw_name)

    # Step 3 — resolve filename: skip any slug already used by another inbox
    taken = {inbox["filename"] for inbox in inboxes}
    slug = base_slug
    n = 1
    while f"{slug}.md" in taken:
        n += 1
        slug = f"{base_slug}-{n}"
    filename = f"{slug}.md"

    # Step 4 — build content; email ALWAYS from session, never from body
    title = (name or display_name or slug).strip() or slug
    today = date.today().isoformat()
    content = _build_inbox_content(session_email, title, today)

    # Step 5 — delegate INSERT + permission check to create_note
    doc_svc = HostedDocumentService(pool, user_id, is_superadmin=is_superadmin)
    row = await doc_svc.create_note(kb_id, filename, BUZON_PATH, content)

    return {
        "doc_id": str(row["id"]),
        "path": BUZON_PATH,
        "filename": filename,
        "email": session_email,
    }
