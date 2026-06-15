"""Email sender using smtplib with support for none/starttls/ssl encryption."""

import smtplib
from email.mime.text import MIMEText
from email.utils import format_datetime
from typing import TYPE_CHECKING

from feed2email.models import EmailMessage, SendResult, SmtpConfig

if TYPE_CHECKING:
    from feed2email.db import Database


class EmailSender:
    """Sends email messages via SMTP."""

    def __init__(self, config: SmtpConfig) -> None:
        self.config = config

    @classmethod
    def from_db(cls, db: "Database") -> "EmailSender":
        """Raises:
        RuntimeError: If required SMTP configuration keys are missing.
        """
        config = db.get_all_config()
        required = ("smtp.host", "smtp.port", "smtp.from", "smtp.encryption")
        missing = [k for k in required if k not in config]
        if missing:
            raise RuntimeError(f"SMTP configuration incomplete. Missing: {', '.join(missing)}")

        smtp_config = SmtpConfig(
            host=config["smtp.host"],
            port=int(config["smtp.port"]),
            from_address=config["smtp.from"],
            encryption=config["smtp.encryption"],
            username=config.get("smtp.user"),
            password=config.get("smtp.password"),
        )
        return cls(smtp_config)

    def send(self, message: EmailMessage) -> SendResult:
        """Send an email message via SMTP.

        Login is only performed when username and password are both configured.

        Returns SendResult(success=True) on success, or
        SendResult(success=False, error=str(e)) on any exception.
        """
        try:
            msg = MIMEText(message.body, _subtype=self._subtype(message.content_type))
            msg["From"] = self.config.from_address
            msg["To"] = message.recipient
            msg["Subject"] = message.subject
            msg["Date"] = format_datetime(message.date)

            if message.user_agent:
                msg["User-Agent"] = message.user_agent
            if message.feed_id:
                msg["List-ID"] = message.feed_id
            msg["List-Post"] = "NO"  # From rfc2369 3.4
            if message.feed_id:
                msg["X-Feed-URL"] = message.feed_id
            if message.item_url:
                msg["X-Feed-Item-URL"] = message.item_url
            if message.item_id:
                msg["X-Feed-Item-ID"] = message.item_id

            connection = self._connect()
            try:
                if self.config.username and self.config.password:
                    connection.login(self.config.username, self.config.password)
                connection.sendmail(self.config.from_address, message.recipient, msg.as_string())
            finally:
                connection.quit()

            return SendResult(success=True)
        except (RuntimeError, OSError) as e:
            return SendResult(success=False, error=str(e))

    def _connect(self) -> smtplib.SMTP | smtplib.SMTP_SSL:
        """Create and return an SMTP connection based on encryption setting."""
        if self.config.encryption == "ssl":
            return smtplib.SMTP_SSL(self.config.host, self.config.port)
        else:
            conn = smtplib.SMTP(self.config.host, self.config.port)
            if self.config.encryption == "starttls":
                conn.starttls()
            return conn

    @staticmethod
    def _subtype(content_type: str) -> str:
        """Extract MIME subtype from content_type string."""
        if content_type == "text/html":
            return "html"
        return "plain"
