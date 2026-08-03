"""Safe subprocess execution used by the ``issuebrief run`` command."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from os import PathLike
from time import perf_counter
from typing import BinaryIO

DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024


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
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    output_limit_bytes: int = 0


def run_command(
    command: Sequence[str],
    timeout: float | None = None,
    *,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    cwd: str | PathLike[str] | None = None,
    stdin: int | BinaryIO | None = subprocess.DEVNULL,
) -> RunResult:
    """Run *command* once and retain bounded stdout/stderr without a shell."""
    if not command:
        raise ValueError("A command is required.")
    if timeout is not None and timeout <= 0:
        raise ValueError("Timeout must be greater than zero.")
    if max_output_bytes <= 0:
        raise ValueError("Maximum output bytes must be greater than zero.")

    normalized_command = tuple(str(part) for part in command)
    working_directory = (
        os.path.abspath(os.fspath(cwd)) if cwd is not None else os.getcwd()
    )
    started = perf_counter()
    try:
        process = subprocess.Popen(
            normalized_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=stdin,
            shell=False,
            cwd=cwd,
            **_process_group_options(),
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

    stdout_capture = _BoundedCapture(max_output_bytes)
    stderr_capture = _BoundedCapture(max_output_bytes)
    readers = (
        threading.Thread(
            target=_drain_stream,
            args=(process.stdout, stdout_capture),
            name="issuebrief-stdout",
            daemon=True,
        ),
        threading.Thread(
            target=_drain_stream,
            args=(process.stderr, stderr_capture),
            name="issuebrief-stderr",
            daemon=True,
        ),
    )
    for reader in readers:
        reader.start()

    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # ``wait`` should return promptly after termination, but do
            # not let a defective platform utility prevent report generation.
            process.kill()
            process.wait()
    finally:
        for reader in readers:
            reader.join()

    return RunResult(
        command=normalized_command,
        stdout=stdout_capture.text,
        stderr=stderr_capture.text,
        exit_code=None if timed_out else process.returncode,
        duration_seconds=perf_counter() - started,
        timed_out=timed_out,
        cwd=working_directory,
        stdout_truncated=stdout_capture.truncated,
        stderr_truncated=stderr_capture.truncated,
        stdout_bytes=stdout_capture.total_bytes,
        stderr_bytes=stderr_capture.total_bytes,
        output_limit_bytes=max_output_bytes,
    )


class _BoundedCapture:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.data = bytearray()
        self.total_bytes = 0

    def add(self, chunk: bytes) -> None:
        self.total_bytes += len(chunk)
        remaining = self.limit - len(self.data)
        if remaining > 0:
            self.data.extend(chunk[:remaining])

    @property
    def truncated(self) -> bool:
        return self.total_bytes > len(self.data)

    @property
    def text(self) -> str:
        return bytes(self.data).decode(errors="replace")


def _drain_stream(stream: BinaryIO | None, capture: _BoundedCapture) -> None:
    if stream is None:
        return
    try:
        while chunk := stream.read(64 * 1024):
            capture.add(chunk)
    finally:
        stream.close()


def _process_group_options() -> dict[str, object]:
    """Return the platform-specific options needed to own a process tree."""
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
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
