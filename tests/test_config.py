"""Tests unitarios para api/config.py — campos de configuración."""


def test_max_upload_bytes_default():
    from config import settings

    assert settings.MAX_UPLOAD_BYTES == 104_857_600
