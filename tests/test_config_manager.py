import pytest

from feed2email.config_manager import ConfigManager
from feed2email.db import Database


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

    def test_user_agent_valid(self, config_mgr: ConfigManager) -> None:
        assert config_mgr.validate_value("user-agent", "MyBot/1.0") == (True, None)
        assert config_mgr.validate_value("user-agent", "feed2email") == (True, None)

    def test_user_agent_empty_invalid(self, config_mgr: ConfigManager) -> None:
        is_valid, error = config_mgr.validate_value("user-agent", "")
        assert is_valid is False
        assert error is not None

        is_valid, error = config_mgr.validate_value("user-agent", "   ")
        assert is_valid is False
        assert error is not None

    def test_user_agent_stored_and_retrieved(self, config_mgr: ConfigManager) -> None:
        config_mgr.set("user-agent", "CustomAgent/2.0")
        assert config_mgr.get("user-agent") == "CustomAgent/2.0"


class TestTemplateConfig:
    def test_template_subject_valid(self, config_mgr: ConfigManager) -> None:
        assert config_mgr.validate_value("template.subject", "{{ title }}") == (True, None)
        assert config_mgr.validate_value("template.subject", "[{{ feed_title }}] {{ title }}") == (
            True,
            None,
        )

    def test_template_subject_invalid_syntax(self, config_mgr: ConfigManager) -> None:
        is_valid, error = config_mgr.validate_value("template.subject", "{{ title")
        assert is_valid is False
        assert error is not None
        assert "Jinja2" in error

    def test_template_body_valid(self, config_mgr: ConfigManager) -> None:
        assert config_mgr.validate_value(
            "template.body", "{{ title }}\n{{ link }}\n{{ body }}"
        ) == (True, None)

    def test_template_body_invalid_syntax(self, config_mgr: ConfigManager) -> None:
        is_valid, error = config_mgr.validate_value("template.body", "{% if %}")
        assert is_valid is False
        assert error is not None
        assert "Jinja2" in error

    def test_template_subject_stored_and_retrieved(self, config_mgr: ConfigManager) -> None:
        config_mgr.set("template.subject", "[{{ feed_title }}] {{ title }}")
        assert config_mgr.get("template.subject") == "[{{ feed_title }}] {{ title }}"

    def test_template_body_stored_and_retrieved(self, config_mgr: ConfigManager) -> None:
        tpl = "{{ title }}\n{{ body }}"
        config_mgr.set("template.body", tpl)
        assert config_mgr.get("template.body") == tpl
