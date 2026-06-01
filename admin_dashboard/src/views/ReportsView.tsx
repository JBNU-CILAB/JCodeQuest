import { Suspense, use, useCallback, useEffect, useState } from "react";
import type {
  BugReportCategory,
  BugReportRow,
  BugReportStatus,
  ConnSettings,
} from "../types";
import { adminFetch, fmtDate } from "../api";
import { unwrap, useResource } from "../lib/resource";

interface Props {
  settings: ConnSettings;
}

const STATUSES: { v: "" | BugReportStatus; label: string }[] = [
  { v: "", label: "전체" },
  { v: "open", label: "열림" },
  { v: "in_progress", label: "처리 중" },
  { v: "resolved", label: "해결됨" },
  { v: "rejected", label: "반려" },
];

const CATEGORIES: { v: "" | BugReportCategory; label: string }[] = [
  { v: "", label: "전체" },
  { v: "judging", label: "채점 오류" },
  { v: "statement", label: "문제 오타" },
  { v: "sample", label: "예제 이상" },
  { v: "system", label: "시스템 / UI" },
  { v: "other", label: "기타" },
];

const STATUS_BADGE: Record<BugReportStatus, string> = {
  open: "badge-amber",
  in_progress: "badge-gray",
  resolved: "badge-green",
  rejected: "badge-red",
};

const CATEGORY_LABEL: Record<BugReportCategory, string> = {
  judging: "채점",
  statement: "오타",
  sample: "예제",
  system: "시스템",
  other: "기타",
};

const STATUS_LABEL: Record<BugReportStatus, string> = {
  open: "열림",
  in_progress: "처리 중",
  resolved: "해결됨",
  rejected: "반려",
};

type Filters = { status: "" | BugReportStatus; category: "" | BugReportCategory };
type Query = Filters & { offset: number };

/**
 * Suspense 안에서 use(promise) 로 행 데이터를 읽는다.
 * 부모가 mutation 후 refresh() 하면 이 컴포넌트만 새 데이터로 재렌더된다.
 */
function ReportRows({
  promise,
  onOpen,
  onCount,
}: {
  promise: Promise<BugReportRow[]>;
  onOpen: (row: BugReportRow) => void;
  onCount: (n: number) => void;
}) {
  const rows = use(promise);
  // commit 이후에 부모로 카운트 전파(페이지네이션 버튼 enable/disable 용).
  useEffect(() => { onCount(rows.length); }, [rows.length, onCount]);
  if (rows.length === 0) {
    return (
      <tr className="empty-row">
        <td colSpan={8}>제보 없음</td>
      </tr>
    );
  }
  return (
    <>
      {rows.map((r) => (
        <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => onOpen(r)}>
          <td className="num">{r.id}</td>
          <td>
            {r.user_display_name ?? `#${r.user_id}`}
            <span className="hint">#{r.user_id}</span>
          </td>
          <td>
            {r.problem_id == null ? (
              <span className="text-muted">—</span>
            ) : (
              <>
                {r.problem_title ?? `#${r.problem_id}`}
                <span className="hint">#{r.problem_id}</span>
              </>
            )}
          </td>
          <td>
            <span className="badge badge-gray">{CATEGORY_LABEL[r.category]}</span>
          </td>
          <td>{r.title}</td>
          <td>
            <span className={`badge ${STATUS_BADGE[r.status]}`}>{STATUS_LABEL[r.status]}</span>
          </td>
          <td className="num">{r.code_snapshot ? `${r.code_snapshot.length}B` : "—"}</td>
          <td className="text-sm text-muted">{fmtDate(r.created_at)}</td>
        </tr>
      ))}
    </>
  );
}

function RowsFallback() {
  return (
    <tr className="empty-row">
      <td colSpan={8}><span className="spinner" style={{ width: 12, height: 12 }} /> 불러오는 중…</td>
    </tr>
  );
}

