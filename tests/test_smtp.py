import smtplib
from unittest.mock import MagicMock, patch

import pytest

from obsidian_agent.config import SmtpConfig
from obsidian_agent.delivery.base import DeliveryError
from obsidian_agent.delivery.smtp import SmtpDelivery

_CFG = SmtpConfig(
    smtp_host="smtp.example.com",
    smtp_port=587,
    username="sender@example.com",
    password_env="TEST_SMTP_PASSWORD",
    from_address="sender@example.com",
    to_address="recipient@example.com",
)

_PATCH = "obsidian_agent.delivery.smtp.smtplib.SMTP"


def _make_delivery(monkeypatch) -> SmtpDelivery:
    monkeypatch.setenv("TEST_SMTP_PASSWORD", "test-secret")
    return SmtpDelivery(_CFG)


def _mock_smtp():
    """Return (MockSMTP class, mock connection instance) for use in patch()."""
    mock_conn = MagicMock()
    mock_cls = MagicMock()
    mock_cls.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return mock_cls, mock_conn


class TestSmtpDeliveryInit:
    def test_missing_env_var_raises_delivery_error(self, monkeypatch) -> None:
        monkeypatch.delenv("TEST_SMTP_PASSWORD", raising=False)
        with pytest.raises(DeliveryError, match="TEST_SMTP_PASSWORD"):
            SmtpDelivery(_CFG)

    def test_missing_env_var_raises_at_init_not_send(self, monkeypatch) -> None:
        monkeypatch.delenv("TEST_SMTP_PASSWORD", raising=False)
        with pytest.raises(DeliveryError):
            SmtpDelivery(_CFG)
        # If we reach here the error was raised at init, not deferred

    def test_present_env_var_succeeds(self, monkeypatch) -> None:
        monkeypatch.setenv("TEST_SMTP_PASSWORD", "secret")
        delivery = SmtpDelivery(_CFG)
        assert delivery is not None


class TestSmtpDeliverySend:
    def test_send_uses_starttls(self, monkeypatch) -> None:
        mock_cls, mock_conn = _mock_smtp()
        with patch(_PATCH, mock_cls):
            _make_delivery(monkeypatch).send("Subject", "Body")
        mock_conn.starttls.assert_called_once()

    def test_send_logs_in_with_password(self, monkeypatch) -> None:
        mock_cls, mock_conn = _mock_smtp()
        with patch(_PATCH, mock_cls):
            _make_delivery(monkeypatch).send("Subject", "Body")
        mock_conn.login.assert_called_once_with("sender@example.com", "test-secret")

    def test_send_calls_sendmail(self, monkeypatch) -> None:
        mock_cls, mock_conn = _mock_smtp()
        with patch(_PATCH, mock_cls):
            _make_delivery(monkeypatch).send("Hello", "World")
        mock_conn.sendmail.assert_called_once()
        args = mock_conn.sendmail.call_args
        assert args[0][0] == "sender@example.com"
        assert "recipient@example.com" in args[0][1]

    def test_send_connects_to_configured_host(self, monkeypatch) -> None:
        mock_cls, _ = _mock_smtp()
        with patch(_PATCH, mock_cls):
            _make_delivery(monkeypatch).send("Subject", "Body")
        mock_cls.assert_called_once_with("smtp.example.com", 587)

    def test_smtp_exception_raises_delivery_error(self, monkeypatch) -> None:
        mock_cls = MagicMock()
        mock_cls.return_value.__enter__.side_effect = smtplib.SMTPException("conn failed")
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        with patch(_PATCH, mock_cls):
            delivery = _make_delivery(monkeypatch)
            with pytest.raises(DeliveryError, match="SMTP delivery failed"):
                delivery.send("Subject", "Body")

    def test_smtp_auth_error_raises_delivery_error(self, monkeypatch) -> None:
        mock_cls, mock_conn = _mock_smtp()
        mock_conn.login.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")
        with patch(_PATCH, mock_cls):
            delivery = _make_delivery(monkeypatch)
            with pytest.raises(DeliveryError):
                delivery.send("Subject", "Body")
