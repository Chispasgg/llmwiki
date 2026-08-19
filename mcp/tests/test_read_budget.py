"""El presupuesto de lectura se deriva de config (READ_MAX_TOKENS), no hardcodeado."""


def test_char_budget_derives_from_config(monkeypatch):
    from config import settings
    import tools.read as read

    monkeypatch.setattr(settings, "READ_MAX_TOKENS", 1000)
    assert read._char_budget() == 4000  # ~4 chars/token


def test_char_budget_default_preserves_120k():
    from config import settings
    import tools.read as read

    # Default 30000 tokens * 4 = 120_000 chars → mismo comportamiento que el tope viejo.
    assert settings.READ_MAX_TOKENS == 30000
    assert read._char_budget() == 120_000
