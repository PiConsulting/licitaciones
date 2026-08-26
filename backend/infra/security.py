from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(token\s*[=:]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(sig=)([^&\s]+)"),
    re.compile(r"(?i)(password\s*[=:]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(accountkey=)([^;\s]+)"),
]


def sanitize_error_message(message: str) -> str:
    sanitized = message
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub(r"\1***", sanitized)
    return sanitized


def sanitize_url_for_logs(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
