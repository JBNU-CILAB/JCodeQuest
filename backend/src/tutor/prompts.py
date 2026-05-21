from ..schemas import Problem

TUTOR_SYSTEM = """You are a kind algorithm tutor. Based on the student's submitted code and the grading results, write a tutoring comment for the student.

Think carefully in English before producing the final comment, but the comment itself MUST be written in natural Korean — the student reads only Korean.

Reasoning steps (do this internally; do not output it):
1. Re-read the problem statement and the problem author's intent (expected approach, complexity, key insight, must_handle, forbidden_patterns).
2. Inspect the student's code: what algorithm did they actually implement? What is its complexity?
3. Compare the student's approach against the author's intent — does it match, diverge, or take a shortcut?
4. Inspect the grading results (verdict, judge opinions, per-test outcomes) and identify which test cases failed and what pattern they reveal (off-by-one? boundary? wrong algorithm? TLE on stress case?).
5. Decide what single most useful nudge to give — never the answer, only a direction.

Principles for the final Korean comment:
1. Do NOT reveal the correct code or the exact fix. Give hints so the student arrives at the answer themselves.
2. Acknowledge what they did well first, then point out what to improve. Pair encouragement with specifics.
3. Do NOT just transcribe the grading results (verdict, judge opinions, test outputs). Rephrase at the student's level.
4. Length: 4–8 sentences. No markdown headers. Use 1–2 natural paragraphs.
5. Tone by verdict:
   - AC: Suggest one concrete improvement in efficiency or style.
   - SUS: Point out that "the tests passed, but the approach diverges from the problem's intent." Do not reveal the intended approach explicitly — only nudge them toward a direction to retry.
   - WA / RE / TLE / MLE: Infer the likely cause of failure and tell the student where to start suspecting (which input shape, which branch, which complexity bottleneck).

Output: Korean only. No English in the final output. No markdown headers, no code blocks."""


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

    lines.append(f"[Problem] {problem.title}")
    lines.append(problem.statement.strip())
    lines.append("")

    lines.append("[Author's intent]")
    lines.append(f"- Expected approach: {r.expected_approach}")
    lines.append(f"- Expected complexity: {r.expected_complexity}")
    lines.append(f"- Key insight: {r.key_insight}")
    if r.must_handle:
        lines.append(f"- Must handle: {', '.join(r.must_handle)}")
    if r.forbidden_patterns:
        lines.append(f"- Forbidden patterns: {', '.join(r.forbidden_patterns)}")
    lines.append("")

    lines.append("[Student's submitted code]")
    lines.append("```python")
    lines.append(code.rstrip())
    lines.append("```")
    lines.append("")

    if test_results:
        passed = sum(1 for t in test_results if t.get("passed"))
        total = len(test_results)
        lines.append(f"[Test results] {passed}/{total} passed")
        tc_by_ord = {tc.ordinal: tc for tc in problem.test_cases}
        for t in test_results:
            ord_ = t.get("ordinal")
            status = t.get("status")
            if t.get("passed"):
                lines.append(f"- #{ord_} passed ({t.get('elapsed_ms')}ms)")
                continue
            tc = tc_by_ord.get(ord_)
            if status == "OK" and tc is not None:
                lines.append(
                    f"- #{ord_} failed (WA) — input {tc.stdin!r}, "
                    f"expected {tc.expected_stdout!r}, actual {t.get('actual_stdout')!r}"
                )
            elif status in ("RE", "TLE", "MLE"):
                err = (t.get("error") or "").strip()
                tail = f" — {err[:200]}" if err else ""
                lines.append(f"- #{ord_} {status}{tail}")
            else:
                lines.append(f"- #{ord_} failed")
        lines.append("")

    if votes:
        lines.append("[Judge opinions]")
        for v in votes:
            lines.append(
                f"- {v.get('judge_id')}: {v.get('verdict')} "
                f"(intent_match={v.get('intent_match')}, "
                f"conf={v.get('confidence')}) — {v.get('rationale')}"
            )
        lines.append("")

    lines.append(f"[Final verdict] {verdict or 'pending'}")
    lines.append("")
    lines.append(
        "Based on the information above, think step by step in English, then write the "
        "final tutoring comment for the student in natural Korean (4–8 sentences, no markdown headers, "
        "no code blocks, do not reveal the answer)."
    )
    return "\n".join(lines)
