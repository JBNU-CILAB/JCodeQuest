import { Suspense, use, useCallback, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Cell, LabelList, ResponsiveContainer,
} from "recharts";
import type { ConnSettings, PlagiarismFragment, PlagiarismPair, PlagiarismStatus } from "../types";
import { plagFetch, fmtDate } from "../api";
import ProblemPicker, { loadProblemsList } from "../components/ProblemPicker";
import { unwrap, useResource } from "../lib/resource";

// 조정자가 매긴 4축 점수(0~100). defense는 '독립 가능성'(높을수록 표절 아님)이라 초록,
// 나머지는 의심 방향이라 호박/빨강/보라. agent_debate.scores에서 존재하는 축만 그린다.
const SCORE_AXES: { key: "structural" | "semantic" | "defense" | "adjudicator"; label: string; fill: string }[] = [
  { key: "structural",  label: "구조 유사도",     fill: "#d97706" },
  { key: "semantic",    label: "베낀 정황",       fill: "#dc2626" },
  { key: "defense",     label: "독립 가능성",     fill: "#16a34a" },
  { key: "adjudicator", label: "종합 표절 확신",  fill: "#7c3aed" },
];

function AgentScoreChart({ scores }: { scores?: Record<string, number | undefined> }) {
  if (!scores) return null;
  const data = SCORE_AXES
    .filter((a) => typeof scores[a.key] === "number")
    .map((a) => ({ name: a.label, value: Math.max(0, Math.min(100, scores[a.key] as number)), fill: a.fill }));
  if (data.length === 0) return null;
  return (
    <div style={{ marginTop: 8 }}>
      <div className="text-sm" style={{ marginBottom: 4 }}>요소별 점수 (조정자 채점, 0~100)</div>
      <ResponsiveContainer width="100%" height={data.length * 34 + 16}>
        <BarChart layout="vertical" data={data} margin={{ top: 2, right: 36, bottom: 2, left: 8 }}>
          <XAxis type="number" domain={[0, 100]} hide />
          <YAxis type="category" dataKey="name" width={92} tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
          <Bar dataKey="value" radius={[0, 3, 3, 0]} barSize={16} isAnimationActive={false}>
            {data.map((d, i) => <Cell key={i} fill={d.fill} />)}
            <LabelList dataKey="value" position="right" style={{ fontSize: 11, fill: "#475569" }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="text-sm text-muted" style={{ fontSize: 11 }}>
        ※ ‘독립 가능성’만 높을수록 표절 아님(초록), 나머지는 높을수록 의심.
      </div>
    </div>
  );
}

interface Props { settings: ConnSettings }

const STATUSES: { v: "" | PlagiarismStatus; label: string }[] = [
  { v: "", label: "전체" },
  { v: "open", label: "검토 대기" },
  { v: "in_progress", label: "검토 중" },
  { v: "confirmed", label: "표절 확정" },
  { v: "dismissed", label: "무혐의" },
];

const STATUS_BADGE: Record<PlagiarismStatus, string> = {
  open: "badge-amber",
  in_progress: "badge-gray",
  confirmed: "badge-red",
  dismissed: "badge-green",
};
const STATUS_LABEL: Record<PlagiarismStatus, string> = {
  open: "검토 대기", in_progress: "검토 중", confirmed: "표절 확정", dismissed: "무혐의",
};

// fragments에서 한쪽(a 또는 b) 매칭 라인 번호 집합 추출.
// Dolos는 a_lines/b_lines를 [startLine, endLine] 범위(1-indexed)로 보낸다 — 끝점만 칠하면
// 사이 라인이 비어 보이고 끝점이 빈 줄에 떨어지면 개행만 노랗게 보이는 착시가 생기므로
// 범위를 펼쳐서 그 안의 모든 라인을 후보로 둔다. 단 빈 줄(공백만)은 토큰이 0이라
// 매칭 의미가 없으니 형광에서 제외 — 의미 있는 라인만 강조.
// winnow 폴백이면 fragments가 비어 plain 렌더.
function matchedLines(
  code: string | null | undefined,
  fragments: PlagiarismFragment[] | undefined,
  side: "a" | "b",
): Set<number> {
  const out = new Set<number>();
  if (!code) return out;
  const lines = code.split("\n");
  for (const f of fragments ?? []) {
    const arr = side === "a" ? f.a_lines : f.b_lines;
    const nums = arr.filter((n): n is number => typeof n === "number" && n > 0);
    if (nums.length === 0) continue;
    const start = Math.max(1, Math.min(...nums));
    const end   = Math.min(lines.length, Math.max(...nums));
    for (let ln = start; ln <= end; ln++) {
      const text = lines[ln - 1];
      if (text != null && text.trim() !== "") out.add(ln);
    }
  }
  return out;
}

// 라인 단위로 코드를 렌더하면서 fragments에 포함된 라인만 형광 노란색 배경으로 마킹.
// 라인 번호 거터 + 텍스트 영역, 빈 라인은 nbsp로 높이 유지.
function HighlightedCode({ code, matched }: { code: string | null | undefined; matched: Set<number> }) {
  if (code == null) {
    return <pre className="code-block">(로딩 중 또는 없음)</pre>;
  }
  const lines = code.split("\n");
  return (
    <pre className="code-block code-block-marked">
      {lines.map((line, i) => {
        const lineNum = i + 1;
        const hit = matched.has(lineNum);
        return (
          <div key={i} className={hit ? "code-line match" : "code-line"}>
            <span className="code-line-num">{lineNum}</span>
            <span className="code-line-text">{line || " "}</span>
          </div>
        );
      })}
    </pre>
  );
}

function simTone(s: number): string {
  return s >= 0.85 ? "badge-red" : s >= 0.7 ? "badge-amber" : "badge-gray";
}

/**
 * Suspense 경계 안에서 `use(promise)` 로 의심 쌍 목록을 읽어 테이블 본문만 렌더.
 * 부모가 mutation 후 refresh() 하면 새 Promise 가 들어와 이 컴포넌트만 다시 그려진다.
 */
function PairRows({
  promise,
  onOpen,
}: {
  promise: Promise<PlagiarismPair[]>;
  onOpen: (row: PlagiarismPair) => void;
}) {
  const rows = use(promise);
  if (rows.length === 0) {
    return (
      <tr className="empty-row">
        <td colSpan={7}>의심 쌍 없음 — 위 드롭다운에서 문제를 골라 표절 검사를 실행하세요.</td>
      </tr>
    );
  }
  return (
    <>
      {rows.map((r) => (
        <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => onOpen(r)}>
          <td className="num">{r.id}</td>
          <td><span className={`badge ${simTone(r.similarity)}`}>{(r.similarity * 100).toFixed(1)}%</span></td>
          <td>
            {r.user_a_name ?? `#${r.user_a_id}`} ↔ {r.user_b_name ?? `#${r.user_b_id}`}
          </td>
          <td>{r.problem_title ?? `#${r.problem_id}`}<span className="hint">#{r.problem_id}</span></td>
          <td className="num text-sm text-muted">{r.longest_fragment} / {r.total_overlap}</td>
          <td><span className={`badge ${STATUS_BADGE[r.status]}`}>{STATUS_LABEL[r.status]}</span></td>
          <td className="text-sm text-muted">{fmtDate(r.created_at)}</td>
        </tr>
      ))}
    </>
  );
}

