"""Envío de email vía SMTP (stdlib smtplib), ejecutado en hilo aparte."""

import asyncio
import smtplib
from email.message import EmailMessage


def _send_sync(
    host: str,
    port: int,
    username: str,
    password: str,
    from_address: str,
    use_tls: bool,
    to: str,
    subject: str,
    body: str,
) -> None:
    msg = EmailMessage()
    msg["From"] = from_address
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20) as server:
            if username:
                server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if use_tls:
                server.starttls()
            if username:
                server.login(username, password)
            server.send_message(msg)


async def send_email(cfg: dict, to: str, subject: str, body: str) -> None:
    """Envía un email. `cfg` con host/port/username/password/from_address/use_tls."""
    await asyncio.to_thread(
        _send_sync,
        cfg["host"],
        int(cfg["port"]),
        cfg.get("username", ""),
        cfg.get("password", ""),
        cfg["from_address"],
        bool(cfg.get("use_tls", True)),
        to,
        subject,
        body,
    )
