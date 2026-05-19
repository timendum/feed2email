import pytest

from feed2email.core.config_manager import ConfigManager
from feed2email.db.database import Database
from feed2email.models import SmtpConfig


@pytest.fixture
def config_mgr(db: Database) -> ConfigManager:
    return ConfigManager(db)


class TestConfig:
    def test_returns_none_for_unset_key(self, config_mgr: ConfigManager) -> None:
        assert config_mgr.get("smtp.host") is None

    def test_returns_value_after_set(self, config_mgr: ConfigManager) -> None:
        config_mgr.set("smtp.host", "mail.example.com")
        assert config_mgr.get("smtp.host") == "mail.example.com"

    def test_stores_value(self, config_mgr: ConfigManager) -> None:
        config_mgr.set("smtp.host", "mail.example.com")
        assert config_mgr.get("smtp.host") == "mail.example.com"

    def test_overwrites_existing_value(self, config_mgr: ConfigManager) -> None:
        config_mgr.set("smtp.host", "old.example.com")
        config_mgr.set("smtp.host", "new.example.com")
        assert config_mgr.get("smtp.host") == "new.example.com"

    def test_empty_when_no_config(self, config_mgr: ConfigManager) -> None:
        assert config_mgr.list_all() == {}

    def test_returns_all_set_values(self, config_mgr: ConfigManager) -> None:
        config_mgr.set("smtp.host", "mail.example.com")
        config_mgr.set("smtp.port", "587")
        result = config_mgr.list_all()
        assert result == {"smtp.host": "mail.example.com", "smtp.port": "587"}

    def test_returns_none_when_incomplete(self, config_mgr: ConfigManager) -> None:
        config_mgr.set("smtp.host", "mail.example.com")
        assert config_mgr.get_smtp() is None

    def test_returns_smtp_config_when_complete_with_auth(self, config_mgr: ConfigManager) -> None:
        config_mgr.set("smtp.host", "mail.example.com")
        config_mgr.set("smtp.port", "587")
        config_mgr.set("smtp.from", "sender@example.com")
        config_mgr.set("smtp.user", "user@example.com")
        config_mgr.set("smtp.password", "secret")
        config_mgr.set("smtp.encryption", "starttls")

        smtp = config_mgr.get_smtp()
        assert smtp is not None
        assert smtp == SmtpConfig(
            host="mail.example.com",
            port=587,
            from_address="sender@example.com",
            encryption="starttls",
            username="user@example.com",
            password="secret",
        )

    def test_returns_smtp_config_without_auth(self, config_mgr: ConfigManager) -> None:
        """SMTP config is valid without username and password (relay server)."""
        config_mgr.set("smtp.host", "mail.example.com")
        config_mgr.set("smtp.port", "25")
        config_mgr.set("smtp.from", "sender@example.com")
        config_mgr.set("smtp.encryption", "none")

        smtp = config_mgr.get_smtp()
        assert smtp is not None
        assert smtp == SmtpConfig(
            host="mail.example.com",
            port=25,
            from_address="sender@example.com",
            encryption="none",
            username=None,
            password=None,
        )

    def test_returns_none_when_not_set(self, config_mgr: ConfigManager) -> None:
        assert config_mgr.get_default_recipient() is None

    def test_returns_value_when_set(self, config_mgr: ConfigManager) -> None:
        config_mgr.set("default-recipient", "user@example.com")
        assert config_mgr.get_default_recipient() == "user@example.com"


class TestSmtp:

    def test_smtp_port_valid(self, config_mgr: ConfigManager) -> None:
        assert config_mgr.validate_value("smtp.port", "587") == (True, None)
        assert config_mgr.validate_value("smtp.port", "1") == (True, None)
        assert config_mgr.validate_value("smtp.port", "65535") == (True, None)

    def test_smtp_port_invalid(self, config_mgr: ConfigManager) -> None:
        is_valid, error = config_mgr.validate_value("smtp.port", "0")
        assert is_valid is False
        assert error is not None

        is_valid, error = config_mgr.validate_value("smtp.port", "65536")
        assert is_valid is False
        assert error is not None

        is_valid, error = config_mgr.validate_value("smtp.port", "abc")
        assert is_valid is False
        assert error is not None

    def test_smtp_encryption_valid(self, config_mgr: ConfigManager) -> None:
        for val in ("none", "starttls", "ssl"):
            assert config_mgr.validate_value("smtp.encryption", val) == (True, None)

    def test_smtp_encryption_invalid(self, config_mgr: ConfigManager) -> None:
        is_valid, error = config_mgr.validate_value("smtp.encryption", "tls")
        assert is_valid is False
        assert error is not None

    def test_smtp_from_valid(self, config_mgr: ConfigManager) -> None:
        assert config_mgr.validate_value("smtp.from", "sender@example.com") == (True, None)

    def test_smtp_from_invalid(self, config_mgr: ConfigManager) -> None:
        is_valid, error = config_mgr.validate_value("smtp.from", "not-an-email")
        assert is_valid is False
        assert error is not None

    def test_default_recipient_valid(self, config_mgr: ConfigManager) -> None:
        assert config_mgr.validate_value("default-recipient", "user@example.com") == (True, None)

    def test_default_recipient_invalid(self, config_mgr: ConfigManager) -> None:
        is_valid, error = config_mgr.validate_value("default-recipient", "not-an-email")
        assert is_valid is False
        assert error is not None

    def test_other_keys_always_valid(self, config_mgr: ConfigManager) -> None:
        assert config_mgr.validate_value("smtp.host", "anything") == (True, None)
        assert config_mgr.validate_value("smtp.user", "user@mail.com") == (True, None)
        assert config_mgr.validate_value("smtp.password", "p@ss!") == (True, None)

    def test_all_missing_when_empty(self, config_mgr: ConfigManager) -> None:
        missing = config_mgr.get_missing_smtp_keys()
        assert set(missing) == {
            "smtp.host", "smtp.port", "smtp.from", "smtp.encryption",
        }

    def test_some_missing(self, config_mgr: ConfigManager) -> None:
        config_mgr.set("smtp.host", "mail.example.com")
        config_mgr.set("smtp.port", "587")
        missing = config_mgr.get_missing_smtp_keys()
        assert "smtp.host" not in missing
        assert "smtp.port" not in missing
        assert "smtp.from" in missing
        assert "smtp.encryption" in missing

    def test_none_missing_when_all_required_set(self, config_mgr: ConfigManager) -> None:
        config_mgr.set("smtp.host", "mail.example.com")
        config_mgr.set("smtp.port", "587")
        config_mgr.set("smtp.from", "sender@example.com")
        config_mgr.set("smtp.encryption", "starttls")
        assert config_mgr.get_missing_smtp_keys() == []

    def test_user_and_password_not_required(self, config_mgr: ConfigManager) -> None:
        """smtp.user and smtp.password are optional, not in missing keys."""
        config_mgr.set("smtp.host", "mail.example.com")
        config_mgr.set("smtp.port", "587")
        config_mgr.set("smtp.from", "sender@example.com")
        config_mgr.set("smtp.encryption", "starttls")
        missing = config_mgr.get_missing_smtp_keys()
        assert "smtp.user" not in missing
        assert "smtp.password" not in missing
