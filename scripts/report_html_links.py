"""Safe link and inline HTML helpers for generated local reports."""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse

from scripts.report_sources import as_list

SAFE_LINK_REL = "noopener noreferrer"
SAFE_HREF_SCHEMES = {"http", "https", "mailto"}
UNSAFE_HREF_CHAR_RE = re.compile(r"""[\x00-\x20"'<>`]""")
TELEGRAM_HANDLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def safe_href(value: object) -> str | None:
    """Return an escaped href attribute value, or None when it is not safe.

    Reports are built from Telegram text and LLM output, so link validation must
    happen before attribute escaping. In particular, quotes and whitespace are
    rejected instead of merely escaped because they usually indicate attribute
    injection attempts or pasted prose rather than a navigable URL.
    """
    href = str(value or "").strip()
    if not href or UNSAFE_HREF_CHAR_RE.search(href):
        return None
    parsed = urlparse(href)
    scheme = parsed.scheme.lower()
    if scheme not in SAFE_HREF_SCHEMES:
        return None
    if scheme in {"http", "https"} and not parsed.netloc:
        return None
    if scheme == "mailto":
        address = parsed.path
        if not EMAIL_RE.fullmatch(address):
            return None
    return html.escape(href, quote=True)


def telegram_handle_to_url(value: object) -> str | None:
    handle = str(value or "").strip()
    if handle.startswith("@"):
        handle = handle[1:]
    if not TELEGRAM_HANDLE_RE.fullmatch(handle):
        return None
    return f"https://t.me/{handle}"


def _safe_link_html(href: object, label: object, *, label_is_html: bool = False) -> str | None:
    safe = safe_href(href)
    if safe is None:
        return None
    label_html = str(label) if label_is_html else _esc(label)
    return (
        f'<a href="{safe}" target="_blank" '
        f'rel="{SAFE_LINK_REL}">{label_html}</a>'
    )


def _link_or_text(href: object, label: object, *, label_is_html: bool = False) -> str:
    link = _safe_link_html(href, label, label_is_html=label_is_html)
    if link:
        return link
    return str(label) if label_is_html else _esc(label)


def readable_url_label(value: object, *, field_name: str = "") -> str:
    parsed = urlparse(str(value or "").strip())
    field = field_name.lower()
    if field == "origin_url":
        return "Open source"
    if parsed.netloc:
        host = parsed.netloc.removeprefix("www.")
        path = parsed.path.strip("/")
        label = host if not path else f"{host}/{path.split('/')[0]}"
        return label[:34] + "..." if len(label) > 37 else label
    return "Open link"


def missing_url_label(field_name: str) -> str:
    field = field_name.lower()
    if field in {"apply_url", "application_url"}:
        return "No apply link found"
    return "No link found"


def _url_field_html(field_name: str, values: list[str]) -> str:
    rendered: list[str] = []
    for value in _split_inline_values(values):
        text = str(value or "").strip()
        if safe_href(text):
            rendered.append(_link_or_text(text, readable_url_label(text, field_name=field_name)))
        elif not text or text.lower() in {"not specified", "unknown", "none", "n/a"}:
            rendered.append(_esc(missing_url_label(field_name)))
        else:
            rendered.append(_esc(f"{missing_url_label(field_name)}: {text}"))
    return _inline_html_group(rendered)


def _tg_md_to_html(text: str) -> str:
    """Convert Telegram-flavored markdown to safe HTML snippets.

    Handles: **bold**, __italic__, `code`, [link](url), https://urls.
    Everything else is HTML-escaped first, then patterns are restored.
    """
    s = html.escape(text, quote=True)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"__(.+?)__", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)

    def _replace_md_link(match: re.Match[str]) -> str:
        label_html = match.group(1)
        href = html.unescape(match.group(2))
        return _link_or_text(href, label_html, label_is_html=True)

    s = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        _replace_md_link,
        s,
    )

    def _replace_bare_url(match: re.Match[str]) -> str:
        label_html = match.group(1)
        href = html.unescape(label_html)
        return _link_or_text(href, label_html, label_is_html=True)

    s = re.sub(
        r"(?<!href=\")(https?://[^\s<\)]+)",
        _replace_bare_url,
        s,
    )
    return s.replace("\n", "<br>\n")


def _channel_link(name: str) -> str:
    name = name.strip()
    telegram_url = telegram_handle_to_url(name)
    if telegram_url:
        return _link_or_text(telegram_url, name)
    if safe_href(name):
        return _link_or_text(name, name)
    return _esc(name)


def _source_links(sources: object) -> str:
    return _inline_html_group([_channel_link(s) for s in _split_inline_values(as_list(sources))])


def _inline_html_group(items: list[str]) -> str:
    cleaned = [item for item in items if item]
    if len(cleaned) <= 1:
        return cleaned[0] if cleaned else ""
    return (
        '<span class="inline-ref-list">'
        + "".join(f'<span class="inline-ref">{item}</span>' for item in cleaned)
        + "</span>"
    )


def _split_inline_values(values: list[str]) -> list[str]:
    """Split legacy report values that used spaced slashes as UI separators.

    Fields like contact/source/link can arrive from older Markdown reports as one
    display string ("Not specified / @handle"). Splitting only at the renderer keeps
    parsing stable while removing the visual slash artifact from the card middle.
    """
    parts = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if " / " in text and not safe_href(text):
            parts.extend(part.strip() for part in text.split(" / ") if part.strip())
        else:
            parts.append(text)
    return parts


def _contact_html(contact: str) -> str:
    contact = str(contact).strip()
    if not contact or contact in ("Not specified", "Unknown"):
        return _esc(contact)
    if contact.startswith("@"):
        telegram_url = telegram_handle_to_url(contact)
        return _link_or_text(telegram_url, contact) if telegram_url else _esc(contact)
    if EMAIL_RE.fullmatch(contact):
        return _link_or_text(f"mailto:{contact}", contact)
    if contact.startswith(("http://", "https://")):
        parsed = urlparse(contact)
        display = parsed.netloc or "link"
        return _link_or_text(contact, display)
    return _esc(contact)
