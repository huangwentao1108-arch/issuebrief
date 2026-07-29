import subprocess
import unittest
from unittest.mock import MagicMock, patch

from issuebrief.runner import _terminate_process_tree, run_command


class RunCommandTests(unittest.TestCase):
    def test_runs_without_a_shell_and_collects_output(self):
        process = MagicMock()
        process.communicate.return_value = ("out", "err")
        process.returncode = 3
        with patch("issuebrief.runner.subprocess.Popen", return_value=process) as popen:
            result = run_command(["tool", "arg"], timeout=2)

        self.assertEqual(("tool", "arg"), result.command)
        self.assertEqual(3, result.exit_code)
        self.assertEqual("out", result.stdout)
        self.assertEqual("err", result.stderr)
        self.assertFalse(result.timed_out)
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertEqual(2, process.communicate.call_args.kwargs["timeout"])
        self.assertTrue(
            popen.call_args.kwargs.get("start_new_session", False)
            or "creationflags" in popen.call_args.kwargs
        )

    def test_timeout_normalizes_byte_streams(self):
        error = subprocess.TimeoutExpired(
            ["tool"], 0.1, output=b"partial out", stderr=b"partial err"
        )
        process = MagicMock()
        process.communicate.side_effect = [error, (b"partial out", b"partial err")]
        with (
            patch("issuebrief.runner.subprocess.Popen", return_value=process),
            patch("issuebrief.runner._terminate_process_tree") as terminate,
        ):
            result = run_command(["tool"], timeout=0.1)

        self.assertTrue(result.timed_out)
        self.assertIsNone(result.exit_code)
        self.assertEqual("partial out", result.stdout)
        self.assertEqual("partial err", result.stderr)
        terminate.assert_called_once_with(process)

    def test_launch_failure_is_a_result_not_an_exception(self):
        with patch(
            "issuebrief.runner.subprocess.Popen",
            side_effect=FileNotFoundError("missing-tool"),
        ):
            result = run_command(["missing-tool"])

        self.assertFalse(result.timed_out)
        self.assertIsNone(result.exit_code)
        self.assertIn("Unable to start command", result.stderr)

    def test_rejects_empty_command_and_non_positive_timeout(self):
        with self.assertRaises(ValueError):
            run_command([])
        with self.assertRaises(ValueError):
            run_command(["tool"], timeout=0)

    def test_unix_timeout_terminates_the_process_group(self):
        process = MagicMock(pid=42)
        with (
            patch("issuebrief.runner.os.name", "posix"),
            patch("issuebrief.runner.os.killpg", create=True) as killpg,
            patch("issuebrief.runner.signal.SIGKILL", 9, create=True),
        ):
            _terminate_process_tree(process)

        killpg.assert_called_once()
        self.assertEqual(42, killpg.call_args.args[0])
        process.kill.assert_not_called()

    def test_windows_timeout_uses_taskkill_and_falls_back_to_direct_kill(self):
        process = MagicMock(pid=42)
        failed = subprocess.CompletedProcess(("taskkill",), 1)
        with (
            patch("issuebrief.runner.os.name", "nt"),
            patch("issuebrief.runner.subprocess.run", return_value=failed) as taskkill,
        ):
            _terminate_process_tree(process)

        self.assertFalse(taskkill.call_args.kwargs["shell"])
        self.assertIn("/T", taskkill.call_args.args[0])
        process.kill.assert_called_once()
