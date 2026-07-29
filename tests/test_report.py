import unittest

from issuebrief.report import display_command, render_report
from issuebrief.runner import RunResult


class ReportTests(unittest.TestCase):
    def test_report_uses_supplied_redacted_values_in_all_text_sections(self):
        result = RunResult(
            command=("python", "[REDACTED:GITHUB_TOKEN]"),
            stdout="stdout [REDACTED:EMAIL]",
            stderr="stderr [REDACTED:HOME_PATH]",
            exit_code=0,
            duration_seconds=1.2345,
        )
        report = render_report(
            result,
            stdout=result.stdout,
            stderr=result.stderr,
            command_text="python [REDACTED:GITHUB_TOKEN] cwd=[REDACTED:HOME_PATH]",
            redaction_counts={"EMAIL": 1, "HOME_PATH": 2},
            include_system_info=False,
        )

        self.assertIn("## Command", report)
        self.assertIn("## Standard Output", report)
        self.assertIn("## Standard Error", report)
        self.assertIn("cwd=[REDACTED:HOME_PATH]", report)
        self.assertIn("- EMAIL: 1", report)
        self.assertNotIn("## System Information", report)
        self.assertIn("- Duration: 1.234s", report)

    def test_timeout_and_empty_redaction_have_clear_markdown(self):
        result = RunResult(("tool",), "", "", None, 0.01, timed_out=True)
        report = render_report(result, stdout="", stderr="", include_system_info=False)

        self.assertIn("- Status: timed out", report)
        self.assertIn("- Exit code: N/A", report)
        self.assertIn("- No replacements made.", report)
        self.assertTrue(report.endswith("\n"))

    def test_display_command_returns_a_single_safe_display_string(self):
        shown = display_command(("tool", "argument with spaces", "plain"))
        self.assertIsInstance(shown, str)
        self.assertIn("tool", shown)
        self.assertIn("argument", shown)

    def test_dynamic_text_with_backticks_cannot_close_its_code_block(self):
        injected = "safe\n```\n## Not a report heading\n```\nmore"
        result = RunResult(("tool",), injected, injected, 0, 0.0, cwd=injected)
        report = render_report(
            result,
            command_text=injected,
            stdout=injected,
            stderr=injected,
            cwd_text=injected,
            include_system_info=False,
        )

        # Four ticks are selected because the dynamic values contain three;
        # therefore the embedded triple ticks stay literal code content.
        self.assertEqual(4, report.count("````text"))
        self.assertEqual(4, report.count("\n````\n"))
