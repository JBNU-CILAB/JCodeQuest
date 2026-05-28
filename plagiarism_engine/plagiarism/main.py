"""CLI — 문제 하나에 대해 표절 검토를 실행한다.

  python -m plagiarism.main --problem-id 3
"""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from .pipeline import run_plagiarism  # noqa: E402  (load_dotenv 후 import)


def main() -> None:
    ap = argparse.ArgumentParser(description="JCodeQuest 표절 검토 (Dolos)")
    ap.add_argument("--problem-id", type=int, required=True)
    args = ap.parse_args()
    result = run_plagiarism(args.problem_id)
    print(
        f"[plagiarism] run={result['run_id']} "
        f"submissions={result['submissions']} flagged={result['flagged']}"
    )


if __name__ == "__main__":
    main()
