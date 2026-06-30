"""Digest periódico por email de notificaciones de wikis (modo hosted)."""

import logging

from infra.email import send_email

logger = logging.getLogger(__name__)

_PENDING_QUERY = (
    "SELECT n.id, n.recipient_id, u.email AS recipient_email, "
    "kb.name AS kb_name, kb.slug AS kb_slug, n.unread_count "
    "FROM kb_notifications n "
    "JOIN users u ON u.id = n.recipient_id "
    "JOIN knowledge_bases kb ON kb.id = n.kb_id "
    "WHERE n.read_at IS NULL AND u.is_active = true "
    "AND (n.emailed_at IS NULL OR n.last_activity_at > n.emailed_at) "
    "ORDER BY n.recipient_id, n.last_activity_at DESC"
)


async def run_digest_once(pool, app_url: str) -> int:
    """Envía un digest por destinatario con actividad nueva. Devuelve el intervalo (min)."""
    app_url = app_url.rstrip("/")
    cfg = await pool.fetchrow("SELECT * FROM smtp_settings WHERE id = 1")
    interval = cfg["digest_interval_minutes"] if cfg else 60
    if not cfg or not cfg["enabled"] or not cfg["host"] or not cfg["from_address"]:
        return interval

    rows = await pool.fetch(_PENDING_QUERY)
    if not rows:
        return interval

    cfg_d = dict(cfg)
    by_recipient: dict[str, list] = {}
    for r in rows:
        by_recipient.setdefault(r["recipient_email"], []).append(r)

    sent_ids: list = []
    for email, items in by_recipient.items():
        lines = ["Hay novedades en wikis que compartes:", ""]
        for it in items:
            lines.append(
                f"- {it['kb_name']}: {it['unread_count']} cambio(s) "
                f"— {app_url}/wikis/{it['kb_slug']}"
            )
        body = "\n".join(lines)
        try:
            await send_email(cfg_d, email, "Novedades en tus wikis", body)
            sent_ids.extend(it["id"] for it in items)
        except Exception:
            logger.warning("digest email failed for %s", email, exc_info=True)

    if sent_ids:
        await pool.execute(
            "UPDATE kb_notifications SET emailed_at = now() WHERE id = ANY($1)",
            sent_ids,
        )
    return interval
