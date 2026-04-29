import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mcp"))

from local_server import _parse_args


def test_default_transport_is_stdio(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["local_server", "."])
    args = _parse_args()
    assert args.transport == "stdio"


def test_streamable_http_transport(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["local_server", ".", "--transport", "streamable-http"])
    args = _parse_args()
    assert args.transport == "streamable-http"


def test_default_port(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["local_server", "."])
    args = _parse_args()
    assert args.port == 8765


def test_custom_port(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["local_server", ".", "--port", "9000"])
    args = _parse_args()
    assert args.port == 9000


def test_default_host(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["local_server", "."])
    args = _parse_args()
    assert args.host == "0.0.0.0"
