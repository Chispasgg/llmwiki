"""Unit tests for CLI network detection functions (_local_ip, _load_conf, _resolve_network)."""

import importlib.machinery
import importlib.util
import socket
from pathlib import Path

# The 'llmwiki' CLI has no .py extension — load it explicitly.
_CLI_PATH = Path(__file__).parent.parent.parent / "llmwiki"
_loader = importlib.machinery.SourceFileLoader("llmwiki", str(_CLI_PATH))
_spec = importlib.util.spec_from_loader("llmwiki", _loader)
cli = importlib.util.module_from_spec(_spec)
_loader.exec_module(cli)


def test_local_ip_returns_valid_ipv4():
    ip = cli._local_ip()
    parts = ip.split(".")
    assert len(parts) == 4
    assert all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def test_local_ip_not_loopback_when_network_available():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            has_network = True
    except Exception:
        has_network = False

    if has_network:
        assert cli._local_ip() != "127.0.0.1"


def test_load_conf_returns_empty_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path / "llmwiki")
    assert cli._load_conf() == {}


def test_load_conf_parses_key_value(monkeypatch, tmp_path):
    conf_dir = tmp_path / "config"
    conf_dir.mkdir()
    (conf_dir / "llmwiki-launcher.conf").write_text(
        'LAN_HOST="192.168.1.10"\n'
        'APP_URL="http://192.168.1.10:1504"\n'
        "# comentario\n"
        "\n"
        'NEXT_PUBLIC_API_URL="http://192.168.1.10:1503"\n'
    )
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path / "llmwiki")
    conf = cli._load_conf()
    assert conf["LAN_HOST"] == "192.168.1.10"
    assert conf["APP_URL"] == "http://192.168.1.10:1504"
    assert conf["NEXT_PUBLIC_API_URL"] == "http://192.168.1.10:1503"


def test_load_conf_ignores_empty_values(monkeypatch, tmp_path):
    conf_dir = tmp_path / "config"
    conf_dir.mkdir()
    (conf_dir / "llmwiki-launcher.conf").write_text('LAN_HOST=""\nAPI_PORT="1503"\n')
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path / "llmwiki")
    conf = cli._load_conf()
    assert "LAN_HOST" not in conf
    assert conf["API_PORT"] == "1503"


def test_resolve_network_host_flag_takes_precedence(monkeypatch, tmp_path):
    conf_dir = tmp_path / "config"
    conf_dir.mkdir()
    (conf_dir / "llmwiki-launcher.conf").write_text('LAN_HOST="10.0.0.1"\n')
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path / "llmwiki")
    app, api, cors = cli._resolve_network("192.168.1.99", "1503", "1504")
    assert "192.168.1.99" in app
    assert "192.168.1.99" in api


def test_resolve_network_reads_lan_host_from_conf(monkeypatch, tmp_path):
    conf_dir = tmp_path / "config"
    conf_dir.mkdir()
    (conf_dir / "llmwiki-launcher.conf").write_text('LAN_HOST="10.0.0.5"\n')
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path / "llmwiki")
    app, api, cors = cli._resolve_network(None, "1503", "1504")
    assert "10.0.0.5" in app
    assert "10.0.0.5" in api


def test_resolve_network_explicit_urls_override_lan_host(monkeypatch, tmp_path):
    conf_dir = tmp_path / "config"
    conf_dir.mkdir()
    (conf_dir / "llmwiki-launcher.conf").write_text(
        'LAN_HOST="10.0.0.5"\n'
        'APP_URL="http://miwiki.local:1504"\n'
        'NEXT_PUBLIC_API_URL="http://miwiki.local:1503"\n'
    )
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path / "llmwiki")
    app, api, cors = cli._resolve_network(None, "1503", "1504")
    assert app == "http://miwiki.local:1504"
    assert api == "http://miwiki.local:1503"


def test_resolve_network_cors_origin_overrides_app_url(monkeypatch, tmp_path):
    conf_dir = tmp_path / "config"
    conf_dir.mkdir()
    (conf_dir / "llmwiki-launcher.conf").write_text(
        'LAN_HOST="10.0.0.5"\n'
        'CORS_ORIGIN="http://proxy.local:443"\n'
    )
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path / "llmwiki")
    app, api, cors = cli._resolve_network(None, "1503", "1504")
    assert cors == "http://proxy.local:443"
