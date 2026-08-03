"""Conservative, text-only secret redaction used when building issue briefs."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from ipaddress import IPv6Address
from pathlib import Path


@dataclass(frozen=True)
class RedactionResult:
    """The redacted text and the number of replacements made by category."""

    text: str
    counts: dict[str, int]


_MASK_PREFIX = "[REDACTED:"
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "PEM_PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"
        ),
    ),
    (
        "URL_CREDENTIALS",
        re.compile(r"\b([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@", re.IGNORECASE),
    ),
    (
        "COOKIE_HEADER",
        re.compile(
            r"^([ \t]*(?:Cookie|Set-Cookie)[ \t]*:[ \t]*)[^\r\n]+",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "BASIC_AUTH",
        re.compile(
            r"(\bAuthorization[ \t]*:[ \t]*Basic[ \t]+)[A-Za-z0-9+/=]+",
            re.IGNORECASE,
        ),
    ),
    (
        "API_KEY_HEADER",
        re.compile(r"(\bX-Api-Key[ \t]*:[ \t]*)[^\s,;]+", re.IGNORECASE),
    ),
    (
        "GITHUB_TOKEN",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{10,}\b"),
    ),
    (
        "GITHUB_PAT",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "AWS_ACCESS_KEY",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    (
        "GITLAB_TOKEN",
        re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "GOOGLE_API_KEY",
        re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),
    ),
    (
        "NPM_TOKEN",
        re.compile(r"\bnpm_[A-Za-z0-9]{20,}\b"),
    ),
    (
        "STRIPE_LIVE_KEY",
        re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
    ),
    (
        "OPENAI_TOKEN",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{8,}\b"),
    ),
    (
        "SLACK_TOKEN",
        re.compile(r"\bxox(?:a|b|p|o|r|s)-[A-Za-z0-9-]{10,}\b", re.IGNORECASE),
    ),
    (
        "BEARER_TOKEN",
        re.compile(
            r"(?P<prefix>\bBearer[ \t]+)(?:(?P<quote>[\"'])(?P<quoted>[A-Za-z0-9._~+/=-]{8,})(?P=quote)|(?P<bare>[A-Za-z0-9._~+/=-]{8,})\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "JWT",
        re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b"),
    ),
    (
        "CREDENTIAL_VALUE",
        re.compile(
            r"((?:[\"']?(?:password|passwd|pwd|token|api[_-]?key|secret|access[_-]?token)[\"']?)\s*(?:=|:)\s*)([\"']?)(?!\[REDACTED:)([^\s,;\"'`}\]]+)\2",
            re.IGNORECASE,
        ),
    ),
    (
        "EMAIL",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    ),
    (
        "IPV4",
        re.compile(
            r"\b(?!(?:127\.0\.0\.1)\b)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
        ),
    ),
)

_IPV6_CANDIDATE = re.compile(
    r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![0-9A-Fa-f:])"
)


def _mask(kind: str) -> str:
    return f"[REDACTED:{kind}]"


def _replace_pattern(
    text: str, pattern: re.Pattern[str], kind: str, counts: dict[str, int]
) -> str:
    def replacement(match: re.Match[str]) -> str:
        # This also makes a second pass stable if a caller supplied a broad rule.
        if _MASK_PREFIX in match.group(0):
            return match.group(0)
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "URL_CREDENTIALS":
            return match.group(1) + _mask(kind) + "@"
        if kind in {"COOKIE_HEADER", "BASIC_AUTH", "API_KEY_HEADER"}:
            return match.group(1) + _mask(kind)
        if kind == "BEARER_TOKEN":
            quote = match.group("quote") or ""
            return match.group("prefix") + quote + _mask(kind) + quote
        if kind == "CREDENTIAL_VALUE":
            return match.group(1) + match.group(2) + _mask(kind) + match.group(2)
        return _mask(kind)

    return pattern.sub(replacement, text)


def redact_text(
    text: str, *, home: str | None = None, extra_patterns: Sequence[str] = ()
) -> RedactionResult:
    """Redact common credentials without changing ordinary text or line endings.

    ``extra_patterns`` are regular expressions for project-specific secrets.  They
    are applied after built-ins and share the ``EXTRA_PATTERN`` count category.
    Invalid patterns intentionally raise ``re.error`` so callers do not silently
    ship an unprotected issue pack.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a str")

    counts: dict[str, int] = {}
    redacted = text
    for kind, pattern in _PATTERNS:
        redacted = _replace_pattern(redacted, pattern, kind, counts)
    redacted = _replace_ipv6(redacted, counts)

    home_path = str(Path.home() if home is None else home)
    if home_path:
        # Windows tools commonly print either slash style for the same path.
        # Match both without trying to infer any directory beyond the literal home.
        is_windows_path = (
            "\\" in home_path or re.match(r"^[A-Za-z]:", home_path) is not None
        )
        if is_windows_path:
            home_source = r"[\\/]+".join(
                re.escape(part) for part in re.split(r"[\\/]+", home_path)
            )
        else:
            home_source = re.escape(home_path)
        home_pattern = re.compile(home_source, re.IGNORECASE if is_windows_path else 0)
        redacted = _replace_pattern(redacted, home_pattern, "HOME_PATH", counts)

    for source in extra_patterns:
        redacted = _replace_pattern(
            redacted, re.compile(source), "EXTRA_PATTERN", counts
        )

    return RedactionResult(text=redacted, counts=counts)


def _replace_ipv6(text: str, counts: dict[str, int]) -> str:
    def replacement(match: re.Match[str]) -> str:
        candidate = match.group(0)
        try:
            address = IPv6Address(candidate)
        except ValueError:
            return candidate
        if address.is_loopback:
            return candidate
        counts["IPV6"] = counts.get("IPV6", 0) + 1
        return _mask("IPV6")

    return _IPV6_CANDIDATE.sub(replacement, text)