export default function ReportsView({ settings }: Props) {
  const [error, setError] = useState("");
  const [limit] = useState(50);
  const [rowCount, setRowCount] = useState(0);

  // 입력 폼 상태 (필터 셀렉트). "검색" 누르기 전에는 query 에 반영되지 않는다.
  const [filters, setFilters] = useState<Filters>({ status: "", category: "" });
  // 실제로 GET 에 들어가는 쿼리 — 이 값이 바뀌어야 새 fetch 가 발생한다.
  const [query, setQuery] = useState<Query>({ status: "", category: "", offset: 0 });

  // 상세 패널 — admin_notes / status는 백엔드 row와 별도로 편집 버퍼.
  const [detail, setDetail] = useState<BugReportRow | null>(null);
  const [editStatus, setEditStatus] = useState<BugReportStatus>("open");
  const [editNotes, setEditNotes] = useState("");
  const [savingDetail, setSavingDetail] = useState(false);

  const fetchReports = useCallback(async (): Promise<BugReportRow[]> => {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(query.offset) });
    if (query.status) qs.set("status", query.status);
    if (query.category) qs.set("category", query.category);
    return unwrap<BugReportRow[]>(await adminFetch(`/api/reports?${qs}`, settings));
  }, [settings, limit, query]);
  const { promise: reportsPromise, refresh, isPending } = useResource(fetchReports, [settings, query]);

  function runSearch() {
    setError("");
    setQuery({ ...filters, offset: 0 });
  }
  function gotoOffset(off: number) {
    setQuery((q) => ({ ...q, offset: Math.max(0, off) }));
  }

  function openDetail(row: BugReportRow) {
    setDetail(row);
    setEditStatus(row.status);
    setEditNotes(row.admin_notes ?? "");
  }

  function closeDetail() {
    setDetail(null);
    setSavingDetail(false);
  }

  async function saveDetail() {
    if (!detail) return;
    setSavingDetail(true);
    try {
      const r = await adminFetch(`/api/reports/${detail.id}`, settings, {
        method: "PATCH",
        body: JSON.stringify({ status: editStatus, admin_notes: editNotes }),
      });
      if (!r.ok) {
        const t = await r.text();
        setError(`[${r.status}] ${t.slice(0, 200)}`);
        return;
      }
      const updated: BugReportRow = await r.json();
      setDetail(updated);
      refresh(); // 목록은 use(promise) 가 새 데이터로 알아서 그린다
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setSavingDetail(false);
    }
  }

  async function deleteReport(rid: number) {
    if (!confirm(`제보 #${rid}를 삭제할까요? (되돌릴 수 없음)`)) return;
    try {
      const r = await adminFetch(`/api/reports/${rid}`, settings, { method: "DELETE" });
      if (!r.ok) {
        const t = await r.text();
        setError(`[${r.status}] ${t.slice(0, 200)}`);
        return;
      }
      if (detail?.id === rid) closeDetail();
      refresh();
    } catch (err: unknown) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="main reports">
      <div className="page-head">
        <h1>버그 제보</h1>
        <span className="sub">상태 토글 · 내부 메모 · 코드 스냅샷으로 재현</span>
      </div>

      <div className="card">
        <div className="filter-row">
          <div className="field narrow">
            <label>상태</label>
            <select
              value={filters.status}
              onChange={(e) =>
                setFilters((p) => ({ ...p, status: e.target.value as "" | BugReportStatus }))
              }
            >
              {STATUSES.map((s) => (
                <option key={s.v} value={s.v}>{s.label}</option>
              ))}
            </select>
          </div>
          <div className="field narrow">
            <label>카테고리</label>
            <select
              value={filters.category}
              onChange={(e) =>
                setFilters((p) => ({ ...p, category: e.target.value as "" | BugReportCategory }))
              }
            >
              {CATEGORIES.map((c) => (
                <option key={c.v} value={c.v}>{c.label}</option>
              ))}
            </select>
          </div>
          <div className="field" style={{ maxWidth: 100, marginTop: "auto" }}>
            <button className="btn btn-primary" onClick={runSearch} disabled={isPending}>
              {isPending ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "검색"}
            </button>
          </div>
        </div>
        {error && <div className="output-panel err">{error}</div>}
      </div>

      <div className="card" style={{ padding: 0, position: "relative" }}>
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
              <tr>
                <th>ID</th><th>유저</th><th>문제</th><th>분류</th>
                <th>제목</th><th>상태</th><th>코드</th><th>제보 시각</th>
              </tr>
            </thead>
            <tbody>
              <Suspense fallback={<RowsFallback />}>
                <ReportRows promise={reportsPromise} onOpen={openDetail} onCount={setRowCount} />
              </Suspense>
            </tbody>
          </table>
        </div>
        {rowCount > 0 && (
          <div className="pagination" style={{ padding: "10px 16px" }}>
            <span className="page-info">offset {query.offset} · {rowCount}건</span>
            <button
              className="btn btn-ghost btn-sm"
              disabled={query.offset === 0 || isPending}
              onClick={() => gotoOffset(query.offset - limit)}
            >
              ← 이전
            </button>
            <button
              className="btn btn-ghost btn-sm"
              disabled={rowCount < limit || isPending}
              onClick={() => gotoOffset(query.offset + limit)}
            >
              다음 →
            </button>
          </div>
        )}
      </div>

      {detail && (
        <>
          <div className="overlay-bg" onClick={closeDetail} />
          <div className="detail-panel">
            <div className="detail-header">
              <div className="detail-title">
                제보 #{detail.id}{" "}
                <span className={`badge ${STATUS_BADGE[detail.status]}`}>
                  {STATUS_LABEL[detail.status]}
                </span>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={closeDetail}>✕</button>
            </div>
            <div className="detail-body">
              <div className="kv-grid">
                <span className="kv-key">유저</span>
                <span className="kv-val">
                  {detail.user_display_name ?? "(unknown)"}
                  <span className="hint">#{detail.user_id}</span>
                </span>
                <span className="kv-key">문제</span>
                <span className="kv-val">
                  {detail.problem_id == null ? (
                    <span className="text-muted">—</span>
                  ) : (
                    <>
                      {detail.problem_title ?? "(deleted)"}
                      <span className="hint">#{detail.problem_id}</span>
                    </>
                  )}
                </span>
                <span className="kv-key">분류</span>
                <span className="kv-val">{CATEGORY_LABEL[detail.category]}</span>
                <span className="kv-key">제보</span>
                <span className="kv-val text-mono text-sm">{fmtDate(detail.created_at)}</span>
                <span className="kv-key">수정</span>
                <span className="kv-val text-mono text-sm">{fmtDate(detail.updated_at)}</span>
              </div>

              <div className="divider" style={{ margin: "12px 0" }} />

              <div className="field mb-12">
                <label>제목</label>
                <div style={{ fontWeight: 600 }}>{detail.title}</div>
              </div>

              <div className="field mb-12">
                <label>본문</label>
                <pre className="code-block" style={{ whiteSpace: "pre-wrap", fontFamily: "inherit" }}>
                  {detail.body}
                </pre>
              </div>

              {detail.code_snapshot && (
                <details open>
                  <summary>▸ 첨부 코드 ({detail.code_snapshot.length} bytes)</summary>
                  <pre className="code-block">{detail.code_snapshot}</pre>
                </details>
              )}

              <div className="divider" style={{ margin: "12px 0" }} />

              <div className="field mb-12">
                <label>상태 변경</label>
                <select
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value as BugReportStatus)}
                >
                  {STATUSES.filter((s) => s.v !== "").map((s) => (
                    <option key={s.v} value={s.v}>{s.label}</option>
                  ))}
                </select>
              </div>

              <div className="field mb-12">
                <label>내부 메모 (사용자에게 비공개)</label>
                <textarea
                  value={editNotes}
                  onChange={(e) => setEditNotes(e.target.value)}
                  rows={4}
                  placeholder="처리 메모, 재현 결과 등"
                />
              </div>

              <div className="row">
                <button className="btn btn-primary" onClick={saveDetail} disabled={savingDetail}>
                  {savingDetail ? (
                    <span className="spinner" style={{ width: 12, height: 12 }} />
                  ) : (
                    "저장"
                  )}
                </button>
                <button className="btn btn-danger" onClick={() => deleteReport(detail.id)}>
                  삭제
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
