"""Render a PR comment from a Qualis JSON report file.

Usage:
    python -m qualis.github <report.json> [<commit-sha>]
"""

from __future__ import annotations

import sys
from pathlib import Path

from qualis.github.comment import render_comment_from_file


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python -m qualis.github <report.json> [<commit-sha>]", file=sys.stderr)
        return 2

    report_path = Path(args[0])
    if not report_path.is_file():
        print(f"Error: report file not found: {report_path}", file=sys.stderr)
        return 1

    commit_sha = args[1] if len(args) > 1 else None
    print(render_comment_from_file(report_path, commit_sha=commit_sha))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
