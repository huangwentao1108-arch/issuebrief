"""Module entry point for :mod:`issuebrief`."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":  # pragma: no cover - exercised by Python itself
    raise SystemExit(main())
