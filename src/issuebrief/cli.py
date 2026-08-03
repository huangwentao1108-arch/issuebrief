"""Command line interface for issuebrief."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from . import __version__
from .report import display_command, normalize_counts, render_report
from .runner import DEFAULT_MAX_OUTPUT_BYTES, run_command

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
        "--max-output-bytes",
        type=_positive_integer,
        default=DEFAULT_MAX_OUTPUT_BYTES,
        metavar="BYTES",
        help=(
            "maximum bytes retained from each output stream "
            f"(default: {DEFAULT_MAX_OUTPUT_BYTES})"
        ),
    )
    run.add_argument(
        "--cwd",
        type=Path,
        metavar="PATH",
        help="working directory for the child command",
    )
    run.add_argument(
        "--stdin",
        type=Path,
        metavar="PATH",
        help="read child standard input from PATH; use '-' to inherit standard input",
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
    _add_redaction_arguments(run)

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
    _add_redaction_arguments(sanitize)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    run_arguments = raw_argv[1:] if raw_argv[:1] == ["run"] else []
    help_requested = any(argument in {"-h", "--help"} for argument in run_arguments)
    if run_arguments and "--" not in run_arguments and not help_requested:
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
    extra_patterns = _load_redaction_patterns(args, parser)
    stdin_context = _stdin_context(args.stdin, parser)
    with stdin_context as stdin_stream:
        result = run_command(
            args.command,
            timeout=args.timeout,
            max_output_bytes=args.max_output_bytes,
            cwd=args.cwd,
            stdin=stdin_stream,
        )
    stdout_result = _redact(result.stdout, extra_patterns)
    stderr_result = _redact(result.stderr, extra_patterns)
    command_result = _redact(display_command(result.command), extra_patterns)
    cwd_result = _redact(result.cwd, extra_patterns)
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
    extra_patterns = _load_redaction_patterns(args, parser)
    try:
        if args.input is None or str(args.input) == "-":
            source = sys.stdin.read()
        else:
            source = args.input.read_text(encoding="utf-8")
    except OSError as error:
        parser.error(f"could not read input: {error}")
    sys.stdout.write(_redact(source, extra_patterns).text)
    return 0


def _redact(text: str, extra_patterns: Sequence[str] = ()) -> RedactionResult:
    # Imported lazily so ``--help`` remains usable if a caller packages only
    # the CLI components, and to keep the public redaction implementation central.
    from .redaction import redact_text

    return redact_text(text, home=str(Path.home()), extra_patterns=extra_patterns)


def _add_redaction_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--redact-pattern",
        action="append",
        default=[],
        metavar="REGEX",
        help="additional regular expression to redact; may be repeated",
    )
    parser.add_argument(
        "--redact-file",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help="UTF-8 file containing one redaction regex per line",
    )


def _load_redaction_patterns(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> tuple[str, ...]:
    patterns = list(args.redact_pattern)
    for path in args.redact_file:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            parser.error(f"could not read redaction file {path}: {error}")
        patterns.extend(
            line.strip()
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        )
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as error:
            parser.error(f"invalid redaction pattern {pattern!r}: {error}")
    return tuple(patterns)


def _stdin_context(
    path: Path | None, parser: argparse.ArgumentParser
) -> AbstractContextManager[int | BinaryIO | None]:
    if path is None:
        return nullcontext(subprocess.DEVNULL)
    if str(path) == "-":
        return nullcontext(sys.stdin.buffer)
    try:
        return path.open("rb")
    except OSError as error:
        parser.error(f"could not read child standard input from {path}: {error}")
    raise AssertionError("parser.error must exit")


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


def _positive_integer(value: str) -> int:
    try:
        integer = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if integer <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return integer
