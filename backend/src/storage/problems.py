from sqlalchemy import func
from sqlmodel import Session, select

from ..schemas import IntentRubric, Problem, TestCase
from .models import ProblemRow, SubmissionRow, TestCaseRow, TutorMessageRow


def _to_domain(row: ProblemRow) -> Problem:
    return Problem(
        id=row.id,  # type: ignore[arg-type]
        title=row.title,
        statement=row.statement,
        category=row.category,
        level=row.level,  # type: ignore[arg-type]
        points=row.points,
        time_limit_ms=row.time_limit_ms,
        memory_limit_mb=row.memory_limit_mb,
        reference_code=row.reference_code,
        intent_rubric=IntentRubric.model_validate(row.intent_rubric),
        test_cases=[
            TestCase(
                ordinal=t.ordinal,
                stdin=t.stdin,
                expected_stdout=t.expected_stdout,
                is_sample=t.is_sample,
            )
            for t in row.test_cases
        ],
    )


def get_problem(session: Session, problem_id: int) -> Problem | None:
    row = session.get(ProblemRow, problem_id)
    return _to_domain(row) if row else None


def list_category_embeddings(
    session: Session, problem_id: int
) -> list[tuple[int, str, list[float] | None, str, float | None]] | None:
    """problem_id와 같은 카테고리의 approved 문제(자기 자신 제외)의
    (id, title, embedding, level, judge_score)를 반환한다.

    두 용도를 함께 받친다:
      - 신규성 검사: 카테고리 형제 전체와 후보를 비교하는 모집단 (id/title/embedding).
      - RAG exemplar 선정: level(레벨 윈도 필터)·judge_score(품질 가중) 추가.

    embedding이 NULL인 문제도 포함해 반환하며(백필 여부 가시화), 호출 측이 NULL을 건너뛴다.
    judge_score는 authoring_meta JSON에서 끌어오고, 메타가 없거나 숫자가 아니면 None.
    대상 문제가 없으면 None."""
    target = session.get(ProblemRow, problem_id)
    if target is None:
        return None
    stmt = (
        select(
            ProblemRow.id,
            ProblemRow.title,
            ProblemRow.embedding,
            ProblemRow.level,
            ProblemRow.authoring_meta,
        )
        .where(ProblemRow.status == "approved")
        .where(ProblemRow.category == target.category)
        .where(ProblemRow.id != problem_id)  # type: ignore[arg-type]
    )
    out: list[tuple[int, str, list[float] | None, str, float | None]] = []
    for rid, title, emb, level, meta in session.exec(stmt).all():
        score = None
        if isinstance(meta, dict):
            raw = meta.get("judge_score")
            if isinstance(raw, (int, float)):
                score = float(raw)
        out.append((rid, title, emb, level, score))
    return out


def set_problem_embedding(
    session: Session, problem_id: int, embedding: list[float]
) -> bool:
    """기존 문제의 임베딩을 채운다(백필/갱신). 문제가 없으면 False."""
    row = session.get(ProblemRow, problem_id)
    if row is None:
        return False
    row.embedding = embedding
    session.add(row)
    session.commit()
    return True


def list_problems(
    session: Session,
    *,
    status: str | None = None,
    category: str | None = None,
    level: str | None = None,
    iso_week: str | None = None,
) -> list[Problem]:
    stmt = select(ProblemRow)
    if status is not None:
        stmt = stmt.where(ProblemRow.status == status)
    if category is not None:
        stmt = stmt.where(ProblemRow.category == category)
    if level is not None:
        stmt = stmt.where(ProblemRow.level == level)
    if iso_week is not None:
        stmt = stmt.where(ProblemRow.iso_week == iso_week)
    return [_to_domain(r) for r in session.exec(stmt).all()]


def list_problem_rows(
    session: Session,
    *,
    status: str | None = None,
    iso_week: str | None = None,
) -> list[ProblemRow]:
    """row-level 메타(iso_week, created_at)를 그대로 써야 하는 라우터용.
    list_problems는 Problem(shared) 도메인 객체만 돌려주는데 거기에는 주차 컬럼이 없다."""
    stmt = select(ProblemRow)
    if status is not None:
        stmt = stmt.where(ProblemRow.status == status)
    if iso_week is not None:
        stmt = stmt.where(ProblemRow.iso_week == iso_week)
    return list(session.exec(stmt).all())


def list_week_buckets(
    session: Session, *, status: str | None = None
) -> list[tuple[str, int]]:
    """주차별 (week, count)을 ISO 주차 내림차순(최신주가 위)으로 반환."""
    stmt = select(ProblemRow.iso_week, func.count(ProblemRow.id))
    if status is not None:
        stmt = stmt.where(ProblemRow.status == status)
    stmt = stmt.group_by(ProblemRow.iso_week).order_by(
        ProblemRow.iso_week.desc()
    )
    return [(week, count) for week, count in session.exec(stmt).all()]


