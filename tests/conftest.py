import os
import sys

os.environ["DATABASE_URL"] = (
    "postgresql://postgres:postgres@localhost:5434/supavault_test"
)
os.environ["AWS_ACCESS_KEY_ID"] = ""
os.environ["AWS_SECRET_ACCESS_KEY"] = ""
os.environ["S3_BUCKET"] = ""
os.environ["LOGFIRE_TOKEN"] = ""
os.environ["SENTRY_DSN"] = ""
os.environ["APP_URL"] = "http://localhost:3000"
os.environ["GLOBAL_MAX_USERS"] = "1000"
os.environ["MODE"] = "hosted"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import pytest  # noqa: E402

# Capture the API's `config` module now, before any test imports the MCP package.
# The MCP package (mcp/) ships its own bare `config` module; importing it (e.g.
# via local_server or tools.helpers) replaces `config` in sys.modules with the
# MCP one, whose Settings lacks API-only fields such as USAGE_LOG_FILE. That
# shadow leaks across tests and breaks any later test that re-imports an API
# service. Restoring it after every test keeps the API config authoritative.
import config as _api_config  # noqa: E402


@pytest.fixture(autouse=True)
def _keep_api_config_authoritative():
    yield
    sys.modules["config"] = _api_config
