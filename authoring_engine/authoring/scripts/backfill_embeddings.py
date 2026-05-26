"""기존 approved 문제의 임베딩 백필.

신규성(중복) 검사는 같은 카테고리 형제의 저장 임베딩과 후보를 비교한다. 기능 도입 이전에
저장된 문제는 embedding이 NULL이라 비교에서 제외(fail-open)되므로, 한 번 백필해 둬야
검사가 실제로 작동한다. backend의 PATCH /internal/problems/{id}/embedding로 채운다.

사용법:
    cd authoring_engine
    python -m authoring.scripts.backfill_embeddings              # approved 전체
    python -m authoring.scripts.backfill_embeddings --dry-run    # 계산만, 저장 안 함
    python -m authoring.scripts.backfill_embeddings --limit 10   # 앞 N개만

선행조건:
    - backend가 떠 있고 problem 테이블에 embedding 컬럼이 있어야 한다
      (Postgres: `ALTER TABLE problem ADD COLUMN embedding JSONB;`).
    - 원격 Ollama에 임베딩 모델(JCQ_EMBED_MODEL, 기본 bge-m3)이 pull돼 있어야 한다.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

import argparse

from rich.console import Console

from ..backend_client import (
    fetch_problem,
    list_problems,
    set_problem_embedding,
)
from ..config import EMBED_MODEL
from ..embeddings import embed_text, problem_text

console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="approved 문제 임베딩 백필")
    parser.add_argument("--dry-run", action="store_true", help="계산만 하고 저장하지 않음")
    parser.add_argument("--limit", type=int, default=None, help="처리할 최대 문제 수")
    args = parser.parse_args()

    summaries = [s for s in list_problems(originals_only=False) if s.status == "approved"]
    if args.limit is not None:
        summaries = summaries[: args.limit]

    console.print(
        f"[bold]백필 대상[/bold]: approved {len(summaries)}개 · 모델 {EMBED_MODEL}"
        + (" · [yellow]dry-run[/yellow]" if args.dry_run else "")
    )

    ok = 0
    failed = 0
    for s in summaries:
        try:
            p = fetch_problem(s.id)
            text = problem_text(p.title, p.statement, p.intent_rubric.model_dump())
            vec = embed_text(text)
            if not args.dry_run:
                set_problem_embedding(s.id, vec)
            ok += 1
            console.print(f"  [green]✓[/green] #{s.id} {s.title} (dim={len(vec)})")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            console.print(f"  [red]✗[/red] #{s.id} {s.title} — {exc}")

    console.print(f"[bold]완료[/bold]: 성공 {ok} · 실패 {failed}")


if __name__ == "__main__":
    main()
