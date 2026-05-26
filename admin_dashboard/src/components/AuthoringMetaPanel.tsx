import type { ProblemDetail, AuthoringMeta } from "../types";
import { fmtDate } from "../api";
import VerdictBadge from "./VerdictBadge";

interface Props {
  detail: ProblemDetail | null;
  loading: boolean;
  onClose: () => void;
}

/* 점수 막대 — axis="hal"은 낮을수록 좋음(환각/유사도), "pos"는 높을수록 좋음(품질/의도). */
function scoreClass(axis: "hal" | "pos", v: number | null | undefined): string {
  if (v == null) return "score-mid";
  if (axis === "hal") return v < 0.3 ? "score-good" : v < 0.6 ? "score-mid" : "score-bad";
  return v > 0.7 ? "score-good" : v > 0.4 ? "score-mid" : "score-bad";
}

function ScoreBar({ axis, v }: { axis: "hal" | "pos"; v?: number | null }) {
  if (v == null) return <span className="text-dim">—</span>;
  return (
    <div className={`score-bar-wrap ${scoreClass(axis, v)}`}>
      <div className="score-bar"><div className="score-bar-fill" style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%` }} /></div>
      <span className="score-val">{v.toFixed(3)}</span>
    </div>
  );
}

function PassBadge({ passed }: { passed?: boolean | null }) {
  if (passed == null) return <span className="badge badge-gray">미실행</span>;
  return passed
    ? <span className="badge badge-green">PASS</span>
    : <span className="badge badge-red">FAIL</span>;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="card-title" style={{ marginBottom: 8 }}><span className="card-icon">◈</span> {children}</div>;
}

/* RAG 과정 — retrieve_exemplars가 고른 모범문제 + novelty(밀어내기) */
function RagSection({ meta }: { meta: AuthoringMeta }) {
  const rag = meta.rag;
  const nov = meta.novelty;
  const hasRag = rag != null;
  const hasNov = nov != null && (nov.max_similarity != null || nov.attempts != null);
  if (!hasRag && !hasNov) {
    return (
      <div className="card">
        <SectionTitle>RAG 과정</SectionTitle>
        <div className="text-sm text-muted">
          이 문제엔 RAG 메타가 없습니다. (RAG exemplar 영속화 이전에 생성된 변형이거나 수기 등록 원본)
        </div>
      </div>
    );
  }
  return (
    <div className="card">
      <SectionTitle>RAG 과정 (exemplar 검색 + 신규성)</SectionTitle>

      {hasRag && (
        <>
          <div className="kv-grid">
            <span className="kv-key">enabled</span>
            <span className="kv-val">
              {rag!.enabled
                ? <span className="badge badge-green">ON</span>
                : <span className="badge badge-gray">OFF</span>}
            </span>
            <span className="kv-key">top_k / λ</span>
            <span className="kv-val text-mono">{rag!.top_k ?? "—"} / {rag!.mmr_lambda ?? "—"}</span>
            <span className="kv-key">level_window</span>
            <span className="kv-val text-mono">±{rag!.level_window ?? "—"}</span>
            <span className="kv-key">min_judge_score</span>
            <span className="kv-val text-mono">{rag!.min_judge_score ?? "—"}</span>
          </div>

          <div className="text-sm text-muted" style={{ margin: "8px 0 4px" }}>
            참고한 모범문제 (grounding exemplars)
          </div>
          {rag!.exemplars && rag!.exemplars.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {rag!.exemplars.map((e, i) => (
                <div key={i} className="badge badge-blue" style={{ justifyContent: "flex-start" }}>
                  #{e.id ?? "?"} · {e.title ?? "(제목 없음)"}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-dim">
              {rag!.enabled
                ? "선정된 exemplar 없음 — 빈 코퍼스/폴백(예시 없이 생성)"
                : "RAG 비활성 — 시드 블록으로 생성"}
            </div>
          )}
        </>
      )}

      {hasNov && (
        <>
          <div className="text-sm text-muted" style={{ margin: "12px 0 4px" }}>
            신규성 검사 (임베딩 cosine — 낮을수록 형제와 다름)
          </div>
          <div className="kv-grid">
            <span className="kv-key">max_similarity</span>
            <span className="kv-val"><ScoreBar axis="hal" v={nov!.max_similarity} /></span>
            <span className="kv-key">closest sibling</span>
            <span className="kv-val text-mono">{nov!.closest_id != null ? `#${nov!.closest_id}` : "—"}</span>
            <span className="kv-key">draft 재시도</span>
            <span className="kv-val text-mono">{nov!.attempts ?? "—"}회</span>
          </div>
        </>
      )}
    </div>
  );
}

