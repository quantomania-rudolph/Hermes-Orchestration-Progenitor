"""NGINX combined access log line parser."""

from __future__ import annotations

import re

__all__ = ["parse_line"]

# remote_addr ident user [time] "METHOD path HTTP/x.x" status body_bytes_sent ...
_LINE_RE = re.compile(
    r"^(?P<ip>\S+)\s+"
    r"\S+\s+\S+\s+"
    r"\[[^\]]+\]\s+"
    r'"(?:\S+)\s+(?P<path>\S+)\s+\S+"\s+'
    r"(?P<status>\d{3})\s+"
    r"(?P<bytes>\d+)"
)


def parse_line(line: str) -> dict | None:
    """Parse one nginx combined log line into ip/status/path/bytes, or None if malformed."""
    text = line.strip()
    if not text:
        return None

    match = _LINE_RE.match(text)
    if match is None:
        return None

    return {
        "ip": match.group("ip"),
        "status": int(match.group("status")),
        "path": match.group("path"),
        "bytes": int(match.group("bytes")),
    }
