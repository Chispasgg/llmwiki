from unittest.mock import AsyncMock, MagicMock
from linter.reconcile import reconcile_comments
from linter.checks import Finding


def _conn():
    conn = AsyncMock()
    acq = MagicMock()
    acq.__aenter__ = AsyncMock(return_value=conn)
    acq.__aexit__ = AsyncMock(return_value=False)
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    conn.fetchrow = AsyncMock(return_value={"id": "cnew"})
    return conn, acq


async def test_reconcile_creates_and_resolves():
    conn, acq = _conn()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acq)
    # doc con un finding broken-link nuevo; existe un maint:stale viejo que ya no aplica
    pool.fetch = AsyncMock(
        return_value=[
            {"id": "cold", "target_text": "maint:stale:/wiki/x.md", "document_id": "d1"}
        ]
    )
    findings = [Finding("broken-link", "/wiki/x.md", "error", "roto", "arregla")]
    # doc id lookup: la impl resuelve page_path -> document_id (mockeado abajo)
    pool.fetchval = AsyncMock(return_value="d1")
    out = await reconcile_comments(pool, "kb1", findings, ["broken-link", "stale"])
    assert out["created"] == 1 and out["resolved"] == 1
    exec_sql = " ".join(c.args[0] for c in conn.execute.call_args_list)
    row_sql = " ".join(c.args[0] for c in conn.fetchrow.call_args_list)
    assert "INSERT INTO wiki_comments" in row_sql
    assert "status = 'resolved'" in exec_sql
    assert "UPDATE documents" not in (exec_sql + row_sql)


async def test_reconcile_does_not_resolve_out_of_scope_check():
    """Comentarios de checks fuera de comment_checks no deben resolverse."""
    conn, acq = _conn()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acq)
    # Solo existe un comentario de check 'frontmatter', fuera del scope de la llamada
    pool.fetch = AsyncMock(
        return_value=[
            {
                "id": "cold",
                "target_text": "maint:frontmatter:/wiki/x.md",
                "document_id": "d1",
            }
        ]
    )
    pool.fetchval = AsyncMock(return_value="d1")
    findings = []
    # comment_checks no incluye 'frontmatter' → el comentario existente no se toca
    out = await reconcile_comments(pool, "kb1", findings, ["broken-link"])
    assert out["created"] == 0 and out["resolved"] == 0
    exec_sql = " ".join(c.args[0] for c in conn.execute.call_args_list)
    assert "status = 'resolved'" not in exec_sql


async def test_reconcile_uncited_source_no_key_collision():
    """Dos findings uncited-source con distinto filename pero mismo page_path
    deben crear DOS comentarios distintos (no colapsar a uno)."""
    conn, acq = _conn()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acq)
    pool.fetch = AsyncMock(return_value=[])  # sin comentarios existentes
    pool.fetchval = AsyncMock(return_value="doverview")  # doc_id de overview.md
    findings = [
        Finding(
            "uncited-source",
            "/wiki/overview.md",
            "warning",
            "la fuente «a.pdf» no está citada",
            "Cítala o retírala.",
            key="maint:uncited-source:a.pdf",
        ),
        Finding(
            "uncited-source",
            "/wiki/overview.md",
            "warning",
            "la fuente «b.pdf» no está citada",
            "Cítala o retírala.",
            key="maint:uncited-source:b.pdf",
        ),
    ]
    out = await reconcile_comments(pool, "kb1", findings, ["uncited-source"])
    assert out["created"] == 2, f"esperado 2 creados, obtenido {out['created']}"
    assert out["resolved"] == 0
