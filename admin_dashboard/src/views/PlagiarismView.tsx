import { useCallback, useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Cell, LabelList, ResponsiveContainer,
} from "recharts";
import type { ConnSettings, PlagiarismPair, PlagiarismStatus } from "../types";
import { plagFetch, fmtDate } from "../api";

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

function simTone(s: number): string {
  return s >= 0.85 ? "badge-red" : s >= 0.7 ? "badge-amber" : "badge-gray";
}

export default function PlagiarismView({ settings }: Props) {
  const [rows, setRows] = useState<PlagiarismPair[]>([]);
  const [loading, setLoading] = useState(false);
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

  const load = useCallback(async () => {
    setLoading(true); setError("");
    const qs = new URLSearchParams({ limit: "200" });
    if (statusFilter) qs.set("status", statusFilter);
    if (problemId.trim()) qs.set("problem_id", problemId.trim());
    try {
      const r = await plagFetch(`/api/plagiarism/pairs?${qs}`, settings);
      if (!r.ok) { setError(`[${r.status}] ${(await r.text()).slice(0, 200)}`); return; }
      setRows(await r.json());
    } catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, [settings, statusFilter, problemId]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  async function runCheck() {
    const pid = parseInt(triggerId.trim(), 10);
    if (!Number.isFinite(pid)) { setError("문제 ID를 입력하세요"); return; }
    setRunning(true); setError(""); setInfo("");
    try {
      const r = await plagFetch("/api/plagiarism/runs", settings, {
        method: "POST", body: JSON.stringify({ problem_id: pid }),
      });
      if (!r.ok) { setError(`[${r.status}] ${(await r.text()).slice(0, 200)}`); return; }
      setInfo(`문제 #${pid} 표절 검사를 시작했어요. 잠시 후 새로고침하면 결과가 보입니다.`);
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
      setRows((prev) => prev.map((x) => (x.id === detail.id ? { ...x, status: editStatus, admin_notes: editNotes } : x)));
      setDetail((d) => (d ? { ...d, status: editStatus, admin_notes: editNotes } : d));
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }

  return (
    <div className="main reports">
      <div className="page-head">
        <h1>표절 검토</h1>
        <span className="sub">Dolos 구조 유사도로 의심 쌍을 추출 · 사람이 최종 판단</span>
      </div>

      <div className="card">
        <div className="filter-row">
          <div className="field narrow">
            <label>표절 검사 실행 (문제 ID)</label>
            <input value={triggerId} onChange={(e) => setTriggerId(e.target.value)} placeholder="예: 3" />
          </div>
          <div className="field" style={{ maxWidth: 140, marginTop: "auto" }}>
            <button className="btn btn-primary" onClick={runCheck} disabled={running}>
              {running ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "표절 검사 실행"}
            </button>
          </div>
          <div className="field narrow">
            <label>상태</label>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as "" | PlagiarismStatus)}>
              {STATUSES.map((s) => <option key={s.v} value={s.v}>{s.label}</option>)}
            </select>
          </div>
          <div className="field narrow">
            <label>문제 ID 필터</label>
            <input value={problemId} onChange={(e) => setProblemId(e.target.value)} placeholder="전체" />
          </div>
          <div className="field" style={{ maxWidth: 100, marginTop: "auto" }}>
            <button className="btn btn-outline" onClick={load} disabled={loading}>
              {loading ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "조회"}
            </button>
          </div>
        </div>
        {info && <div className="output-panel">{info}</div>}
        {error && <div className="output-panel err">{error}</div>}
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>ID</th><th>유사도</th><th>유저 A ↔ 유저 B</th><th>문제</th><th>최장/중복</th><th>상태</th><th>생성</th></tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr className="empty-row"><td colSpan={7}>의심 쌍 없음 — 문제 ID로 표절 검사를 실행하세요.</td></tr>
              ) : rows.map((r) => (
                <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => openDetail(r)}>
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
              <div className="plag-codes">
                <div>
                  <div className="prob-io-label">코드 A · {detail.user_a_name ?? `#${detail.user_a_id}`}</div>
                  <pre className="code-block">{detail.code_a ?? "(로딩 중 또는 없음)"}</pre>
                </div>
                <div>
                  <div className="prob-io-label">코드 B · {detail.user_b_name ?? `#${detail.user_b_id}`}</div>
                  <pre className="code-block">{detail.code_b ?? "(로딩 중 또는 없음)"}</pre>
                </div>
              </div>

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
