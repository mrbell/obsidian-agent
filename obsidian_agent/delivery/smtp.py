from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

from obsidian_agent.config import SmtpConfig
from obsidian_agent.delivery.base import DeliveryError

log = logging.getLogger(__name__)


class SmtpDelivery:
    """Sends email via SMTP with STARTTLS.

    Reads the SMTP password from the environment variable named in cfg.password_env
    at construction time. Raises DeliveryError immediately if the variable is unset.
    """

    def __init__(self, cfg: SmtpConfig) -> None:
        password = os.environ.get(cfg.password_env)
        if not password:
            raise DeliveryError(
                f"SMTP password env var '{cfg.password_env}' is not set"
            )
        self._cfg = cfg
        self._password = password

    def send(self, subject: str, body: str) -> None:
        """Send a plain-text email. Raises DeliveryError on any SMTP failure."""
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self._cfg.from_address
        msg["To"] = self._cfg.to_address

        try:
            with smtplib.SMTP(self._cfg.smtp_host, self._cfg.smtp_port) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(self._cfg.username, self._password)
                smtp.sendmail(
                    self._cfg.from_address,
                    [self._cfg.to_address],
                    msg.as_string(),
                )
        except smtplib.SMTPException as exc:
            log.error("SMTP delivery failed: %s", exc, exc_info=True)
            raise DeliveryError(f"SMTP delivery failed: {exc}") from exc
