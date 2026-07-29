"""Safe subprocess execution used by the ``issuebrief run`` command."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True)
class RunResult:
    """The complete result of one subprocess invocation."""

    command: tuple[str, ...]
    stdout: str
    stderr: str
    exit_code: int | None
    duration_seconds: float
    timed_out: bool = False
    cwd: str = ""


def run_command(command: Sequence[str], timeout: float | None = None) -> RunResult:
    """Run *command* once, without a shell, and collect its text streams.

    ``TimeoutExpired`` can contain either bytes or text depending on platform and
    Python version, so both are normalised before returning a result.
    """
    if not command:
        raise ValueError("A command is required.")
    if timeout is not None and timeout <= 0:
        raise ValueError("Timeout must be greater than zero.")

    normalized_command = tuple(str(part) for part in command)
    working_directory = os.getcwd()
    started = perf_counter()
    try:
        process = subprocess.Popen(
            normalized_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            shell=False,
            **_process_group_options(),
        )
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        _terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # ``communicate`` should return promptly after termination, but do
            # not let a defective platform utility prevent report generation.
            process.kill()
            stdout, stderr = process.communicate()
        duration = perf_counter() - started
        return RunResult(
            command=normalized_command,
            stdout=_as_text(stdout) or _as_text(error.stdout),
            stderr=_as_text(stderr) or _as_text(error.stderr),
            exit_code=None,
            duration_seconds=duration,
            timed_out=True,
            cwd=working_directory,
        )
    except OSError as error:
        # Report launch failures too; this is more useful than an uncaught CLI
        # traceback and follows the same report shape as a completed command.
        duration = perf_counter() - started
        return RunResult(
            command=normalized_command,
            stdout="",
            stderr=f"Unable to start command: {error}",
            exit_code=None,
            duration_seconds=duration,
            cwd=working_directory,
        )

    return RunResult(
        command=normalized_command,
        stdout=_as_text(stdout),
        stderr=_as_text(stderr),
        exit_code=process.returncode,
        duration_seconds=perf_counter() - started,
        cwd=working_directory,
    )


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _process_group_options() -> dict[str, object]:
    """Return the platform-specific options needed to own a process tree."""
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Stop ``process`` and descendants after a command timeout."""
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                shell=False,
                timeout=5,
            )
            if completed.returncode == 0:
                return
        except (OSError, subprocess.SubprocessError):
            pass
        process.kill()
        return

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError, PermissionError):
        process.kill()
