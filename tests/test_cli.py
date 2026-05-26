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


def _setup_required_config(runner, db_path):
    """Set all required configuration keys so operational commands pass the setup guard."""
    runner.invoke(cli, ["--db", db_path, "config", "smtp.host", "mail.example.com"])
    runner.invoke(cli, ["--db", db_path, "config", "smtp.port", "587"])
    runner.invoke(cli, ["--db", db_path, "config", "smtp.from", "sender@example.com"])
    runner.invoke(cli, ["--db", db_path, "config", "smtp.encryption", "starttls"])
    runner.invoke(cli, ["--db", db_path, "config", "default-recipient", "user@example.com"])


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


class TestAddCommand:
    def _setup_default_recipient(self, runner, db_path):
        _setup_required_config(runner, db_path)

    def test_add_feed_with_default_recipient(self, runner, db_path):
        self._setup_default_recipient(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "add", "https://example.com/feed.xml"])
        assert result.exit_code == 0

    def test_add_feed_with_explicit_recipient(self, runner, db_path):
        self._setup_default_recipient(runner, db_path)
        result = runner.invoke(
            cli,
            [
                "--db",
                db_path,
                "add",
                "https://example.com/feed.xml",
                "--recipient",
                "other@example.com",
            ],
        )
        assert result.exit_code == 0

    def test_add_feed_no_default_recipient_no_explicit_errors(self, runner, db_path):
        # Set smtp config but not default-recipient
        runner.invoke(cli, ["--db", db_path, "config", "smtp.host", "mail.example.com"])
        runner.invoke(cli, ["--db", db_path, "config", "smtp.port", "587"])
        runner.invoke(cli, ["--db", db_path, "config", "smtp.from", "sender@example.com"])
        runner.invoke(cli, ["--db", db_path, "config", "smtp.encryption", "starttls"])
        runner.invoke(cli, ["--db", db_path, "config", "smtp.encryption", "starttls"])
        result = runner.invoke(cli, ["--db", db_path, "add", "https://example.com/feed.xml"])
        assert result.exit_code != 0

    def test_add_duplicate_feed_errors(self, runner, db_path):
        self._setup_default_recipient(runner, db_path)
        runner.invoke(cli, ["--db", db_path, "add", "https://example.com/feed.xml"])
        result = runner.invoke(cli, ["--db", db_path, "add", "https://example.com/feed.xml"])
        assert result.exit_code != 0

    def test_add_invalid_url_errors(self, runner, db_path):
        self._setup_default_recipient(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "add", "ftp://example.com/feed.xml"])
        assert result.exit_code != 0

    def test_add_invalid_recipient_errors(self, runner, db_path):
        self._setup_default_recipient(runner, db_path)
        result = runner.invoke(
            cli,
            ["--db", db_path, "add", "https://example.com/feed.xml", "--recipient", "not-an-email"],
        )
        assert result.exit_code != 0

    def test_add_with_options(self, runner, db_path):
        self._setup_default_recipient(runner, db_path)
        result = runner.invoke(
            cli,
            [
                "--db",
                db_path,
                "add",
                "https://example.com/feed.xml",
                "--dedup-key",
                "link",
                "--format",
                "html",
                "--item-date",
            ],
        )
        assert result.exit_code == 0

    def test_add_blocked_by_setup_guard(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "add", "https://example.com/feed.xml"])
        assert result.exit_code != 0
        assert "Setup is incomplete" in result.output
        assert "feed2email init" in result.output


class TestRemoveCommand:
    def _add_feed(self, runner, db_path, url="https://example.com/feed.xml"):
        _setup_required_config(runner, db_path)
        runner.invoke(cli, ["--db", db_path, "add", url])

    def test_remove_by_url(self, runner, db_path):
        self._add_feed(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "remove", "https://example.com/feed.xml"])
        assert result.exit_code == 0

    def test_remove_by_id(self, runner, db_path):
        self._add_feed(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "remove", "1"])
        assert result.exit_code == 0

    def test_remove_nonexistent_errors(self, runner, db_path):
        _setup_required_config(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "remove", "https://nonexistent.com/feed.xml"])
        assert result.exit_code != 0


class TestListCommand:
    def _add_feed(self, runner, db_path, url="https://example.com/feed.xml"):
        _setup_required_config(runner, db_path)
        runner.invoke(cli, ["--db", db_path, "add", url])

    def test_list_no_feeds(self, runner, db_path):
        _setup_required_config(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "list"])
        assert result.exit_code == 0
        assert "No feeds configured." in result.output

    def test_list_shows_feed(self, runner, db_path):
        self._add_feed(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "list"])
        assert result.exit_code == 0
        assert "https://example.com/feed.xml" in result.output
        assert "dedup_key=id" in result.output
        assert "active" in result.output

    def test_list_shows_paused_status(self, runner, db_path):
        self._add_feed(runner, db_path)
        runner.invoke(cli, ["--db", db_path, "pause", "1"])
        result = runner.invoke(cli, ["--db", db_path, "list"])
        assert "paused" in result.output

    def test_list_shows_recipient(self, runner, db_path):
        _setup_required_config(runner, db_path)
        runner.invoke(
            cli,
            [
                "--db",
                db_path,
                "add",
                "https://example.com/feed.xml",
                "--recipient",
                "other@example.com",
            ],
        )
        result = runner.invoke(cli, ["--db", db_path, "list"])
        assert result.exit_code == 0
        assert "other@example.com" in result.output


class TestPauseCommand:
    def _add_feed(self, runner, db_path, url="https://example.com/feed.xml"):
        _setup_required_config(runner, db_path)
        runner.invoke(cli, ["--db", db_path, "add", url])

    def test_pause_feed(self, runner, db_path):
        self._add_feed(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "pause", "1"])
        assert result.exit_code == 0

    def test_pause_already_paused(self, runner, db_path):
        self._add_feed(runner, db_path)
        runner.invoke(cli, ["--db", db_path, "pause", "1"])
        result = runner.invoke(cli, ["--db", db_path, "pause", "1"])
        assert result.exit_code == 0

    def test_pause_nonexistent_errors(self, runner, db_path):
        _setup_required_config(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "pause", "999"])
        assert result.exit_code != 0


class TestUnpauseCommand:
    def _add_feed(self, runner, db_path, url="https://example.com/feed.xml"):
        _setup_required_config(runner, db_path)
        runner.invoke(cli, ["--db", db_path, "add", url])

    def test_unpause_paused_feed(self, runner, db_path):
        self._add_feed(runner, db_path)
        runner.invoke(cli, ["--db", db_path, "pause", "1"])
        result = runner.invoke(cli, ["--db", db_path, "unpause", "1"])
        assert result.exit_code == 0

    def test_unpause_already_active(self, runner, db_path):
        self._add_feed(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "unpause", "1"])
        assert result.exit_code == 0

    def test_unpause_nonexistent_errors(self, runner, db_path):
        _setup_required_config(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "unpause", "999"])
        assert result.exit_code != 0


class TestRunCommand:
    def _add_feed(self, runner, db_path, url="https://example.com/feed.xml"):
        _setup_required_config(runner, db_path)
        runner.invoke(cli, ["--db", db_path, "add", url])

    def test_run_no_feeds_exits_0(self, runner, db_path):
        _setup_required_config(runner, db_path)
        result = runner.invoke(cli, ["--db", db_path, "run"])
        assert result.exit_code == 0

    def test_run_blocked_by_setup_guard(self, runner, db_path):
        result = runner.invoke(cli, ["--db", db_path, "run"])
        assert result.exit_code != 0
