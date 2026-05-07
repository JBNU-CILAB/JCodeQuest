from ..schemas import Problem

TUTOR_SYSTEM = """당신은 친절한 알고리즘 튜터입니다. 학생의 제출 코드와 채점 결과를 바탕으로 한국어 코멘트를 작성하세요.

원칙:
1. 정답 코드를 직접 보여주지 말고, 학생이 스스로 깨닫도록 힌트를 주세요.
2. 잘한 점을 먼저 짚고 개선점은 그 다음에. 격려와 구체성을 함께.
3. 채점 결과(verdict, 판사 의견, 테스트 결과)를 그대로 옮기지 말고 학생 눈높이로 풀어 쓰세요.
4. 분량은 4~8문장. 마크다운 헤더 없이 자연 문단 1~2개로.
5. verdict별 톤:
   - AC: 효율·스타일 개선 한 가지를 제안.
   - SUS: "테스트는 통과했지만 의도와 어긋난 점"을 짚되, 정답을 알려주지 말고 다시 시도할 방향만 제시.
   - WA/RE/TLE/MLE: 실패 원인을 추론해 어디부터 의심해야 할지 안내."""


def render_user_message(
    *,
    problem: Problem,
    code: str,
    verdict: str | None,
    votes: list[dict] | None,
    test_results: list[dict],
) -> str:
    r = problem.intent_rubric
    lines: list[str] = []

    lines.append(f"[문제] {problem.title}")
    lines.append(problem.statement.strip())
    lines.append("")

    lines.append("[출제자 의도]")
    lines.append(f"- 접근: {r.expected_approach}")
    lines.append(f"- 복잡도: {r.expected_complexity}")
    lines.append(f"- 핵심 통찰: {r.key_insight}")
    if r.must_handle:
        lines.append(f"- 반드시 처리: {', '.join(r.must_handle)}")
    if r.forbidden_patterns:
        lines.append(f"- 금지 패턴: {', '.join(r.forbidden_patterns)}")
    lines.append("")

    lines.append("[학생 제출 코드]")
    lines.append("```python")
    lines.append(code.rstrip())
    lines.append("```")
    lines.append("")

    if test_results:
        passed = sum(1 for t in test_results if t.get("passed"))
        total = len(test_results)
        lines.append(f"[테스트 결과] {passed}/{total} 통과")
        tc_by_ord = {tc.ordinal: tc for tc in problem.test_cases}
        for t in test_results:
            ord_ = t.get("ordinal")
            status = t.get("status")
            if t.get("passed"):
                lines.append(f"- #{ord_} 통과 ({t.get('elapsed_ms')}ms)")
                continue
            tc = tc_by_ord.get(ord_)
            if status == "OK" and tc is not None:
                lines.append(
                    f"- #{ord_} 실패(WA) — 입력 {tc.stdin!r}, "
                    f"기대 {tc.expected_stdout!r}, 실제 {t.get('actual_stdout')!r}"
                )
            elif status in ("RE", "TLE", "MLE"):
                err = (t.get("error") or "").strip()
                tail = f" — {err[:200]}" if err else ""
                lines.append(f"- #{ord_} {status}{tail}")
            else:
                lines.append(f"- #{ord_} 실패")
        lines.append("")

    if votes:
        lines.append("[판사 의견]")
        for v in votes:
            lines.append(
                f"- {v.get('judge_id')}: {v.get('verdict')} "
                f"(intent_match={v.get('intent_match')}, "
                f"conf={v.get('confidence')}) — {v.get('rationale')}"
            )
        lines.append("")

    lines.append(f"[최종 판정] {verdict or '미판정'}")
    lines.append("")
    lines.append("위 정보를 바탕으로 학생에게 줄 튜터링 코멘트를 작성하세요.")
    return "\n".join(lines)
