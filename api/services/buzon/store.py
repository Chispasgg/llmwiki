"""Buzón store — atomic write primitives for wiki pages (hosted / Postgres).

Provides two low-level operations that honour the golden rule: never lose or
corrupt a wiki page.  Both use **optimistic concurrency control** (a
version-checked UPDATE) so concurrent writes to other lines are always
preserved.

No permission logic here — callers (BZ-004 / BZ-005 endpoints) own that.
"""

from __future__ import annotations

from fastapi import HTTPException

from services.buzon.parser import extract_id
from services.chunker import chunk_text
from services.hosted import store_chunks

# Maximum number of write attempts before giving up (1 original + 1 retry).
_MAX_ATTEMPTS = 2


# ── Private helpers ───────────────────────────────────────────────────────────


async def _read_doc(pool, doc_id: str) -> dict:
    """Fetch (content, version, path, kb_id) for a document, or raise 404."""
    row = await pool.fetchrow(
        "SELECT content, version, path, knowledge_base_id::text AS kb_id "
        "FROM documents WHERE id = $1",
        doc_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)


async def _write_with_version_check(
    pool, doc_id: str, new_content: str, user_id: str, expected_version: int
) -> dict | None:
    """Attempt a version-guarded UPDATE.

    Returns the RETURNING row on success, or None when the version no longer
    matches (concurrent write detected — caller should retry or raise 409).
    """
    return await pool.fetchrow(
        "UPDATE documents "
        "SET content = $1, version = version + 1, updated_at = now(), "
        "    last_edited_by = $3, last_edited_via = 'web' "
        "WHERE id = $2 AND version = $4 "
        "RETURNING id, content, version",
        new_content,
        doc_id,
        user_id,
        expected_version,
    )


async def _persist_after_write(
    pool,
    doc_id: str,
    user_id: str,
    old_content: str,
    new_content: str,
    old_version: int,
    path: str,
    kb_id: str | None,
    updated_row: dict,
) -> dict:
    """Insert document history and reindex after a successful write.

    History is only inserted when the page is under /wiki/ and the content
    actually changed, matching the behaviour of update_content.
    """
    if (
        old_content.strip()
        and old_content.strip() != new_content.strip()
        and (path or "").startswith("/wiki/")
    ):
        await pool.execute(
            "INSERT INTO document_history (document_id, user_id, content, version) "
            "VALUES ($1, $2, $3, $4)",
            doc_id,
            user_id,
            old_content,
            old_version,
        )

    if kb_id:
        chunks = chunk_text(new_content) if new_content else []
        await store_chunks(pool, doc_id, user_id, kb_id, chunks)

    return dict(updated_row)


# ── Public API ────────────────────────────────────────────────────────────────


async def append_line(pool, doc_id: str, line: str, user_id: str) -> dict:
    """Append *line* as the last line of document *doc_id*, atomically.

    Algorithm
    ---------
    1. Read ``(content, version, path, kb_id)``.
    2. Build ``new_content``: existing content (trailing newlines stripped) +
       exactly one newline + ``line`` + newline.
    3. ``UPDATE … WHERE id = $doc AND version = $expected RETURNING …``.
    4. Zero rows returned (concurrent write detected) → re-read once and retry.
    5. Second attempt also returns zero rows → raise HTTPException 409.
    6. Success → persist history + reindex.

    Returns
    -------
    The ``{id, content, version}`` dict from the RETURNING clause.
    """
    for _ in range(_MAX_ATTEMPTS):
        doc = await _read_doc(pool, doc_id)
        old_content = doc["content"] or ""
        expected_version = doc["version"]

        stripped = old_content.rstrip("\n")
        new_content = (stripped + "\n" if stripped else "") + line + "\n"

        updated = await _write_with_version_check(
            pool, doc_id, new_content, user_id, expected_version
        )
        if updated is not None:
            return await _persist_after_write(
                pool,
                doc_id,
                user_id,
                old_content,
                new_content,
                expected_version,
                doc["path"],
                doc["kb_id"],
                updated,
            )
        # Conflict: loop continues to re-read and retry

    raise HTTPException(
        status_code=409,
        detail="Conflict: document was modified concurrently. Please retry.",
    )


async def edit_line(pool, doc_id: str, line_id: str, transform, user_id: str) -> dict:
    """Edit the single line whose buzón ID equals *line_id*, atomically.

    *transform* is a callable ``(raw: str) -> str`` applied to the matched
    line.  It receives the **current** raw string (re-read on each attempt) so
    it always operates on fresh data.

    Algorithm
    ---------
    1. Read ``(content, version, path, kb_id)``.
    2. Split content on ``\\n``, locate the unique line where
       ``extract_id(raw) == line_id``.
       - Not found → raise HTTPException 404 (immediately, no retry).
       - More than one → raise HTTPException 409 (data integrity issue).
    3. Apply *transform* to the matched line; rejoin.
    4. ``UPDATE … WHERE id = $doc AND version = $expected RETURNING …``.
    5. Conflict (zero rows) → re-read once and retry from step 2 with fresh
       content.  *transform* is re-applied to the fresh line.
    6. Second conflict → raise HTTPException 409.
    7. Success → persist history + reindex.

    Returns
    -------
    The ``{id, content, version}`` dict from the RETURNING clause.
    """
    for _ in range(_MAX_ATTEMPTS):
        doc = await _read_doc(pool, doc_id)
        old_content = doc["content"] or ""
        expected_version = doc["version"]

        # split('\n') on "a\nb\n" gives ['a', 'b', ''] — round-trips perfectly
        lines = old_content.split("\n")
        matching = [i for i, raw in enumerate(lines) if extract_id(raw) == line_id]

        if len(matching) == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Line with ID '{line_id}' not found in document.",
            )
        if len(matching) > 1:
            # Should never happen in a well-formed buzón, but guard it explicitly
            raise HTTPException(
                status_code=409,
                detail=f"Ambiguous: {len(matching)} lines share ID '{line_id}'.",
            )

        idx = matching[0]
        new_lines = list(lines)
        new_lines[idx] = transform(lines[idx])
        new_content = "\n".join(new_lines)

        updated = await _write_with_version_check(
            pool, doc_id, new_content, user_id, expected_version
        )
        if updated is not None:
            return await _persist_after_write(
                pool,
                doc_id,
                user_id,
                old_content,
                new_content,
                expected_version,
                doc["path"],
                doc["kb_id"],
                updated,
            )
        # Conflict: loop continues with a fresh read

    raise HTTPException(
        status_code=409,
        detail="Conflict: document was modified concurrently. Please retry.",
    )
