# Contributing

Thanks for helping make diagnostic sharing safer.

## Before opening a pull request

1. Keep changes focused and explain the user-visible behavior.
2. Add or update standard-library `unittest` coverage for behavior changes.
3. Install development tools with `python -m pip install -e ".[dev]"`.
4. Run `ruff check src tests` and `ruff format --check src tests`.
5. Run `python -m unittest discover -s tests -v` on Python 3.10 or newer.
6. Do not add real secrets, customer data, or personally identifying diagnostic output to tests, issues, or commits.

## Redaction changes

Redaction is best effort. A new pattern should include safe, synthetic examples, avoid overly broad matching, preserve ordinary text where practical, and document its expected replacement label. Please describe both false-negative and false-positive tradeoffs in the pull request.

## Reporting bugs and requesting features

Use the repository templates for non-sensitive reports. For a suspected vulnerability or a possible redaction bypass involving sensitive material, follow [SECURITY.md](SECURITY.md) instead of publishing details in a public issue.

By contributing, you agree that your contributions may be licensed under the MIT License.