/* LLM-as-a-Judge — 품질 심사 + 변별력 + 비교 + 솔버 */
function JudgeSection({ meta }: { meta: AuthoringMeta }) {
  const disc = meta.discrimination;
  const comp = meta.comparison;
  return (
    <div className="card">
      <SectionTitle>LLM-as-a-Judge 지표</SectionTitle>

      {/* 품질 심사 (3-judge) */}
      <div className="text-sm text-muted" style={{ marginBottom: 4 }}>
        품질 심사 (3-judge · 중앙값) <PassBadge passed={meta.judge_passed} />
      </div>
      <div className="kv-grid">
        <span className="kv-key">judge_score</span>
        <span className="kv-val"><ScoreBar axis="pos" v={meta.judge_score} /></span>
        {(meta.judge_scores ?? []).map((s, i) => (
          <span key={`js-${i}`} style={{ display: "contents" }}>
            <span className="kv-key">판사 {i + 1}</span>
            <span className="kv-val"><ScoreBar axis="pos" v={s} /></span>
          </span>
        ))}
      </div>
      {meta.judge_rationale && (
        <details>
          <summary>▸ judge rationale</summary>
          <pre className="json-block" style={{ whiteSpace: "pre-wrap" }}>{meta.judge_rationale}</pre>
        </details>
      )}
      {meta.judge_issues && meta.judge_issues.length > 0 && (
        <details>
          <summary>▸ 지적된 품질 이슈 ({meta.judge_issues.length})</summary>
          <ul style={{ margin: "4px 0 0 16px", fontSize: 12, color: "var(--text-muted)" }}>
            {meta.judge_issues.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </details>
      )}

      {/* 변별력 (attack) */}
      <div className="text-sm text-muted" style={{ margin: "14px 0 4px" }}>
        테스트 변별력 (결함 풀이 공격) <PassBadge passed={disc?.passed} />
      </div>
      <div className="kv-grid">
        <span className="kv-key">discrim score</span>
        <span className="kv-val"><ScoreBar axis="pos" v={disc?.score} /></span>
      </div>
      {disc?.attacks && disc.attacks.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 4 }}>
          <table>
            <thead><tr><th>전략</th><th>판정</th><th>걸러냄?</th><th>설명</th></tr></thead>
            <tbody>
              {disc.attacks.map((a, i) => (
                <tr key={i}>
                  <td className="text-mono text-sm">{a.strategy ?? "—"}</td>
                  <td><VerdictBadge verdict={a.verdict} /></td>
                  <td>{a.rejected
                    ? <span className="badge badge-green">✓ 걸러냄</span>
                    : <span className="badge badge-red">✗ 통과시킴</span>}</td>
                  <td className="text-sm text-muted">{a.rationale ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 원본-변형 비교 */}
      <div className="text-sm text-muted" style={{ margin: "14px 0 4px" }}>
        원본-변형 비교 (단일 judge) <PassBadge passed={comp?.passed} />
      </div>
      <div className="kv-grid">
        <span className="kv-key">hallucination ↓</span>
        <span className="kv-val"><ScoreBar axis="hal" v={comp?.hallucination_score} /></span>
        <span className="kv-key">intent sim ↑</span>
        <span className="kv-val"><ScoreBar axis="pos" v={comp?.intent_similarity} /></span>
        <span className="kv-key">difficulty sim</span>
        <span className="kv-val"><ScoreBar axis="pos" v={comp?.difficulty_similarity} /></span>
      </div>
      {comp?.error
        ? <div className="text-sm" style={{ color: "var(--red)" }}>error: {comp.error}</div>
        : comp?.rationale && (
          <details>
            <summary>▸ comparison rationale</summary>
            <pre className="json-block" style={{ whiteSpace: "pre-wrap" }}>{comp.rationale}</pre>
          </details>
        )}

      {/* 솔버 */}
      <div className="text-sm text-muted" style={{ margin: "14px 0 4px" }}>
        솔버 (LLM 직접 풀이) <PassBadge passed={meta.solver_passed} />
      </div>
      {meta.solver_results && meta.solver_results.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead><tr><th>모델</th><th>판정</th><th>설명</th></tr></thead>
            <tbody>
              {meta.solver_results.map((s, i) => (
                <tr key={i}>
                  <td className="text-mono text-sm">{s.judge_id ?? "—"}</td>
                  <td><VerdictBadge verdict={s.verdict} /></td>
                  <td className="text-sm text-muted">{s.rationale ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <div className="text-sm text-dim">솔버 결과 없음</div>}
    </div>
  );
}

export default function AuthoringMetaPanel({ detail, loading, onClose }: Props) {
  if (!detail && !loading) return null;
  const meta = detail?.authoring_meta ?? null;
  const isManual = meta?.source === "manual";

  return (
    <>
      <div className="overlay-bg" onClick={onClose} />
      <div className="detail-panel">
        <div className="detail-header">
          <div className="detail-title">
            {loading
              ? <><span className="spinner" style={{ width: 16, height: 16 }} /> 로딩 중...</>
              : <>문제 #{detail?.id} · {detail?.title}</>}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>

        {detail && !loading && (
          <div className="detail-body">
            <div className="kv-grid">
              <span className="kv-key">상태</span>
              <span className="kv-val"><span className="badge badge-gray">{detail.status}</span></span>
              <span className="kv-key">원본(parent)</span>
              <span className="kv-val text-mono">{detail.parent_id != null ? `#${detail.parent_id}` : "— (원본)"}</span>
              <span className="kv-key">카테고리/난이도</span>
              <span className="kv-val">
                <span className="badge badge-blue">{detail.category}</span>{" "}
                <span className="badge badge-amber">{detail.level}</span>
              </span>
              <span className="kv-key">점수/시간/메모리</span>
              <span className="kv-val text-mono">{detail.points}점 · {detail.time_limit_ms}ms · {detail.memory_limit_mb}MB</span>
              {meta?.candidate_index != null && (
                <>
                  <span className="kv-key">candidate idx</span>
                  <span className="kv-val text-mono">{meta.candidate_index}</span>
                </>
              )}
              {meta?.issued_iso_week && (
                <>
                  <span className="kv-key">출제 주차</span>
                  <span className="kv-val text-mono">{meta.issued_iso_week}</span>
                </>
              )}
              <span className="kv-key">생성일</span>
              <span className="kv-val text-mono text-sm">{fmtDate(detail.created_at ?? undefined)}</span>
              {detail.langsmith_trace_id && (
                <>
                  <span className="kv-key">trace_id</span>
                  <span className="kv-val text-mono text-sm">{detail.langsmith_trace_id}</span>
                </>
              )}
            </div>

            {isManual ? (
              <div className="output-panel">
                수기 등록 원본 — 출제 파이프라인 메타(RAG/Judge)가 없습니다.
              </div>
            ) : !meta ? (
              <div className="output-panel">
                authoring_meta가 비어 있습니다. (변형이 아니거나 메타 저장 이전 생성분)
              </div>
            ) : (
              <>
                <RagSection meta={meta} />
                <JudgeSection meta={meta} />
                <details>
                  <summary>▸ raw authoring_meta</summary>
                  <pre className="json-block">{JSON.stringify(meta, null, 2)}</pre>
                </details>
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
}
