import { useState, useCallback } from "react";
import type { ConnSettings, SubmissionRow, SubmissionDetail } from "../types";
import { judgeFetch, fmtDate } from "../api";
import VerdictBadge from "../components/VerdictBadge";

interface Props { settings: ConnSettings }

const VERDICTS = ["", "AC", "SUS", "WA", "RE", "TLE", "MLE"];
const STATUSES = ["", "done", "running", "failed"];

export default function SubmissionsView({ settings }: Props) {
  const [rows, setRows] = useState<SubmissionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const [limit] = useState(50);
  const [pageInfo, setPageInfo] = useState("");
  const [error, setError] = useState("");

  const [filters, setFilters] = useState({
    user_id: "", problem_id: "", verdict: "", status: "",
  });

  const upd = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setFilters((p) => ({ ...p, [k]: e.target.value }));

  const load = useCallback(async (newOffset = 0) => {
    setLoading(true);
    setError("");
    const qs = new URLSearchParams({ limit: String(limit), offset: String(newOffset) });
    if (filters.user_id)    qs.set("user_id",    filters.user_id);
    if (filters.problem_id) qs.set("problem_id", filters.problem_id);
    if (filters.verdict)    qs.set("verdict",    filters.verdict);
    if (filters.status)     qs.set("status",     filters.status);

    try {
      const r = await judgeFetch(`/api/submissions?${qs}`, settings);
      if (!r.ok) {
        const t = await r.text();
        setError(`[${r.status}] ${t.slice(0, 200)}`);
        return;
      }
      const data: SubmissionRow[] = await r.json();
      setRows(data);
      setOffset(newOffset);
      setPageInfo(`offset ${newOffset} · ${data.length}행`);
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [filters, limit, settings]);

  async function showDetail(sid: number) {
    setDetailLoading(true);
    setDetail(null);
    try {
      const r = await judgeFetch(`/api/submissions/${sid}`, settings);
      if (!r.ok) {
        const t = await r.text();
        setDetail({ id: sid } as SubmissionDetail);
        setError(`[${r.status}] ${t.slice(0, 200)}`);
        return;
      }
      setDetail(await r.json());
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setDetailLoading(false);
    }
  }

  return (
    <div>
      <p className="card-desc mb-12">
        제출 행을 필터·페이지네이션으로 조회합니다. 행 클릭 시 코드·votes·test_results를 확인할 수 있습니다.
      </p>

      <div className="card">
        <div className="filter-row">
          <div className="field narrow">
            <label>User ID</label>
            <input type="number" value={filters.user_id} onChange={upd("user_id")} placeholder="전체" />
          </div>
          <div className="field narrow">
            <label>Problem ID</label>
            <input type="number" value={filters.problem_id} onChange={upd("problem_id")} placeholder="전체" />
          </div>
          <div className="field narrow">
            <label>Verdict</label>
            <select value={filters.verdict} onChange={upd("verdict")}>
              {VERDICTS.map((v) => <option key={v} value={v}>{v || "전체"}</option>)}
            </select>
          </div>
          <div className="field narrow">
            <label>Status</label>
            <select value={filters.status} onChange={upd("status")}>
              {STATUSES.map((s) => <option key={s} value={s}>{s || "전체"}</option>)}
            </select>
          </div>
          <div className="field" style={{ maxWidth: 100, marginTop: "auto" }}>
            <button className="btn btn-primary" onClick={() => load(0)} disabled={loading}>
              {loading ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "검색"}
            </button>
          </div>
        </div>
        {error && <div className="output-panel err">{error}</div>}
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th><th>유저</th><th>문제</th><th>Verdict</th>
                <th>Status</th><th>ms</th><th>점수</th><th>제출 시각</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr className="empty-row"><td colSpan={8}>결과 없음 — 검색을 눌러주세요</td></tr>
              ) : rows.map((s) => (
                <tr key={s.id} style={{ cursor: "pointer" }} onClick={() => showDetail(s.id)}>
                  <td className="num">{s.id}</td>
                  <td>
                    {s.user_display_name ?? `#${s.user_id}`}
                    <span className="hint">#{s.user_id}</span>
                  </td>
                  <td>
                    {s.problem_title ?? `#${s.problem_id}`}
                    <span className="hint">#{s.problem_id}</span>
                  </td>
                  <td><VerdictBadge verdict={s.final_verdict} /></td>
                  <td><span className="badge badge-gray">{s.status}</span></td>
                  <td className="num">{s.max_elapsed_ms ?? "—"}</td>
                  <td className="num">{s.points_awarded ?? "—"}</td>
                  <td className="text-sm text-muted">{fmtDate(s.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length > 0 && (
          <div className="pagination" style={{ padding: "10px 16px" }}>
            <span className="page-info">{pageInfo}</span>
            <button className="btn btn-ghost btn-sm" disabled={offset === 0} onClick={() => load(Math.max(0, offset - limit))}>← 이전</button>
            <button className="btn btn-ghost btn-sm" disabled={rows.length < limit} onClick={() => load(offset + limit)}>다음 →</button>
          </div>
        )}
      </div>

      {/* Detail panel */}
      {(detail || detailLoading) && (
        <>
          <div className="overlay-bg" onClick={() => setDetail(null)} />
          <div className="detail-panel">
            <div className="detail-header">
              <div className="detail-title">
                {detailLoading
                  ? <><span className="spinner" style={{ width: 16, height: 16 }} /> 로딩 중...</>
                  : <>제출 #{detail?.id} <VerdictBadge verdict={detail?.final_verdict} /></>
                }
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setDetail(null)}>✕</button>
            </div>
            {detail && !detailLoading && (
              <div className="detail-body">
                <div className="kv-grid">
                  <span className="kv-key">user</span>
                  <span className="kv-val">{detail.user_display_name ?? "(unknown)"}<span className="hint">#{detail.user_id}</span></span>
                  <span className="kv-key">problem</span>
                  <span className="kv-val">{detail.problem_title ?? "(deleted)"}<span className="hint">#{detail.problem_id}</span></span>
                  <span className="kv-key">status</span>
                  <span className="kv-val"><span className="badge badge-gray">{detail.status}</span></span>
                  <span className="kv-key">mode</span>
                  <span className="kv-val">{detail.mode ?? "—"}</span>
                  <span className="kv-key">elapsed ms</span>
                  <span className="kv-val text-mono">{detail.max_elapsed_ms ?? "—"}</span>
                  <span className="kv-key">peak mem KB</span>
                  <span className="kv-val text-mono">{detail.peak_memory_kb ?? "—"}</span>
                  <span className="kv-key">points</span>
                  <span className="kv-val text-mono">{detail.points_awarded ?? "—"}</span>
                  <span className="kv-key">created</span>
                  <span className="kv-val text-mono text-sm">{fmtDate(detail.created_at)}</span>
                </div>

                <details open>
                  <summary>▸ 코드 ({(detail.code ?? "").length} bytes)</summary>
                  <pre className="code-block">{detail.code}</pre>
                </details>

                <details>
                  <summary>▸ test_results ({(detail.test_results ?? []).length}건)</summary>
                  <pre className="json-block">{JSON.stringify(detail.test_results, null, 2)}</pre>
                </details>

                <details>
                  <summary>▸ ensemble votes</summary>
                  <pre className="json-block">{JSON.stringify(detail.votes, null, 2)}</pre>
                </details>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
