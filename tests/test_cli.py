import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from issuebrief.cli import TIMEOUT_EXIT_CODE, main


class CliTests(unittest.TestCase):
    def test_version_is_available_without_a_subcommand(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as raised, patch("sys.stdout", stdout):
            main(["--version"])

        self.assertEqual(0, raised.exception.code)
        self.assertEqual("issuebrief 0.2.0\n", stdout.getvalue())

    def test_run_requires_an_explicit_command_separator(self):
        with (
            self.assertRaises(SystemExit) as raised,
            patch("sys.stderr", io.StringIO()),
        ):
            main(["run", sys.executable, "--version"])

        self.assertEqual(2, raised.exception.code)

    def test_run_help_does_not_require_a_command_separator(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as raised, patch("sys.stdout", stdout):
            main(["run", "--help"])

        self.assertEqual(0, raised.exception.code)
        self.assertIn("--max-output-bytes", stdout.getvalue())

    def test_run_writes_default_and_custom_reports_and_redacts_command_output(self):
        fake_token = "ghp_" + "abcdefghijklmno12345"
        script = f"print('{fake_token}')"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            custom = root / "custom.md"
            with _chdir(root):
                default_exit = main(
                    [
                        "run",
                        "--no-system-info",
                        "--",
                        sys.executable,
                        "-c",
                        "print('ok')",
                    ]
                )
            custom_exit = main(
                [
                    "run",
                    "--output",
                    str(custom),
                    "--no-system-info",
                    "--",
                    sys.executable,
                    "-c",
                    script,
                ]
            )

            default_report = (root / "issue-report.md").read_text(encoding="utf-8")
            custom_report = custom.read_text(encoding="utf-8")

        self.assertEqual(0, default_exit)
        self.assertEqual(0, custom_exit)
        self.assertIn("ok", default_report)
        self.assertNotIn(fake_token, custom_report)
        self.assertIn("[REDACTED:GITHUB_TOKEN]", custom_report)

    def test_run_returns_command_exit_code_and_timeout_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            failed = main(
                [
                    "run",
                    "--output",
                    str(root / "failed.md"),
                    "--",
                    sys.executable,
                    "-c",
                    "raise SystemExit(7)",
                ]
            )
            timed_out = main(
                [
                    "run",
                    "--output",
                    str(root / "timeout.md"),
                    "--timeout",
                    "0.01",
                    "--",
                    sys.executable,
                    "-c",
                    "import time; time.sleep(1)",
                ]
            )

            timeout_report = (root / "timeout.md").read_text(encoding="utf-8")
        self.assertEqual(7, failed)
        self.assertEqual(TIMEOUT_EXIT_CODE, timed_out)
        self.assertIn("timed out", timeout_report)

    def test_run_never_reports_common_tokens_from_stdout_or_command(self):
        stdout_token = "AKIA" + "ABCDEFGHIJKLMNOP"
        command_token = "glpat-" + "abcdefghijklmnopqrst"
        script = f"print('{stdout_token}')"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.md"
            exit_code = main(
                [
                    "run",
                    "--output",
                    str(output),
                    "--no-system-info",
                    "--",
                    sys.executable,
                    "-c",
                    script,
                    command_token,
                ]
            )
            report = output.read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertNotIn(stdout_token, report)
        self.assertNotIn(command_token, report)
        self.assertIn("[REDACTED:AWS_ACCESS_KEY]", report)
        self.assertIn("[REDACTED:GITLAB_TOKEN]", report)

    def test_sanitize_reads_file_and_stdin(self):
        fake_email = "person@example.test"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.txt"
            source.write_text(f"contact {fake_email}", encoding="utf-8")
            file_output = io.StringIO()
            with patch("sys.stdout", file_output):
                exit_code = main(["sanitize", str(source)])

        stdin_output = io.StringIO()
        with (
            patch("sys.stdin", io.StringIO("token=example-token-12345")),
            patch("sys.stdout", stdin_output),
        ):
            stdin_exit = main(["sanitize", "-"])

        self.assertEqual(0, exit_code)
        self.assertEqual(0, stdin_exit)
        self.assertNotIn(fake_email, file_output.getvalue())
        self.assertIn("[REDACTED:EMAIL]", file_output.getvalue())
        self.assertIn("[REDACTED:CREDENTIAL_VALUE]", stdin_output.getvalue())

    def test_sanitize_supports_custom_patterns_and_pattern_files(self):
        with tempfile.TemporaryDirectory() as directory:
            pattern_file = Path(directory) / "patterns.txt"
            pattern_file.write_text(
                "# project-specific identifiers\ncustomer-[0-9]+\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with (
                patch(
                    "sys.stdin",
                    io.StringIO("tenant-42 customer-123 ordinary-value"),
                ),
                patch("sys.stdout", stdout),
            ):
                exit_code = main(
                    [
                        "sanitize",
                        "--redact-pattern",
                        r"tenant-[0-9]+",
                        "--redact-file",
                        str(pattern_file),
                        "-",
                    ]
                )

        self.assertEqual(0, exit_code)
        self.assertEqual(
            "[REDACTED:EXTRA_PATTERN] [REDACTED:EXTRA_PATTERN] ordinary-value",
            stdout.getvalue(),
        )

    def test_run_controls_cwd_stdin_and_output_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "stdin.txt"
            source.write_text("from-input-file", encoding="utf-8")
            output = root / "report.md"
            exit_code = main(
                [
                    "run",
                    "--output",
                    str(output),
                    "--cwd",
                    str(root),
                    "--stdin",
                    str(source),
                    "--max-output-bytes",
                    "32",
                    "--no-system-info",
                    "--",
                    sys.executable,
                    "-c",
                    "import os,sys; print(sys.stdin.read()); print('x' * 100)",
                ]
            )
            report = output.read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("from-input-file", report)
        self.assertIn("Standard output: truncated", report)

    def test_invalid_custom_pattern_is_a_cli_error(self):
        with (
            self.assertRaises(SystemExit) as raised,
            patch("sys.stderr", io.StringIO()),
        ):
            main(["sanitize", "--redact-pattern", "(", "-"])

        self.assertEqual(2, raised.exception.code)


@contextlib.contextmanager
def _chdir(path: Path):
    previous = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(previous)
