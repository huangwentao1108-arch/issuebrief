import io
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from issuebrief.runner import _terminate_process_tree, run_command


class RunCommandTests(unittest.TestCase):
    def test_runs_without_a_shell_and_collects_output(self):
        process = MagicMock()
        process.stdout = io.BytesIO(b"out")
        process.stderr = io.BytesIO(b"err")
        process.returncode = 3
        with patch("issuebrief.runner.subprocess.Popen", return_value=process) as popen:
            result = run_command(["tool", "arg"], timeout=2)

        self.assertEqual(("tool", "arg"), result.command)
        self.assertEqual(3, result.exit_code)
        self.assertEqual("out", result.stdout)
        self.assertEqual("err", result.stderr)
        self.assertFalse(result.timed_out)
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertEqual(2, process.wait.call_args.kwargs["timeout"])
        self.assertEqual(subprocess.DEVNULL, popen.call_args.kwargs["stdin"])
        self.assertTrue(
            popen.call_args.kwargs.get("start_new_session", False)
            or "creationflags" in popen.call_args.kwargs
        )

    def test_timeout_normalizes_byte_streams(self):
        error = subprocess.TimeoutExpired(["tool"], 0.1)
        process = MagicMock()
        process.stdout = io.BytesIO(b"partial out")
        process.stderr = io.BytesIO(b"partial err")
        process.wait.side_effect = [error, None]
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
        with self.assertRaises(ValueError):
            run_command(["tool"], max_output_bytes=0)

    def test_large_output_is_drained_but_only_the_limit_is_retained(self):
        result = run_command(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 10000)"],
            max_output_bytes=128,
        )

        self.assertEqual(0, result.exit_code)
        self.assertEqual("x" * 128, result.stdout)
        self.assertTrue(result.stdout_truncated)
        self.assertEqual(10000, result.stdout_bytes)
        self.assertFalse(result.stderr_truncated)

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
