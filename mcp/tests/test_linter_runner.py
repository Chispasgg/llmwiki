from unittest.mock import AsyncMock
from linter.runner import run_lint

FM = "---\ntitle: T\ndescription: D\ndate: 2026-01-01\ntags: [a,b]\n---\n"


class FakeFS:
    def __init__(self, docs, stale=None, uncited=None):
        self._docs, self._stale, self._uncited = docs, stale or [], uncited or []

    async def list_documents_with_content(self, kb_id):
        return self._docs

    async def find_stale_pages(self, kb_id):
        return self._stale

    async def find_uncited_sources(self, kb_id):
        return self._uncited


async def test_run_lint_aggregates(tmp_path):
    docs = [
        {
            "path": "/wiki/",
            "filename": "overview.md",
            "content": FM + "[a](a.md) | x | y |\n|---|---|",
        },
        {
            "path": "/wiki/",
            "filename": "a.md",
            "content": FM + "solo prosa",
        },  # sin visual
    ]
    fs = FakeFS(
        docs,
        stale=[{"path": "/wiki/", "filename": "a.md"}],
        uncited=[{"filename": "src.pdf"}],
    )
    findings = await run_lint(fs, "kb1", "kb-slug", str(tmp_path))
    checks = {f.check for f in findings}
    assert "visual" in checks  # a.md sin tabla/diagrama
    assert "stale" in checks and "uncited-source" in checks
