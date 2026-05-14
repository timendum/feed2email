from feed2email.db.database import Database
from feed2email.models import REQUIRED_SMTP_KEYS, SmtpConfig
from feed2email.validation import validate_email, validate_port


class ConfigManager:
    """Manages application configuration stored in the database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, key: str) -> str | None:
        """Get a single config value by key."""
        return self.db.get_config(key)

    def set(self, key: str, value: str) -> tuple[bool, str | None]:
        """Set a single validated config value."""
        valid, error = self.validate_value(key, value)
        if valid:
            self.db.set_config(key, value)
            return True, None
        return valid, error

    def list_all(self) -> dict[str, str]:
        """Return all configured key-value pairs."""
        return self.db.get_all_config()

    def get_smtp(self) -> SmtpConfig | None:
        """Return valid SmtpConfig or None."""
        config = self.db.get_all_config()
        for key in REQUIRED_SMTP_KEYS:
            if key not in config:
                return None

        return SmtpConfig(
            host=config["smtp.host"],
            port=int(config["smtp.port"]),
            username=config["smtp.user"],
            password=config["smtp.password"],
            encryption=config["smtp.encryption"],
        )

    def get_default_recipient(self) -> str | None:
        """Return the default recipient email, or None if not configured."""
        return self.db.get_config("default-recipient")

    def validate_value(self, key: str, value: str) -> tuple[bool, str | None]:
        """Validate value for the given key. Returns (is_valid, error_message)."""
        if key == "smtp.port":
            try:
                port = int(value)
            except ValueError:
                return False, "Port must be an integer between 1 and 65535"
            if not validate_port(port):
                return False, "Port must be an integer between 1 and 65535"

        elif key == "smtp.encryption":
            valid_values = ("none", "starttls", "ssl")
            if value not in valid_values:
                return False, f"Encryption must be one of: {', '.join(valid_values)}"

        elif key == "default-recipient":
            if not validate_email(value):
                return False, "Invalid email address format"

        return True, None

    def get_missing_smtp_keys(self) -> list[str]:
        """Return list of required but not set SMTP keys."""
        config = self.db.get_all_config()
        return [key for key in REQUIRED_SMTP_KEYS if key not in config]