def create_problem(
    session: Session,
    problem: Problem,
    *,
    status: str = "draft",
    parent_id: int | None = None,
    langsmith_trace_id: str | None = None,
    authoring_meta: dict | None = None,
    iso_week: str | None = None,
    embedding: list[float] | None = None,
) -> int:
    # 출제 주차는 호출자가 명시할 수 있고, 생략 시 ProblemRow.default_factory가
    # 현재 UTC 주차를 박는다(출제 엔진은 명시 전달 — persist 노드/manual create 참조).
    row_kwargs: dict = {}
    if iso_week is not None:
        row_kwargs["iso_week"] = iso_week
    row = ProblemRow(
        title=problem.title,
        statement=problem.statement,
        category=problem.category,
        level=problem.level,
        points=problem.points,
        time_limit_ms=problem.time_limit_ms,
        memory_limit_mb=problem.memory_limit_mb,
        reference_code=problem.reference_code,
        intent_rubric=problem.intent_rubric.model_dump(),
        status=status,
        parent_id=parent_id,
        langsmith_trace_id=langsmith_trace_id,
        authoring_meta=authoring_meta,
        embedding=embedding,
        **row_kwargs,
        test_cases=[
            TestCaseRow(
                ordinal=t.ordinal,
                stdin=t.stdin,
                expected_stdout=t.expected_stdout,
                is_sample=t.is_sample,
            )
            for t in problem.test_cases
        ],
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    assert row.id is not None
    return row.id


def update_problem(
    session: Session,
    problem_id: int,
    *,
    fields: dict,
    intent_rubric: IntentRubric | None = None,
    test_cases: list[TestCase] | None = None,
) -> bool:
    """등록된 문제의 부분 수정. test_cases가 주어지면 전체 교체(cascade delete-orphan).

    fields는 ProblemRow의 스칼라 컬럼만(setattr) — 안전 필터는 호출자(스키마)가 책임진다.
    문제가 없으면 False."""
    row = session.get(ProblemRow, problem_id)
    if row is None:
        return False
    for key, val in fields.items():
        setattr(row, key, val)
    if intent_rubric is not None:
        row.intent_rubric = intent_rubric.model_dump()
    if test_cases is not None:
        # delete-orphan cascade가 기존 row 정리. 새 리스트로 통째 교체.
        row.test_cases = [
            TestCaseRow(
                ordinal=t.ordinal,
                stdin=t.stdin,
                expected_stdout=t.expected_stdout,
                is_sample=t.is_sample,
            )
            for t in test_cases
        ]
    session.add(row)
    session.commit()
    return True


def delete_problem(
    session: Session,
    problem_id: int,
    cascade_children: bool = True,
) -> dict[str, int] | None:
    """문제 + 연관 row를 모두 삭제. 단일 트랜잭션, 마지막에 한 번만 commit.

    cascade_children=True이면 parent_id == problem_id인 변형도 재귀 삭제.
    SubmissionRow.problem_id, ProblemRow.parent_id, TutorMessageRow.submission_id 모두
    ORM Relationship으로 선언돼 있지 않아 SQLAlchemy의 unit-of-work가 DELETE 순서를
    추론할 수 없다 (postgres에서 FK violation 발생). 각 코호트 사이에 명시적으로
    `session.flush()`를 발행해 SQL 순서를 강제한다.

    반환:
      {variants, submissions, tutor_messages, test_cases} 누적 카운트.
      대상 문제가 없으면 None.
    """
    counts = {"variants": 0, "submissions": 0, "tutor_messages": 0, "test_cases": 0}

    def _delete_one(pid: int) -> bool:
        row = session.get(ProblemRow, pid)
        if row is None:
            return False

        # 1) 변형(자식) 먼저 — 자식이 자기 코호트별 flush를 끝낸 뒤 돌아온다.
        if cascade_children:
            children = list(
                session.exec(
                    select(ProblemRow).where(ProblemRow.parent_id == pid)
                ).all()
            )
            for c in children:
                if c.id is not None and _delete_one(c.id):
                    counts["variants"] += 1

        # 2) 이 문제의 submissions에 묶인 tutor_messages 먼저
        sub_ids = [
            s.id for s in session.exec(
                select(SubmissionRow).where(SubmissionRow.problem_id == pid)
            ).all() if s.id is not None
        ]
        if sub_ids:
            tms = list(
                session.exec(
                    select(TutorMessageRow).where(
                        TutorMessageRow.submission_id.in_(sub_ids)  # type: ignore[attr-defined]
                    )
                ).all()
            )
            for tm in tms:
                session.delete(tm)
            if tms:
                session.flush()  # DELETE tutor_message 즉시 발행
            counts["tutor_messages"] += len(tms)

        # 3) submissions
        if sub_ids:
            for sid in sub_ids:
                s = session.get(SubmissionRow, sid)
                if s is not None:
                    session.delete(s)
            session.flush()  # DELETE submission 즉시 발행 (tutor_message 다음)
            counts["submissions"] += len(sub_ids)

        # 4) test_cases는 ProblemRow의 cascade="all, delete-orphan"으로 자동
        counts["test_cases"] += len(row.test_cases)

        session.delete(row)
        session.flush()  # DELETE problem(+test_cases) 즉시 발행 → 다음 형제/부모로 진행
        return True

    if not _delete_one(problem_id):
        return None

    session.commit()
    return counts
