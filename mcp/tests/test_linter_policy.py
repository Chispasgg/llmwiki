from linter.policy import load_policy, DEFAULT_POLICY
from linter.checks import check_scope, check_counts

FM = "---\ntitle: T\ndescription: D\ndate: 2026-01-01\ntags: [a,b]\n---\n"


def test_load_policy_missing_returns_defaults(tmp_path):
    pol = load_policy("no-existe", str(tmp_path))
    assert pol["index_max_entries"] == DEFAULT_POLICY["index_max_entries"]
    assert pol["scope"] == [] and pol["counts"] == []


def test_load_policy_yaml(tmp_path):
    (tmp_path / "mi-kb.yaml").write_text(
        "scope:\n  - label: secreto\n    pattern: 'AKIA[0-9A-Z]+'\n    severity: error\n"
        "index_max_entries: 10\n"
    )
    pol = load_policy("mi-kb", str(tmp_path))
    assert pol["index_max_entries"] == 10
    assert pol["scope"][0]["label"] == "secreto"


def test_scope_multiline():
    # patrón que solo casa si se evalúa en modo multilínea/DOTALL (término partido)
    policy = {
        "scope": [
            {"label": "frase", "pattern": r"fuera\s+de\s+ambito", "severity": "error"}
        ]
    }
    doc = {
        "path": "/wiki/",
        "filename": "p.md",
        "content": FM + "esto está fuera\nde ambito del todo",
    }
    f = check_scope(doc, policy)
    assert f and f[0].check == "scope" and f[0].severity == "error"


def test_counts_mismatch():
    policy = {
        "counts": [
            {
                "label": "fuentes",
                "page": "overview.md",
                "extract": r"Fuentes:\s*(\d+)",
                "equals": "sources",
                "severity": "error",
            }
        ]
    }
    docs = [
        {"path": "/wiki/", "filename": "overview.md", "content": FM + "Fuentes: 5"},
        {"path": "/", "filename": "a.pdf", "content": ""},
        {"path": "/", "filename": "b.pdf", "content": ""},
    ]
    f = check_counts(docs, policy)
    assert f and f[0].check == "count"  # declara 5, hay 2 fuentes
