"""출제 엔진 CLI 진입점.

사용법:
    cd authoring_engine
    python -m authoring.main --problem-id <ID> [--count 5]

    환경변수는 authoring_engine/.env 에 작성한다 (.env.example 참고).
"""
from pathlib import Path

from dotenv import load_dotenv

# 백엔드 src.storage.db가 모듈 임포트 시점에 JCQ_DB_URL을 읽으므로
# 다른 모든 임포트보다 먼저 실행되어야 한다.
load_dotenv(Path(__file__).parent.parent / ".env")

import argparse
import os

from rich.console import Console
from rich.table import Table

console = Console()


def _preflight_check() -> None:
    """실행 전 필수 조건을 점검하고 문제가 있으면 명확한 메시지를 출력한다."""
    import os
    from pathlib import Path
    from .config import BACKEND_PATH, ensure_backend_on_path

    # JCQ_DB_URL 절대경로 주입 (미설정 시)
    ensure_backend_on_path()

    db_url = os.environ.get("JCQ_DB_URL", "")
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.removeprefix("sqlite:///"))
        if not db_path.is_absolute():
            console.print(
                f"[yellow]경고: JCQ_DB_URL이 상대경로입니다 ({db_url}). "
                "CWD에 따라 다른 DB를 가리킬 수 있습니다.[/yellow]"
            )
        elif not db_path.exists():
            console.print(
                f"[bold red]오류: DB 파일이 없습니다 → {db_path}[/bold red]\n"
                f"  백엔드를 한 번 실행해 init_db()로 DB를 생성하거나,\n"
                f"  env.sh에서 JCQ_DB_URL을 올바른 절대경로로 설정하세요.\n"
                f"  현재 기본값: sqlite:///{BACKEND_PATH / 'data' / 'jcq.db'}"
            )
            raise SystemExit(1)

    if not os.environ.get("OLLAMA_BASE_URL"):
        console.print("[yellow]경고: OLLAMA_BASE_URL이 설정되지 않았습니다. 기본값 http://localhost:11434 사용[/yellow]")


def _setup_langsmith() -> None:
    """LANGSMITH_API_KEY가 있으면 LangChain 자동 트레이싱을 활성화한다."""
    key = os.getenv("LANGSMITH_API_KEY", "")
    if not key:
        return
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    os.environ.setdefault("LANGCHAIN_API_KEY", key)
    from .config import LANGSMITH_PROJECT
    os.environ.setdefault("LANGCHAIN_PROJECT", LANGSMITH_PROJECT)
    console.print(f"[dim]LangSmith 트레이싱 활성화: project={os.environ['LANGCHAIN_PROJECT']}[/dim]")


def _print_results(final_state: dict) -> None:
    candidates = final_state.get("candidates", [])
    saved = final_state.get("saved_problem_ids", [])
    errors = final_state.get("errors", [])

    table = Table(title="출제 파이프라인 결과", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("제목", min_width=20)
    table.add_column("생성", justify="center", width=6)
    table.add_column("검증", justify="center", width=6)
    table.add_column("품질심사", justify="center", width=10)
    table.add_column("풀이검증", justify="center", width=10)
    table.add_column("저장 ID", justify="center", width=8)

    for c in candidates:
        ac_count = sum(1 for r in c.get("solver_results", []) if r.get("verdict") == "AC")
        solver_total = len(c.get("solver_results", []))

        table.add_row(
            str(c["index"]),
            c.get("title", "N/A"),
            "[green]✓[/green]",
            "[green]✓[/green]" if c.get("verify_passed") else f"[red]✗[/red] {c.get('verify_error', '')[:30]}",
            f"[green]✓ {c.get('judge_score', 0):.2f}[/green]"
            if c.get("judge_passed")
            else f"[red]✗ {c.get('judge_score', 0):.2f}[/red]",
            f"[green]✓ {ac_count}/{solver_total}[/green]"
            if c.get("solver_passed")
            else (f"[red]✗ {ac_count}/{solver_total}[/red]" if solver_total else "[dim]skip[/dim]"),
            str(c.get("saved_id") or "—"),
        )

    console.print(table)
    console.print(f"\n[bold green]저장 완료: {len(saved)}개[/bold green] → problem_id {saved}")

    if errors:
        console.print(f"\n[bold red]오류 {len(errors)}건:[/bold red]")
        for e in errors:
            console.print(f"  • {e}")


def run(problem_id: int, count: int) -> None:
    _preflight_check()
    _setup_langsmith()

    from langchain_core.runnables import RunnableConfig

    from .pipeline.graph import build_graph

    initial_state = {
        "original_problem_id": problem_id,
        "target_count": count,
        "original_problem": None,
        "seeds": [],
        "candidates": [],
        "saved_problem_ids": [],
        "errors": [],
    }

    graph = build_graph()

    console.rule(f"[bold]JCodeQuest 출제 엔진[/bold]  problem_id={problem_id}  count={count}")

    config = RunnableConfig(
        run_name="authoring_pipeline",
        tags=["authoring", f"problem_{problem_id}"],
    )
    final_state = graph.invoke(initial_state, config=config)

    _print_results(final_state)


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="JCodeQuest 출제 엔진 — 원본 문제를 기반으로 유사 문제를 자동 생성·검증·저장"
    )
    parser.add_argument("--problem-id", type=int, required=True, help="원본 문제 ID")
    parser.add_argument(
        "--count", type=int, default=5, help="생성할 변형 문제 수 (기본값: 5)"
    )
    args = parser.parse_args()
    run(args.problem_id, args.count)


if __name__ == "__main__":
    cli()
