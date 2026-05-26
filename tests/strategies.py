"""Hypothesis strategies for feed2email property-based tests."""

import string
from datetime import datetime, timezone

from hypothesis import strategies as st

from feed2email.models import FeedItem


# --- URL Strategies ---

_VALID_SCHEMES = st.sampled_from(["http://", "https://"])

_DOMAIN_CHARS = string.ascii_lowercase + string.digits
_DOMAIN_LABEL = st.text(alphabet=_DOMAIN_CHARS, min_size=1, max_size=20)
_TLD = st.sampled_from(["com", "org", "net", "io", "dev", "co.uk", "edu"])

_PATH_SEGMENT = st.text(
    alphabet=string.ascii_lowercase + string.digits + "-_",
    min_size=0,
    max_size=15,
)


@st.composite
def valid_urls(draw: st.DrawFn) -> str:
    """Generate valid http/https URLs."""
    scheme = draw(_VALID_SCHEMES)
    label = draw(_DOMAIN_LABEL)
    tld = draw(_TLD)
    domain = f"{label}.{tld}"
    # Optionally add a path
    path_segments = draw(st.lists(_PATH_SEGMENT, min_size=0, max_size=3))
    path = "/".join(seg for seg in path_segments if seg)
    url = f"{scheme}{domain}"
    if path:
        url = f"{url}/{path}"
    return url


_INVALID_SCHEMES = st.sampled_from(
    [
        "ftp://",
        "file://",
        "mailto:",
        "javascript:",
        "data:",
        "",
        "htp://",
        "htps://",
        "ssh://",
        "telnet://",
    ]
)


@st.composite
def invalid_urls(draw: st.DrawFn) -> str:
    """Generate URLs with bad schemes or malformed structure."""
    choice = draw(st.integers(min_value=0, max_value=3))
    if choice == 0:
        # Bad scheme
        scheme = draw(_INVALID_SCHEMES)
        label = draw(_DOMAIN_LABEL)
        tld = draw(_TLD)
        return f"{scheme}{label}.{tld}"
    elif choice == 1:
        # No scheme at all
        label = draw(_DOMAIN_LABEL)
        tld = draw(_TLD)
        return f"{label}.{tld}"
    elif choice == 2:
        # Scheme but no authority
        scheme = draw(st.sampled_from(["http://", "https://"]))
        return scheme
    else:
        # Empty or whitespace
        return draw(st.sampled_from(["", " ", "\t", "\n"]))


# --- Email Strategies ---

_EMAIL_LOCAL_CHARS = string.ascii_lowercase + string.digits + "._+-"
_EMAIL_LOCAL = st.text(alphabet=_EMAIL_LOCAL_CHARS, min_size=1, max_size=30).filter(
    lambda s: not s.startswith(".") and not s.endswith(".") and ".." not in s
)
_EMAIL_DOMAIN_LABEL = st.text(alphabet=_DOMAIN_CHARS, min_size=1, max_size=15)


@st.composite
def valid_emails(draw: st.DrawFn) -> str:
    """Generate valid email addresses in local-part@domain format."""
    local = draw(_EMAIL_LOCAL)
    domain_label = draw(_EMAIL_DOMAIN_LABEL)
    tld = draw(_TLD)
    return f"{local}@{domain_label}.{tld}"


@st.composite
def invalid_emails(draw: st.DrawFn) -> str:
    """Generate malformed email addresses."""
    choice = draw(st.integers(min_value=0, max_value=4))
    if choice == 0:
        # Missing @
        return draw(
            st.text(
                alphabet=string.ascii_lowercase + string.digits,
                min_size=3,
                max_size=20,
            )
        )
    elif choice == 1:
        # Missing domain
        local = draw(_EMAIL_LOCAL)
        return f"{local}@"
    elif choice == 2:
        # Missing local part
        domain = draw(_EMAIL_DOMAIN_LABEL)
        tld = draw(_TLD)
        return f"@{domain}.{tld}"
    elif choice == 3:
        # No dot in domain
        local = draw(_EMAIL_LOCAL)
        domain = draw(_EMAIL_DOMAIN_LABEL)
        return f"{local}@{domain}"
    else:
        # Empty string
        return ""


# --- Feed Item Strategies ---

_OPTIONAL_TEXT = st.one_of(st.none(), st.text(min_size=1, max_size=100))
_OPTIONAL_DATETIME = st.one_of(
    st.none(),
    st.datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2030, 12, 31),
        timezones=st.just(timezone.utc),
    ),
)


@st.composite
def feed_items(draw: st.DrawFn) -> FeedItem:
    """Generate FeedItem dataclass instances with various field combinations."""
    return FeedItem(
        id=draw(_OPTIONAL_TEXT),
        title=draw(_OPTIONAL_TEXT),
        link=draw(st.one_of(st.none(), valid_urls())),
        content=draw(_OPTIONAL_TEXT),
        published=draw(_OPTIONAL_DATETIME),
    )


@st.composite
def feed_items_with_id(draw: st.DrawFn) -> FeedItem:
    """Generate FeedItem instances that always have a non-None id."""
    return FeedItem(
        id=draw(st.text(min_size=1, max_size=100)),
        title=draw(_OPTIONAL_TEXT),
        link=draw(st.one_of(st.none(), valid_urls())),
        content=draw(_OPTIONAL_TEXT),
        published=draw(_OPTIONAL_DATETIME),
    )


@st.composite
def feed_items_with_title(draw: st.DrawFn) -> FeedItem:
    """Generate FeedItem instances that always have a non-None title."""
    return FeedItem(
        id=draw(_OPTIONAL_TEXT),
        title=draw(st.text(min_size=1, max_size=200)),
        link=draw(st.one_of(st.none(), valid_urls())),
        content=draw(_OPTIONAL_TEXT),
        published=draw(_OPTIONAL_DATETIME),
    )


# --- HTML Strategies ---

_HTML_TAGS = st.sampled_from(
    [
        "p",
        "div",
        "span",
        "a",
        "b",
        "i",
        "em",
        "strong",
        "h1",
        "h2",
        "h3",
        "ul",
        "li",
        "br",
        "img",
    ]
)

_TEXT_CONTENT = st.text(
    alphabet=string.ascii_letters + string.digits + " .,!?",
    min_size=0,
    max_size=50,
)


@st.composite
def html_strings(draw: st.DrawFn) -> str:
    """Generate HTML strings with various tag structures."""
    num_elements = draw(st.integers(min_value=1, max_value=5))
    parts: list[str] = []
    for _ in range(num_elements):
        tag = draw(_HTML_TAGS)
        text = draw(_TEXT_CONTENT)
        element_type = draw(st.integers(min_value=0, max_value=2))
        if element_type == 0:
            # Self-closing or void element
            if tag in ("br", "img"):
                parts.append(f"<{tag}>{text}")
            else:
                parts.append(f"<{tag}>{text}</{tag}>")
        elif element_type == 1:
            # Element with attributes
            attr = draw(
                st.sampled_from(
                    [
                        'class="test"',
                        'id="item"',
                        'href="http://example.com"',
                        'style="color:red"',
                    ]
                )
            )
            parts.append(f"<{tag} {attr}>{text}</{tag}>")
        else:
            # Nested elements
            inner_tag = draw(_HTML_TAGS)
            parts.append(f"<{tag}><{inner_tag}>{text}</{inner_tag}></{tag}>")
    return "".join(parts)
