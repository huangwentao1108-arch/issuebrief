"""Markdown rendering for issue reports."""

from __future__ import annotations

import platform
import re
import shlex
import sys
from collections.abc import Mapping
from typing import Any

from .runner import RunResult


def render_report(
    result: RunResult,
    *,
    stdout: str,
    stderr: str,
    redaction_counts: Mapping[str, int] | None = None,
    include_system_info: bool = True,
    command_text: str | None = None,
    cwd_text: str | None = None,
) -> str:
    """Render a deterministic Markdown report from an executed command."""
    lines = ["# Issue Brief", "", "## Command", ""]
    lines.extend(
        _fenced_text(
            command_text
            if command_text is not None
            else display_command(result.command)
        )
    )
    lines.append("")
    lines.extend(["## Result", ""])
    if result.timed_out:
        lines.append("- Status: timed out")
    elif result.exit_code is None:
        lines.append("- Status: could not start")
    else:
        lines.append("- Status: completed")
    lines.append(
        "- Exit code: "
        + (str(result.exit_code) if result.exit_code is not None else "N/A")
    )
    lines.append(f"- Duration: {result.duration_seconds:.3f}s")
    if result.cwd:
        lines.extend(["- Working directory:", ""])
        lines.extend(_fenced_text(cwd_text if cwd_text is not None else result.cwd))
    lines.append("")

    if include_system_info:
        lines.extend(
            [
                "## System Information",
                "",
                f"- OS: {platform.system()} {platform.release()}",
                f"- Python: {platform.python_version()}",
                "",
            ]
        )

    lines.extend(_text_section("Standard Output", stdout))
    lines.extend(_text_section("Standard Error", stderr))
    lines.extend(["## Redaction", ""])
    counts = redaction_counts or {}
    if counts:
        for name in sorted(counts):
            lines.append(f"- {name}: {counts[name]}")
    else:
        lines.append("- No replacements made.")
    lines.append("")
    return "\n".join(lines)


def _text_section(title: str, value: str) -> list[str]:
    return [f"## {title}", "", *_fenced_text(value), ""]


def _fenced_text(value: str) -> list[str]:
    """Return a fenced code block which cannot be closed by ``value`` itself."""
    longest_run = max(
        (len(run.group()) for run in re.finditer(r"`+", value)), default=0
    )
    fence = "`" * max(3, longest_run + 1)
    return [f"{fence}text", value.rstrip("\n"), fence]


def display_command(command: tuple[str, ...]) -> str:
    if sys.platform == "win32":
        return subprocess_list2cmdline(command)
    return shlex.join(command)


def subprocess_list2cmdline(command: tuple[str, ...]) -> str:
    """Use the standard Windows argument quoting without importing subprocess here."""
    import subprocess

    return subprocess.list2cmdline(list(command))


def normalize_counts(value: Any) -> Mapping[str, int]:
    """Accept the mapping supplied by the redaction module defensively."""
    if isinstance(value, Mapping):
        return {str(key): int(count) for key, count in value.items()}
    return {}
