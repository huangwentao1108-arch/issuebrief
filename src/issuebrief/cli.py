"""Command line interface for issuebrief."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from . import __version__
from .report import display_command, normalize_counts, render_report
from .runner import run_command

TIMEOUT_EXIT_CODE = 124
LAUNCH_ERROR_EXIT_CODE = 127

if TYPE_CHECKING:
    from .redaction import RedactionResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="issuebrief",
        description="Capture and redact a command's diagnostic output.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run = subparsers.add_parser(
        "run", help="run a command and write a redacted Markdown report"
    )
    run.add_argument(
        "--output",
        type=Path,
        default=Path("issue-report.md"),
        metavar="PATH",
        help="report path (default: issue-report.md)",
    )
    run.add_argument(
        "--timeout",
        type=_positive_seconds,
        metavar="SECONDS",
        help="maximum command runtime",
    )
    run.add_argument(
        "--no-system-info", action="store_true", help="omit OS and Python details"
    )
    run.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        metavar="COMMAND",
        help="command to run; precede it with --",
    )

    sanitize = subparsers.add_parser(
        "sanitize", help="redact a text file or standard input"
    )
    sanitize.add_argument(
        "input",
        nargs="?",
        type=Path,
        metavar="PATH",
        help="input path; stdin when omitted or '-' ",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv[:1] == ["run"] and "--" not in raw_argv[1:]:
        parser.error(
            "run requires -- before the command (for example: issuebrief run -- python --version)"
        )
    args = parser.parse_args(raw_argv)
    if args.subcommand == "run":
        # With ``argparse.REMAINDER`` the separator is retained on some Python
        # versions.  It is syntax, not part of the subprocess command.
        if args.command[:1] == ["--"]:
            args.command = args.command[1:]
        if not args.command:
            parser.error(
                "run requires a command after -- (for example: issuebrief run -- python --version)"
            )
        return _run(args, parser)
    return _sanitize(args, parser)


def _run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    result = run_command(args.command, timeout=args.timeout)
    stdout_result = _redact(result.stdout)
    stderr_result = _redact(result.stderr)
    command_result = _redact(display_command(result.command))
    cwd_result = _redact(result.cwd)
    counts = _combine_counts(
        stdout_result.counts,
        stderr_result.counts,
        command_result.counts,
        cwd_result.counts,
    )
    report = render_report(
        result,
        stdout=stdout_result.text,
        stderr=stderr_result.text,
        redaction_counts=counts,
        include_system_info=not args.no_system_info,
        command_text=command_result.text,
        cwd_text=cwd_result.text,
    )
    try:
        args.output.write_text(report, encoding="utf-8", newline="\n")
    except OSError as error:
        parser.error(f"could not write report to {args.output}: {error}")
    if result.timed_out:
        return TIMEOUT_EXIT_CODE
    if result.exit_code is None:
        return LAUNCH_ERROR_EXIT_CODE
    return result.exit_code


def _sanitize(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        if args.input is None or str(args.input) == "-":
            source = sys.stdin.read()
        else:
            source = args.input.read_text(encoding="utf-8")
    except OSError as error:
        parser.error(f"could not read input: {error}")
    sys.stdout.write(_redact(source).text)
    return 0


def _redact(text: str) -> RedactionResult:
    # Imported lazily so ``--help`` remains usable if a caller packages only
    # the CLI components, and to keep the public redaction implementation central.
    from .redaction import redact_text

    return redact_text(text, home=str(Path.home()))


def _combine_counts(*counts: object) -> dict[str, int]:
    combined: dict[str, int] = {}
    for count_map in counts:
        for name, count in normalize_counts(count_map).items():
            combined[name] = combined.get(name, 0) + count
    return combined


def _positive_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "timeout must be a number of seconds"
        ) from error
    if seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than zero")
    return seconds
