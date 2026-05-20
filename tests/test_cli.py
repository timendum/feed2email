from pathlib import Path

from click.testing import CliRunner
import pytest

from feed2email.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


class TestCliGroup:
    def test_config_command_listed(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert "config" in result.output

    def test_db_option_uses_custom_path(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "config"])
        assert result.exit_code == 0
        assert Path(db_path).exists()

    def test_db_env_var(self, runner, db_path):
        result = runner.invoke(cli, ["config"], env={"FEED2EMAIL_DB": db_path})
        assert result.exit_code == 0
        assert Path(db_path).exists()


class TestConfigCommand:
    def test_no_args_empty_config(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "config"])
        assert result.exit_code == 0

    def test_set_value(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "config", "smtp.host", "mail.example.com"])
        assert result.exit_code == 0
        assert "smtp.host" in result.output
        assert "mail.example.com" in result.output

    def test_set_overwrites_existing(self, runner, db_path):
        runner.invoke(cli, ["--db", db_path, "config", "smtp.host", "old.example.com"])
        runner.invoke(cli, ["--db", db_path, "config", "smtp.host", "new.example.com"])
        result = runner.invoke(cli, ["--db", db_path, "config", "smtp.host"])
        assert result.exit_code == 0
        assert "new.example.com" in result.output

    def test_invalid_key_error(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "config", "invalid.key"])
        assert result.exit_code != 0
        assert "invalid.key" in result.output

    def test_invalid_key_error_set(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "config", "invalid.key", "val"])
        assert result.exit_code != 0

    def test_invalid_port_error(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "config", "smtp.port", "abc"])
        assert result.exit_code != 0

    def test_invalid_encryption_error(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "config", "smtp.encryption", "tls"])
        assert result.exit_code != 0

    def test_invalid_email_error(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "config", "smtp.from", "bad-email"])
        assert result.exit_code != 0

    def test_invalid_default_recipient_error(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "config", "default-recipient", "notanemail"])
        assert result.exit_code != 0

    def test_user_agent_empty_rejected(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "config", "user-agent", ""])
        assert result.exit_code != 0

    def test_no_args_lists_all(self, runner, db_path):
        values = {
            "smtp.host": "mail.example.com",
            "smtp.port": "587",
            "default-recipient": "user@example.com",
            "smtp.encryption": "ssl",
            "user-agent": "my-custom-agent",
        }
        for k, v in values.items():
            runner.invoke(cli, ["--db", db_path, "config", k, v])
            runner.invoke(cli, ["--db", db_path, "config", k, v])
        result = runner.invoke(cli, ["--db", db_path, "config"])
        assert result.exit_code == 0
        for k, v in values.items():
            assert k in result.output
            assert v in result.output
