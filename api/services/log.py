"""Fire-and-forget usage logging.

Writes to:
  1. The `usage_logs` DB table (for queryable admin screen).
  2. A JSONL file at `settings.USAGE_LOG_FILE` (durable audit trail across DB resets).

Never raises — all failures are logged and swallowed.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

_log_file: Path | None = Path(settings.USAGE_LOG_FILE) if settings.USAGE_LOG_FILE else None


def _write_to_file(entry: dict) -> None:
    if _log_file is None:
        return
    try:
        _log_file.parent.mkdir(parents=True, exist_ok=True)
        with _log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        logger.warning("log_action: failed writing to file %s", _log_file, exc_info=True)


async def log_action(
    pool,
    *,
    user_id: str | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    kb_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Write a usage event to DB and optionally to the audit file."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "kb_id": kb_id,
        "metadata": metadata,
        "ip_address": ip_address,
    }
    # File write (non-blocking via executor)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _write_to_file, entry)
    # DB write
    try:
        uid = uuid.UUID(user_id) if user_id else None
        await pool.execute(
            "INSERT INTO usage_logs "
            "(user_id, action, resource_type, resource_id, kb_id, metadata, ip_address) "
            "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)",
            uid, action, resource_type, resource_id, kb_id,
            json.dumps(metadata) if metadata else None,
            ip_address,
        )
    except Exception:
        logger.warning("log_action: DB write failed for action=%s", action, exc_info=True)


def log_action_bg(pool, **kwargs) -> None:
    """Schedule log_action as a fire-and-forget background task."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("log_action_bg: no running event loop, skipping log")
        return
    loop.create_task(log_action(pool, **kwargs))
