# Changelog

All notable changes to this project are documented in this file.

## [0.2.0] - 2026-08-03

### Added

- Bounded stdout and stderr capture with visible truncation metadata.
- `--cwd`, `--stdin`, and `--max-output-bytes` controls for `issuebrief run`.
- Repeatable `--redact-pattern` and `--redact-file` options for project-specific
  redaction rules.
- Built-in redaction for Basic authorization, cookie headers, API-key headers,
  and non-loopback IPv6 addresses.
- Python 3.14 package metadata and CI coverage across Linux, macOS, and Windows.

### Changed

- Child commands receive no standard input by default, preventing accidental
  interactive hangs. Use `--stdin PATH` or `--stdin -` explicitly when needed.

## [0.1.1] - 2026-07-30

### Changed

- Prepared the package metadata and documentation for the 0.1.1 release.
- Published the package through GitHub Actions OIDC Trusted Publishing without a
  long-lived PyPI API token.

## [0.1.0] - 2026-07-29

### Added

- `issuebrief run` to execute a command and write a redacted GitHub Issue Markdown report.
- `issuebrief sanitize` for files and standard input.
- Best-effort redaction for common credentials and identifying diagnostics.
- Local-only operation with no telemetry or network requests.
