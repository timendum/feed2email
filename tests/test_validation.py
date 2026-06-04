"""Unit tests for the validation module."""

from feed2email.models import validate_email, validate_port, validate_url


class TestValidateUrl:
    """Tests for validate_url()."""

    def test_valid_http_url(self):
        assert validate_url("http://example.com") is True

    def test_valid_https_url(self):
        assert validate_url("https://example.com") is True

    def test_valid_url_with_path(self):
        assert validate_url("https://example.com/feed.xml") is True

    def test_valid_url_with_port(self):
        assert validate_url("http://example.com:8080/rss") is True

    def test_rejects_ftp_scheme(self):
        assert validate_url("ftp://example.com") is False

    def test_rejects_no_scheme(self):
        assert validate_url("example.com") is False

    def test_rejects_empty_string(self):
        assert validate_url("") is False

    def test_rejects_scheme_only(self):
        assert validate_url("http://") is False

    def test_rejects_file_scheme(self):
        assert validate_url("file:///etc/passwd") is False

    def test_rejects_javascript_scheme(self):
        assert validate_url("javascript:alert(1)") is False


class TestValidateEmail:
    """Tests for validate_email()."""

    def test_valid_simple_email(self):
        assert validate_email("user@example.com") is True

    def test_valid_email_with_subdomain(self):
        assert validate_email("user@mail.example.com") is True

    def test_valid_email_with_plus(self):
        assert validate_email("user+tag@example.com") is True

    def test_rejects_no_at_sign(self):
        assert validate_email("userexample.com") is False

    def test_rejects_empty_local_part(self):
        assert validate_email("@example.com") is False

    def test_rejects_no_dot_in_domain(self):
        assert validate_email("user@localhost") is False

    def test_rejects_empty_string(self):
        assert validate_email("") is False

    def test_rejects_domain_starting_with_dot(self):
        assert validate_email("user@.example.com") is False

    def test_rejects_domain_ending_with_dot(self):
        assert validate_email("user@example.com.") is False

    def test_rejects_no_domain(self):
        assert validate_email("user@") is False


class TestValidatePort:
    """Tests for validate_port()."""

    def test_valid_port_min(self):
        assert validate_port(1) is True

    def test_valid_port_max(self):
        assert validate_port(65535) is True

    def test_valid_common_port(self):
        assert validate_port(587) is True

    def test_rejects_zero(self):
        assert validate_port(0) is False

    def test_rejects_negative(self):
        assert validate_port(-1) is False

    def test_rejects_too_large(self):
        assert validate_port(65536) is False
