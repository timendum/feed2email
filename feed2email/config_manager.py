from feed2email.db import Database
from feed2email.models import REQUIRED_KEYS, SmtpConfig, validate_email, validate_port

_REQUIRED_SMTP_KEYS = ["smtp.host", "smtp.port", "smtp.from", "smtp.encryption"]


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

    def unset(self, key: str) -> tuple[bool, str | None]:
        """Remove a config value.

        Returns (True, None) on success, (False, error_message) on failure.
        """
        if key in REQUIRED_KEYS:
            return False, f"Cannot unset required key '{key}'"
        if self.db.delete_config(key):
            return True, None
        return True, None  # key was not set, still a valid operation

    def list_all(self) -> dict[str, str]:
        """Return all configured key-value pairs."""
        return self.db.get_all_config()

    def get_smtp(self) -> SmtpConfig | None:
        """Return valid SmtpConfig or None."""
        config = self.db.get_all_config()
        for key in _REQUIRED_SMTP_KEYS:
            if key not in config:
                return None

        return SmtpConfig(
            host=config["smtp.host"],
            port=int(config["smtp.port"]),
            from_address=config["smtp.from"],
            encryption=config["smtp.encryption"],
            username=config.get("smtp.user"),
            password=config.get("smtp.password"),
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

        elif key == "smtp.from":
            if not validate_email(value):
                return False, "Invalid email address format"

        elif key == "default-recipient":
            if not validate_email(value):
                return False, "Invalid email address format"

        elif key == "user-agent":
            if not value.strip():
                return False, "User-Agent cannot be empty"

        return True, None

    def get_missing_smtp_keys(self) -> list[str]:
        """Return list of required but not set SMTP keys."""
        config = self.db.get_all_config()
        return [key for key in _REQUIRED_SMTP_KEYS if key not in config]

    def is_setup_complete(self) -> bool:
        """Return True only when all Required_Configuration keys have non-empty values."""
        config = self.db.get_all_config()
        return all(key in config and config[key].strip() for key in REQUIRED_KEYS)

    def get_missing_required_keys(self) -> list[str]:
        """Return the list of Required_Configuration keys that are missing or empty."""
        config = self.db.get_all_config()
        return [key for key in REQUIRED_KEYS if key not in config or not config[key].strip()]
