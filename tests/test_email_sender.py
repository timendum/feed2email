"""Unit tests for EmailSender class."""

import smtplib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from feed2email.mailer.email_sender import EmailSender
from feed2email.models import EmailMessage, SmtpConfig


@pytest.fixture
def smtp_config():
    return SmtpConfig(
        host="mail.example.com",
        port=587,
        from_address="sender@example.com",
        encryption="starttls",
        username="user@example.com",
        password="secret",
    )


@pytest.fixture
def smtp_config_no_auth():
    """SMTP config without username/password (relay server)."""
    return SmtpConfig(
        host="mail.example.com",
        port=25,
        from_address="sender@example.com",
        encryption="none",
        username=None,
        password=None,
    )


@pytest.fixture
def email_message():
    return EmailMessage(
        recipient="recipient@example.com",
        subject="Test Subject",
        body="Hello, world!",
        content_type="text/plain",
        date=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestEmailSenderSend:
    """Tests for EmailSender.send() method."""

    @patch("feed2email.mailer.email_sender.smtplib.SMTP")
    def test_starttls_connection_flow(self, mock_smtp_class, smtp_config, email_message):
        """STARTTLS: creates SMTP, calls starttls(), login, sendmail, quit."""
        smtp_config.encryption = "starttls"
        mock_conn = MagicMock()
        mock_smtp_class.return_value = mock_conn

        sender = EmailSender(smtp_config)
        result = sender.send(email_message)

        assert result.success is True
        assert result.error is None
        mock_smtp_class.assert_called_once_with("mail.example.com", 587)
        mock_conn.starttls.assert_called_once()
        mock_conn.login.assert_called_once_with("user@example.com", "secret")
        mock_conn.sendmail.assert_called_once()
        mock_conn.quit.assert_called_once()

    @patch("feed2email.mailer.email_sender.smtplib.SMTP_SSL")
    def test_ssl_connection_flow(self, mock_smtp_ssl_class, smtp_config, email_message):
        """SSL: creates SMTP_SSL, login, sendmail, quit (no starttls)."""
        smtp_config.encryption = "ssl"
        smtp_config.port = 465
        mock_conn = MagicMock()
        mock_smtp_ssl_class.return_value = mock_conn

        sender = EmailSender(smtp_config)
        result = sender.send(email_message)

        assert result.success is True
        assert result.error is None
        mock_smtp_ssl_class.assert_called_once_with("mail.example.com", 465)
        mock_conn.login.assert_called_once_with("user@example.com", "secret")
        mock_conn.sendmail.assert_called_once()
        mock_conn.quit.assert_called_once()

    @patch("feed2email.mailer.email_sender.smtplib.SMTP")
    def test_none_encryption_flow(self, mock_smtp_class, smtp_config, email_message):
        """No encryption: creates SMTP without starttls."""
        smtp_config.encryption = "none"
        smtp_config.port = 25
        mock_conn = MagicMock()
        mock_smtp_class.return_value = mock_conn

        sender = EmailSender(smtp_config)
        result = sender.send(email_message)

        assert result.success is True
        assert result.error is None
        mock_smtp_class.assert_called_once_with("mail.example.com", 25)
        mock_conn.starttls.assert_not_called()
        mock_conn.login.assert_called_once_with("user@example.com", "secret")
        mock_conn.sendmail.assert_called_once()
        mock_conn.quit.assert_called_once()

    @patch("feed2email.mailer.email_sender.smtplib.SMTP")
    def test_no_auth_skips_login(self, mock_smtp_class, smtp_config_no_auth, email_message):
        """When username/password are None, login is not called."""
        mock_conn = MagicMock()
        mock_smtp_class.return_value = mock_conn

        sender = EmailSender(smtp_config_no_auth)
        result = sender.send(email_message)

        assert result.success is True
        assert result.error is None
        mock_smtp_class.assert_called_once_with("mail.example.com", 25)
        mock_conn.login.assert_not_called()
        mock_conn.sendmail.assert_called_once()
        mock_conn.quit.assert_called_once()

    @patch("feed2email.mailer.email_sender.smtplib.SMTP")
    def test_no_auth_uses_from_address_in_sendmail(
        self, mock_smtp_class, smtp_config_no_auth, email_message
    ):
        """Without auth, from_address is used as envelope sender."""
        mock_conn = MagicMock()
        mock_smtp_class.return_value = mock_conn

        sender = EmailSender(smtp_config_no_auth)
        sender.send(email_message)

        call_args = mock_conn.sendmail.call_args
        assert call_args[0][0] == "sender@example.com"
        assert call_args[0][1] == "recipient@example.com"

    @patch("feed2email.mailer.email_sender.smtplib.SMTP")
    def test_from_address_used_in_header(self, mock_smtp_class, smtp_config, email_message):
        """From header uses from_address, not username."""
        mock_conn = MagicMock()
        mock_smtp_class.return_value = mock_conn

        sender = EmailSender(smtp_config)
        sender.send(email_message)

        call_args = mock_conn.sendmail.call_args
        raw_message = call_args[0][2]
        assert "From: sender@example.com" in raw_message

    @patch("feed2email.mailer.email_sender.smtplib.SMTP")
    def test_from_address_used_as_envelope_sender(
        self, mock_smtp_class, smtp_config, email_message
    ):
        """from_address is used as envelope sender in sendmail call."""
        mock_conn = MagicMock()
        mock_smtp_class.return_value = mock_conn

        sender = EmailSender(smtp_config)
        sender.send(email_message)

        call_args = mock_conn.sendmail.call_args
        assert call_args[0][0] == "sender@example.com"

    @patch("feed2email.mailer.email_sender.smtplib.SMTP")
    def test_connection_failure_returns_error(self, mock_smtp_class, smtp_config, email_message):
        """Connection failure returns SendResult with success=False."""
        mock_smtp_class.side_effect = ConnectionRefusedError("Connection refused")

        sender = EmailSender(smtp_config)
        result = sender.send(email_message)

        assert result.success is False
        assert "Connection refused" in result.error

    @patch("feed2email.mailer.email_sender.smtplib.SMTP")
    def test_login_failure_returns_error(self, mock_smtp_class, smtp_config, email_message):
        """Login failure returns SendResult with success=False."""
        mock_conn = MagicMock()
        mock_smtp_class.return_value = mock_conn
        mock_conn.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")

        sender = EmailSender(smtp_config)
        result = sender.send(email_message)

        assert result.success is False
        assert result.error is not None
        mock_conn.quit.assert_called_once()

    @patch("feed2email.mailer.email_sender.smtplib.SMTP")
    def test_sendmail_rejection_returns_error(self, mock_smtp_class, smtp_config, email_message):
        """Message rejection returns SendResult with success=False."""
        mock_conn = MagicMock()
        mock_smtp_class.return_value = mock_conn
        mock_conn.sendmail.side_effect = smtplib.SMTPRecipientsRefused(
            {"recipient@example.com": (550, b"User unknown")}
        )

        sender = EmailSender(smtp_config)
        result = sender.send(email_message)

        assert result.success is False
        assert result.error is not None
        mock_conn.quit.assert_called_once()

    @patch("feed2email.mailer.email_sender.smtplib.SMTP")
    def test_email_headers_are_set_correctly(self, mock_smtp_class, smtp_config, email_message):
        """Email contains proper From, To, Subject, Date, Content-Type headers."""
        mock_conn = MagicMock()
        mock_smtp_class.return_value = mock_conn

        sender = EmailSender(smtp_config)
        sender.send(email_message)

        # Get the raw message string passed to sendmail
        call_args = mock_conn.sendmail.call_args
        raw_message = call_args[0][2]

        assert "From: sender@example.com" in raw_message
        assert "To: recipient@example.com" in raw_message
        assert "Subject: Test Subject" in raw_message
        assert "Date:" in raw_message
        assert "Content-Type: text/plain" in raw_message

    @patch("feed2email.mailer.email_sender.smtplib.SMTP")
    def test_html_content_type(self, mock_smtp_class, smtp_config, email_message):
        """HTML content type sets correct MIME subtype."""
        email_message.content_type = "text/html"
        mock_conn = MagicMock()
        mock_smtp_class.return_value = mock_conn

        sender = EmailSender(smtp_config)
        sender.send(email_message)

        call_args = mock_conn.sendmail.call_args
        raw_message = call_args[0][2]

        assert "Content-Type: text/html" in raw_message