function PairRowsFallback() {
  return (
    <tr className="empty-row">
      <td colSpan={7}><span className="spinner" style={{ width: 12, height: 12 }} /> 의심 쌍 불러오는 중…</td>
    </tr>
  );
}

export default function PlagiarismView({ settings }: Props) {
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | PlagiarismStatus>("");
  const [problemId, setProblemId] = useState("");
  const [triggerId, setTriggerId] = useState("");
  const [running, setRunning] = useState(false);

  const [detail, setDetail] = useState<PlagiarismPair | null>(null);
  const [editStatus, setEditStatus] = useState<PlagiarismStatus>("open");
  const [editNotes, setEditNotes] = useState("");
  const [saving, setSaving] = useState(false);

  // 의심 쌍 목록 — useResource 가 Promise 를 들고 있고, 자식이 use(promise) 로 읽는다.
  // statusFilter / problemId 가 바뀌면 새 Promise 가 자동 생성되어 다시 fetch.
  // refresh() 는 동일 deps 라도 version 을 올려 강제 재fetch (mutation 직후 호출).
  const fetchPairs = useCallback(async (): Promise<PlagiarismPair[]> => {
    const qs = new URLSearchParams({ limit: "200" });
    if (statusFilter) qs.set("status", statusFilter);
    if (problemId.trim()) qs.set("problem_id", problemId.trim());
    return unwrap<PlagiarismPair[]>(await plagFetch(`/api/plagiarism/pairs?${qs}`, settings));
  }, [settings, statusFilter, problemId]);
  const { promise: pairsPromise, refresh: refreshPairs, isPending } = useResource(
    fetchPairs,
    [settings, statusFilter, problemId],
  );

  async function runCheck() {
    setRunning(true); setError(""); setInfo("");
    try {
      // "all" sentinel → 전체 문제 일괄 실행. 백엔드 API가 problem_id 단건만 받기 때문에
      // 프론트에서 fan-out한다. 각 POST는 백그라운드 잡을 시작만 시키므로 빠르게 끝남.
      if (triggerId === "all") {
        let problems: { id: number; title: string }[];
        try {
          problems = await loadProblemsList(settings, false);
        } catch (e) {
          setError(`문제 목록을 불러오지 못했어요: ${(e as Error).message}`);
          return;
        }
        if (problems.length === 0) { setError("등록된 문제가 없습니다"); return; }
        const results = await Promise.allSettled(
          problems.map((p) =>
            plagFetch("/api/plagiarism/runs", settings, {
              method: "POST", body: JSON.stringify({ problem_id: p.id }),
            }).then(async (r) => {
              if (!r.ok) throw new Error(`#${p.id} [${r.status}] ${(await r.text()).slice(0, 120)}`);
              return p.id;
            }),
          ),
        );
        const ok = results.filter((x) => x.status === "fulfilled").length;
        const failed = results.length - ok;
        setInfo(
          `전체 ${problems.length}개 문제 표절 검사를 시작했어요 (성공 ${ok}${failed > 0 ? ` · 실패 ${failed}` : ""}). ` +
          `결과가 도착하면 목록이 자동으로 갱신됩니다.`,
        );
        if (failed > 0) {
          const firstErr = results.find((x): x is PromiseRejectedResult => x.status === "rejected");
          if (firstErr) setError(String(firstErr.reason).slice(0, 200));
        }
      } else {
        const pid = parseInt(triggerId.trim(), 10);
        if (!Number.isFinite(pid)) { setError("문제를 선택하세요"); return; }
        const r = await plagFetch("/api/plagiarism/runs", settings, {
          method: "POST", body: JSON.stringify({ problem_id: pid }),
        });
        if (!r.ok) { setError(`[${r.status}] ${(await r.text()).slice(0, 200)}`); return; }
        setInfo(`문제 #${pid} 표절 검사를 시작했어요. 결과가 도착하면 목록이 자동으로 갱신됩니다.`);
      }
      // 검사가 백그라운드라 즉시 결과가 없을 수 있어 1회 즉시 + 5초 후 한 번 더 refresh.
      refreshPairs();
      window.setTimeout(refreshPairs, 5000);
    } catch (e) { setError((e as Error).message); }
    finally { setRunning(false); }
  }

  async function openDetail(row: PlagiarismPair) {
    setEditStatus(row.status); setEditNotes(row.admin_notes ?? "");
    setDetail(row); // 우선 목록 데이터로 열고, 코드 포함 상세를 덮어씀
    try {
      const r = await plagFetch(`/api/plagiarism/pairs/${row.id}`, settings);
      if (r.ok) setDetail(await r.json());
    } catch { /* 목록 데이터로 폴백 */ }
  }

  async function saveDetail() {
    if (!detail) return;
    setSaving(true);
    try {
      const r = await plagFetch(`/api/plagiarism/pairs/${detail.id}`, settings, {
        method: "PATCH", body: JSON.stringify({ status: editStatus, admin_notes: editNotes }),
      });
      if (!r.ok) { setError(`[${r.status}] ${(await r.text()).slice(0, 200)}`); return; }
      // 상세 패널은 즉시 반영, 목록은 refresh() 가 알아서 다시 그린다(use 패턴).
      setDetail((d) => (d ? { ...d, status: editStatus, admin_notes: editNotes } : d));
      refreshPairs();
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }

  return (
    <div className="main reports">
      <div className="page-head">
        <h1>표절 검토</h1>
        <span className="sub">
          신규 AC 마다 자동 검사(Dolos + 에이전트) · 결과는 검토 큐로 적재 · 운영자가 최종 판단
        </span>
      </div>

      <div className="card">
        <div className="filter-row">
          <div className="field narrow">
            <label>상태</label>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as "" | PlagiarismStatus)}>
              {STATUSES.map((s) => <option key={s.v} value={s.v}>{s.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label>문제 필터</label>
            <ProblemPicker
              settings={settings}
              value={problemId}
              onChange={setProblemId}
              placeholder="전체"
            />
          </div>
          <div className="field" style={{ maxWidth: 100, marginTop: "auto" }}>
            <button className="btn btn-outline" onClick={refreshPairs} disabled={isPending}>
              {isPending ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "조회"}
            </button>
          </div>
          {/* 강제 재검사 — 자동 검사가 누락된 경우(전송 실패/백필)에만 사용. 의도적으로 우측 끝에
              outline 스타일로 격하. 평소엔 클릭할 일 없음. */}
          <div className="field" style={{ marginLeft: "auto" }}>
            <label className="text-muted text-sm">강제 재검사</label>
            <ProblemPicker
              settings={settings}
              value={triggerId}
              onChange={setTriggerId}
              placeholder="— 문제 선택 —"
              extraOptions={[{ value: "all", label: "전체" }]}
            />
          </div>
          <div className="field" style={{ maxWidth: 110, marginTop: "auto" }}>
            <button className="btn btn-outline" onClick={runCheck} disabled={running}>
              {running ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "재검사 실행"}
            </button>
          </div>
        </div>
        {info && <div className="output-panel">{info}</div>}
        {error && <div className="output-panel err">{error}</div>}
      </div>

      <div className="card" style={{ padding: 0, position: "relative" }}>
        {/* 자동 갱신 중일 때 우상단에 옅은 인디케이터 — 깜빡임 없이 새 데이터로 부드럽게 교체된다 */}
        {isPending && (
          <span
            className="text-xs text-muted"
            style={{ position: "absolute", top: 8, right: 12, opacity: 0.7 }}
          >
            <span className="spinner" style={{ width: 10, height: 10 }} /> 갱신 중…
          </span>
        )}
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>ID</th><th>유사도</th><th>유저 A ↔ 유저 B</th><th>문제</th><th>최장/중복</th><th>상태</th><th>생성</th></tr>
            </thead>
            <tbody>
              <Suspense fallback={<PairRowsFallback />}>
                <PairRows promise={pairsPromise} onOpen={openDetail} />
              </Suspense>
            </tbody>
          </table>
        </div>
      </div>

      {detail && (
        <>
          <div className="overlay-bg" onClick={() => setDetail(null)} />
          <div className="detail-panel" style={{ width: 720 }}>
            <div className="detail-header">
              <div className="detail-title">
                의심 쌍 #{detail.id} <span className={`badge ${simTone(detail.similarity)}`}>{(detail.similarity * 100).toFixed(1)}%</span>{" "}
                <span className={`badge ${STATUS_BADGE[detail.status]}`}>{STATUS_LABEL[detail.status]}</span>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setDetail(null)}>✕</button>
            </div>
            <div className="detail-body">
              <div className="kv-grid">
                <span className="kv-key">유저 A</span>
                <span className="kv-val">{detail.user_a_name ?? "(unknown)"}<span className="hint">sub #{detail.submission_a_id}</span></span>
                <span className="kv-key">유저 B</span>
                <span className="kv-val">{detail.user_b_name ?? "(unknown)"}<span className="hint">sub #{detail.submission_b_id}</span></span>
                <span className="kv-key">문제</span>
                <span className="kv-val">{detail.problem_title ?? `#${detail.problem_id}`}</span>
                <span className="kv-key">유사도 / 최장 / 중복</span>
                <span className="kv-val text-mono">{(detail.similarity * 100).toFixed(1)}% · {detail.longest_fragment} · {detail.total_overlap}</span>
                <span className="kv-key">매칭 블록</span>
                <span className="kv-val text-mono text-sm">{detail.fragments?.length ?? 0}개</span>
              </div>

              {detail.agent_verdict && (
                <div className="output-panel" style={{ marginTop: 10 }}>
                  <b>에이전트 판정(권고):</b> {detail.agent_verdict}
                  {detail.agent_confidence != null && ` · 신뢰도 ${(detail.agent_confidence * 100).toFixed(0)}%`}
                  {detail.agent_rationale && <div className="text-sm text-muted" style={{ marginTop: 4 }}>{detail.agent_rationale}</div>}
                  <AgentScoreChart scores={detail.agent_debate?.scores} />
                  {detail.agent_debate && (detail.agent_debate.structural || detail.agent_debate.semantic || detail.agent_debate.defense) && (
                    <details style={{ marginTop: 6 }}>
                      <summary className="text-sm">▸ 4역할 토론</summary>
                      <div className="text-sm text-muted" style={{ marginTop: 4, lineHeight: 1.6 }}>
                        {detail.agent_debate.structural && <div><b>구조 분석가:</b> {detail.agent_debate.structural}</div>}
                        {detail.agent_debate.semantic && <div><b>의미 검토자:</b> {detail.agent_debate.semantic}</div>}
                        {detail.agent_debate.defense && <div><b>반론:</b> {detail.agent_debate.defense}</div>}
                      </div>
                    </details>
                  )}
                </div>
              )}

              <div className="divider" style={{ margin: "12px 0" }} />
              {(() => {
                const linesA = matchedLines(detail.code_a, detail.fragments, "a");
                const linesB = matchedLines(detail.code_b, detail.fragments, "b");
                const hasMarks = linesA.size + linesB.size > 0;
                return (
                  <div className="plag-codes">
                    <div>
                      <div className="prob-io-label">
                        코드 A · {detail.user_a_name ?? `#${detail.user_a_id}`}
                        {linesA.size > 0 && (
                          <span className="badge badge-amber" style={{ marginLeft: 6 }}>
                            중복 {linesA.size}줄
                          </span>
                        )}
                      </div>
                      <HighlightedCode code={detail.code_a} matched={linesA} />
                    </div>
                    <div>
                      <div className="prob-io-label">
                        코드 B · {detail.user_b_name ?? `#${detail.user_b_id}`}
                        {linesB.size > 0 && (
                          <span className="badge badge-amber" style={{ marginLeft: 6 }}>
                            중복 {linesB.size}줄
                          </span>
                        )}
                      </div>
                      <HighlightedCode code={detail.code_b} matched={linesB} />
                    </div>
                    {!hasMarks && (detail.fragments?.length ?? 0) === 0 && (
                      <div className="text-sm text-muted" style={{ marginTop: 4, gridColumn: "1 / -1" }}>
                        ※ 라인 매칭 정보 없음 — winnow 폴백 엔진은 fragments를 채우지 않으므로 형광펜이 표시되지 않습니다.
                      </div>
                    )}
                  </div>
                );
              })()}

              <div className="divider" style={{ margin: "12px 0" }} />
              <div className="field mb-12">
                <label>판정 (사람 최종 결정)</label>
                <select value={editStatus} onChange={(e) => setEditStatus(e.target.value as PlagiarismStatus)}>
                  {STATUSES.filter((s) => s.v !== "").map((s) => <option key={s.v} value={s.v}>{s.label}</option>)}
                </select>
              </div>
              <div className="field mb-12">
                <label>검토 메모 (내부)</label>
                <textarea value={editNotes} onChange={(e) => setEditNotes(e.target.value)} rows={3} placeholder="동일 구조·동일 주석 오타 등 근거" />
              </div>
              <div className="row">
                <button className="btn btn-primary" onClick={saveDetail} disabled={saving}>
                  {saving ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "저장"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
