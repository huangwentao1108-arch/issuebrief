# Changelog

All notable changes to this project are documented in this file.

## [0.1.1] - 2026-07-29

### Changed

- Prepared the package metadata and documentation for the 0.1.1 release.
- Release tags now use PyPI Trusted Publishing through GitHub Actions OIDC; the
  package is not available from PyPI until that workflow has completed successfully.

## [0.1.0] - 2026-07-29

### Added

- `issuebrief run` to execute a command and write a redacted GitHub Issue Markdown report.
- `issuebrief sanitize` for files and standard input.
- Best-effort redaction for common credentials and identifying diagnostics.
- Local-only operation with no telemetry or network requests.
