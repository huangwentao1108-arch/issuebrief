# issuebrief

Create a shareable GitHub Issue Markdown report from a command's output—locally, with best-effort redaction.

**Before sharing, review every generated report yourself.** Redaction is heuristic and cannot guarantee that every secret, personal detail, or sensitive path has been removed.

[简体中文 README](README.zh-CN.md)

## In 30 seconds

```console
python -m pip install "git+https://github.com/huangwentao1108-arch/issuebrief.git@v0.1.0"
issuebrief run --output issue.md -- python -m your_package --diagnose
```

Open `issue.md`, inspect it for sensitive material, then paste it into a GitHub Issue if it is safe to do so.

`issuebrief` never sends your command output anywhere: no network requests, no account, no telemetry, and no background service. It runs the command you explicitly provide and writes only the requested report.

## Commands

### Run and report

```console
issuebrief run [--output PATH] [--timeout SECONDS] [--no-system-info] -- COMMAND...
```

The command runs without a shell. Its standard output, standard error, displayed command, and the current user's home path are passed through the built-in redactor before Markdown is written.

```console
# Default output is issue-report.md
issuebrief run -- python -m pip --version

# Stop the child process after ten seconds
issuebrief run --timeout 10 --output diagnostics.md -- your-command --flag

# Do not include OS and Python version metadata
issuebrief run --no-system-info -- your-command
```

The report contains the command, status, exit code, duration, sanitized working directory, optional system information, sanitized stdout/stderr, and replacement counts.

### Sanitize existing text

```console
issuebrief sanitize [FILE|-]
```

With no argument (or `-`), reads standard input and writes sanitized text to standard output:

```console
issuebrief sanitize app.log > app-sanitized.log
some-command 2>&1 | issuebrief sanitize
```

## Exit codes

For `run`, the child command's exit code is returned when it completes. A timeout returns `124`; a command that cannot be started returns `127`. Argument, input, and output errors are reported by the CLI and exit nonzero. `sanitize` returns `0` after successfully writing sanitized text.

## Redaction and its limits

The built-in rules target common credentials (including GitHub-style tokens, bearer credentials, private-key blocks, common API key assignments, and credential URLs), email addresses, home-directory paths, and non-loopback IPv4 addresses. Replacements are visibly marked, for example `[REDACTED:GITHUB_TOKEN]`.

This is deliberately a small, deterministic first-pass safety tool—not a security boundary or a complete secret scanner. Custom formats, encoded values, context that identifies a person or company, and newly introduced credential patterns can remain. Never run untrusted commands merely to make a report; never publish a report until a human has reviewed it.

## Requirements and development

- Python 3.10 or newer
- No runtime network access or third-party runtime dependency

The project is installable directly from its versioned release tag today. Publishing
the same package on PyPI is planned after its trusted-publishing setup is complete.

Run the standard-library test suite from a checkout:

```console
python -m pip install -e ".[dev]"
ruff check src tests
ruff format --check src tests
python -m unittest discover -s tests -v
python -m build
python -m twine check dist/*
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance, [SECURITY.md](SECURITY.md) for vulnerability reporting, and [CHANGELOG.md](CHANGELOG.md) for releases.

## License

MIT. See [LICENSE](LICENSE).
