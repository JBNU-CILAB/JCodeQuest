import { Suspense, use, useCallback, useEffect, useMemo, useState } from "react";
import type { ConnSettings, ProblemRow, TestCase, ProblemDetail } from "../types";
import { adminFetch, fmtDate } from "../api";
import AuthoringMetaPanel from "../components/AuthoringMetaPanel";
import ComparisonTab from "../components/ComparisonTab";
import { ProblemStatsTab } from "./StatsView";
import { invalidateProblemPickerCache } from "../components/ProblemPicker";
import { unwrap, useResource } from "../lib/resource";

interface Props { settings: ConnSettings }

// 4탭 단일 바: 관리(원본 등록/원본 목록) + 분석(문제별 통계/원본-변형 비교).
// '변형 출제'는 제거됨 — 변형 트리거는 파이프라인 runs 화면에서 수행.
type Tab = "create" | "list" | "stats" | "comparison";

const TAB_SUBTITLES: Record<Tab, string> = {
  create:     "원본 문제 등록",
  list:       "원본 목록 + 출제 메타 조회",
  stats:      "문제별 채점 통계 · LLM-as-Judge 앙상블 동향 (행 클릭 시 상세 차트)",
  comparison: "원본-변형 4축 점수 (hallucination / intent / difficulty / judge)",
};
type ProblemFilter = "all" | "variant" | "original";

/* ────────────────────────────────────────────────────────── */
function CreateTab({ settings }: Props) {
  const [form, setForm] = useState({
    title: "", statement: "", category: "구현", level: "bronze",
    points: "100", time_limit_ms: "2000", memory_limit_mb: "256",
    reference_code: "", tags: "",
  });
  const [testCases, setTestCases] = useState<TestCase[]>([{ stdin: "", expected_stdout: "", is_sample: true }]);
  const [output, setOutput] = useState<{ kind: "ok" | "err" | ""; msg: string }>({ kind: "", msg: "" });
  const [submitting, setSubmitting] = useState(false);

  const upd = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value }));

  const updateTC = (i: number, k: keyof TestCase, v: string | boolean) =>
    setTestCases((prev) => prev.map((tc, idx) => idx === i ? { ...tc, [k]: v } : tc));

  const addTC = () => setTestCases((p) => [...p, { stdin: "", expected_stdout: "", is_sample: false }]);
  const removeTC = (i: number) => setTestCases((p) => p.filter((_, idx) => idx !== i));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setOutput({ kind: "", msg: "등록 중..." });
    try {
      const payload = {
        ...form,
        points: Number(form.points),
        time_limit_ms: Number(form.time_limit_ms),
        memory_limit_mb: Number(form.memory_limit_mb),
        tags: form.tags ? form.tags.split(",").map((t) => t.trim()).filter(Boolean) : [],
        test_cases: testCases.filter((tc) => tc.stdin || tc.expected_stdout),
      };
      const r = await adminFetch("/api/problems", settings, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const body = await r.text();
      let pretty = body;
      try { pretty = JSON.stringify(JSON.parse(body), null, 2); } catch {}
      setOutput({ kind: r.ok ? "ok" : "err", msg: `[${r.status}]\n\n${pretty}` });
      if (r.ok) {
        // 다른 뷰의 ProblemPicker 가 최신 목록을 받도록 캐시 무효화.
        invalidateProblemPickerCache();
      }
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: `네트워크 오류: ${(err as Error).message}` });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <div className="card">
        <div className="card-title"><span className="card-icon">◈</span> 기본 정보</div>
        <div className="form-grid">
          <div className="field span-2">
            <label>제목</label>
            <input type="text" value={form.title} onChange={upd("title")} required placeholder="문제 제목" />
          </div>
          <div className="field">
            <label>카테고리</label>
            <input type="text" value={form.category} onChange={upd("category")} placeholder="구현, 정렬, DP..." />
          </div>
          <div className="field">
            <label>난이도</label>
            <select value={form.level} onChange={upd("level")}>
              {["bronze","silver","gold"].map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>점수</label>
            <input type="number" value={form.points} onChange={upd("points")} min={1} />
          </div>
          <div className="field">
            <label>시간 제한 (ms)</label>
            <input type="number" value={form.time_limit_ms} onChange={upd("time_limit_ms")} min={100} />
          </div>
          <div className="field">
            <label>메모리 제한 (MB)</label>
            <input type="number" value={form.memory_limit_mb} onChange={upd("memory_limit_mb")} min={16} />
          </div>
          <div className="field">
            <label>태그 (쉼표 구분)</label>
            <input type="text" value={form.tags} onChange={upd("tags")} placeholder="배열, 반복문" />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-title"><span className="card-icon">◈</span> 문제 설명</div>
        <div className="field">
          <label>문제 본문 (Markdown)</label>
          <textarea className="code" value={form.statement} onChange={upd("statement")} rows={8} placeholder="문제 설명을 입력..." required />
        </div>
      </div>

      <div className="card">
        <div className="card-title"><span className="card-icon">◈</span> 참조 코드</div>
        <div className="field">
          <label>정답 코드</label>
          <textarea className="code" value={form.reference_code} onChange={upd("reference_code")} rows={10} placeholder="# Python 정답 코드" required />
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <span className="card-icon">◈</span> 테스트 케이스
          <span className="spacer" />
          <button type="button" className="btn btn-ghost btn-sm" onClick={addTC}>+ 추가</button>
        </div>
        <div className="tc-list">
          {testCases.map((tc, i) => (
            <div key={i} className="tc-row">
              <div className="field">
                <div className="tc-num">INPUT #{i + 1}</div>
                <textarea value={tc.stdin} onChange={(e) => updateTC(i, "stdin", e.target.value)} placeholder="stdin" />
              </div>
              <div className="field">
                <div className="tc-num">EXPECTED #{i + 1}</div>
                <textarea value={tc.expected_stdout} onChange={(e) => updateTC(i, "expected_stdout", e.target.value)} placeholder="stdout (비우면 reference_code로 autofill)" />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingTop: 20 }}>
                <label className="checkbox-row">
                  <input type="checkbox" checked={!!tc.is_sample} onChange={(e) => updateTC(i, "is_sample", e.target.checked)} />
                  <span>샘플</span>
                </label>
                {testCases.length > 1 && (
                  <button type="button" className="btn btn-danger btn-sm" onClick={() => removeTC(i)}>✕</button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", gap: 10 }}>
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? <><span className="spinner" />등록 중...</> : "문제 등록"}
        </button>
      </div>

      {output.msg && (
        <div className={`output-panel ${output.kind}`}>{output.msg}</div>
      )}
    </form>
  );
}

/* ────────────────────────────────────────────────────────── */

const LEVEL_COLOR: Record<string, string> = {
  bronze: "badge-amber", silver: "badge-gray", gold: "badge-amber",
  platinum: "badge-blue", diamond: "badge-purple",
};

/** Suspense 안에서 use(promise) 로 문제 목록을 읽어 행만 렌더. 부모 mutation 후 refresh() → 이 컴포넌트만 재렌더. */
function ProblemRows({
  promise,
  filter,
  onOpen,
  onDelete,
  onList,
}: {
  promise: Promise<ProblemRow[]>;
  filter: ProblemFilter;
  onOpen: (pid: number) => void;
  onDelete: (pid: number, title: string) => void;
  onList: (list: ProblemRow[]) => void;
}) {
  const all = use(promise);
  // 부모(parent_title 조회용 캐시 등)가 목록을 참조할 수 있도록 commit 후 전파.
  useEffect(() => { onList(all); }, [all, onList]);
  const visible =
    filter === "variant" ? all.filter((p) => p.parent_id != null) :
    filter === "original" ? all.filter((p) => p.parent_id == null) :
    all;
  if (visible.length === 0) {
    return (
      <tr className="empty-row">
        <td colSpan={9}>
          {all.length === 0
            ? "문제 없음"
            : filter === "variant" ? "변형 문제 없음" : "원본 문제 없음"}
        </td>
      </tr>
    );
  }
  return (
    <>
      {visible.map((p) => (
        <tr key={p.id} style={{ cursor: "pointer" }} onClick={() => onOpen(p.id)}>
          <td className="num">{p.id}</td>
          <td>{p.title}</td>
          <td><span className="badge badge-blue">{p.category}</span></td>
          <td><span className={`badge ${LEVEL_COLOR[p.level] ?? "badge-gray"}`}>{p.level}</span></td>
          <td className="num">{p.points}</td>
          <td className="num">{p.time_limit_ms}</td>
          <td className="num">{p.parent_id ?? "—"}</td>
          <td className="text-sm text-muted">{fmtDate(p.created_at).slice(0, 10)}</td>
          <td className="actions">
            <button
              className="btn btn-danger btn-sm"
              onClick={(e) => { e.stopPropagation(); onDelete(p.id, p.title); }}
            >
              삭제
            </button>
          </td>
        </tr>
      ))}
    </>
  );
}

function ProblemRowsFallback() {
  return (
    <tr className="empty-row">
      <td colSpan={9}><span className="spinner" style={{ width: 12, height: 12 }} /> 불러오는 중…</td>
    </tr>
  );
}

/** 세그먼트 카운터 — Promise 결과의 길이로 계산. Suspense 안에서 use 로 읽는다. */
function ProblemCounts({
  promise,
  filter,
  setFilter,
}: {
  promise: Promise<ProblemRow[]>;
  filter: ProblemFilter;
  setFilter: (f: ProblemFilter) => void;
}) {
  const all = use(promise);
  const variant = all.filter((p) => p.parent_id != null).length;
  const counts = { all: all.length, variant, original: all.length - variant };
  return (
    <>
      {([
        ["all",      "전체 문제", counts.all],
        ["variant",  "변형 문제만", counts.variant],
        ["original", "원본 문제만", counts.original],
      ] as [ProblemFilter, string, number][]).map(([key, label, n]) => (
        <button
          key={key}
          role="tab"
          aria-selected={filter === key}
          className={`seg-btn${filter === key ? " active" : ""}`}
          onClick={() => setFilter(key)}
        >
          {label}
          <span className="seg-count">{n}</span>
        </button>
      ))}
    </>
  );
}

function ListTab({ settings }: Props) {
  const [filter, setFilter] = useState<ProblemFilter>("all");
  const [output, setOutput] = useState<{ kind: "ok" | "err" | ""; msg: string }>({ kind: "", msg: "" });
  const [detail, setDetail] = useState<ProblemDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  // 클릭된 문제가 변형이면 원본 제목을 채워 슬라이드오버 헤더에 노출.
  const [parentTitle, setParentTitle] = useState<string | null>(null);
  // ProblemRows 가 commit 시점에 전달해주는 목록 캐시(parent_title 룩업용).
  const [problemsCache, setProblemsCache] = useState<ProblemRow[]>([]);

  // 문제 목록 — useResource 로 promise 관리. 자식이 use(promise) 로 읽는다.
  // 원본+변형을 한 번에 받아 클라이언트에서 필터 전환.
  const fetchProblems = useCallback(async (): Promise<ProblemRow[]> => {
    return unwrap<ProblemRow[]>(await adminFetch(`/api/problems?originals_only=false`, settings));
  }, [settings]);
  const { promise: problemsPromise, refresh, isPending } = useResource(fetchProblems, [settings]);

  async function showDetail(pid: number) {
    setDetailLoading(true);
    setDetail(null);
    setParentTitle(null);  // 새 detail 열 때 이전 parentTitle 잔존 방지
    try {
      const r = await adminFetch(`/api/problems/${pid}`, settings);
      if (!r.ok) {
        const t = await r.text();
        setOutput({ kind: "err", msg: `[${r.status}] ${t.slice(0, 200)}` });
        setDetailLoading(false);
        return;
      }
      setDetail(await r.json());
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: (err as Error).message });
    } finally {
      setDetailLoading(false);
    }
  }

  // 변형이면 원본 제목을 채운다: 로컬 problems 캐시 우선, 없으면 /api/problems/{parent}로 fetch.
  useEffect(() => {
    const parentId = detail?.parent_id ?? null;
    if (parentId == null) { setParentTitle(null); return; }
    const cached = problemsCache.find((p) => p.id === parentId);
    if (cached?.title) { setParentTitle(cached.title); return; }
    let cancelled = false;
    (async () => {
      try {
        const r = await adminFetch(`/api/problems/${parentId}`, settings);
        if (!r.ok || cancelled) return;
        const d = await r.json();
        if (!cancelled) setParentTitle(typeof d?.title === "string" ? d.title : null);
      } catch { /* 헤더 부가정보 — 실패해도 무시 */ }
    })();
    return () => { cancelled = true; };
  }, [detail?.parent_id, problemsCache, settings]);

  async function deleteProblem(pid: number, title: string) {
    if (!confirm(`문제 #${pid} "${title}"을(를) 삭제할까요?\n변형 문제도 함께 삭제됩니다.`)) return;
    setOutput({ kind: "", msg: `DELETE /api/problems/${pid} ...` });
    try {
      const r = await adminFetch(`/api/problems/${pid}?cascade_children=true`, settings, { method: "DELETE" });
      const body = await r.json().catch(() => ({}));
      if (r.ok) {
        setOutput({ kind: "ok", msg: `✓ 삭제 완료 — id=${pid}` });
        invalidateProblemPickerCache();  // 다른 뷰의 드롭다운도 다음 마운트 시 새 목록 받도록
        refresh();                        // 이 뷰의 테이블은 use(promise) 가 새 데이터로 알아서 그린다
      } else {
        setOutput({ kind: "err", msg: `[${r.status}] ${JSON.stringify(body, null, 2)}` });
      }
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: (err as Error).message });
    }
  }

  // ProblemRows 가 commit 시점에 호출하는 콜백 — 항등성 유지를 위해 메모이즈.
  const handleList = useCallback((list: ProblemRow[]) => setProblemsCache(list), []);

  return (
    <div>
      <div className="card">
        <div className="filter-row">
          <div className="seg" role="tablist" aria-label="문제 유형 필터">
            <Suspense fallback={<span className="text-muted text-sm">로딩 중…</span>}>
              <ProblemCounts promise={problemsPromise} filter={filter} setFilter={setFilter} />
            </Suspense>
          </div>
          <button className="btn btn-primary btn-sm" onClick={refresh} disabled={isPending}>
            {isPending ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "↻"}&nbsp;새로고침
          </button>
        </div>
        <div className="card-desc" style={{ marginTop: 8 }}>
          행을 클릭하면 RAG 과정과 LLM-as-a-Judge 지표(품질·변별력·비교·신규성)를 확인할 수 있습니다.
          출제 메타는 변형 문제에만 채워집니다 — "변형 문제만"으로 좁혀 조회하세요.
        </div>
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
                <th>ID</th><th>제목</th><th>카테고리</th><th>난이도</th>
                <th>점수</th><th>시간 (ms)</th><th>상위 ID</th><th>등록일</th><th></th>
              </tr>
            </thead>
            <tbody>
              <Suspense fallback={<ProblemRowsFallback />}>
                <ProblemRows
                  promise={problemsPromise}
                  filter={filter}
                  onOpen={showDetail}
                  onDelete={deleteProblem}
                  onList={handleList}
                />
              </Suspense>
            </tbody>
          </table>
        </div>
      </div>

      {output.msg && <div className={`output-panel ${output.kind}`}>{output.msg}</div>}

      <AuthoringMetaPanel
        detail={detail}
        loading={detailLoading}
        onClose={() => setDetail(null)}
        settings={settings}
        parentTitle={parentTitle}
        onUpdated={(updated) => {
          setDetail(updated);
          // 목록의 표시값(제목/카테고리/난이도/점수/시간)도 즉시 반영
          setProblemsCache((prev) =>
            prev.map((p) =>
              p.id === updated.id
                ? {
                    ...p,
                    title: updated.title,
                    category: updated.category,
                    level: updated.level,
                    points: updated.points,
                    time_limit_ms: updated.time_limit_ms,
                  }
                : p,
            ),
          );
        }}
      />
    </div>
  );
}

/* ────────────────────────────────────────────────────────── */
export default function ProblemsView({ settings }: Props) {
  const [tab, setTab] = useState<Tab>("create");
  // useMemo to silence unused — kept for future tab-specific subtitle theming
  const subtitle = useMemo(() => TAB_SUBTITLES[tab], [tab]);

  return (
    <div className="main problems">
      <div className="page-head">
        <h1>문제 · 통계</h1>
        <span className="sub">{subtitle}</span>
      </div>

      <div className="tabs">
        {/* 관리(CRUD) 그룹 */}
        {([
          ["create",  "원본 등록"],
          ["list",    "원본 목록"],
        ] as [Tab, string][]).map(([t, label]) => (
          <button key={t} className={`tab-btn${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>
            {label}
          </button>
        ))}
        {/* 분석 그룹과 시각 구분 (탭 바 안의 얇은 세퍼레이터) */}
        <span className="tab-sep" aria-hidden="true" />
        {([
          ["stats",      "문제별 통계"],
          ["comparison", "원본-변형 비교"],
        ] as [Tab, string][]).map(([t, label]) => (
          <button key={t} className={`tab-btn${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "create"     && <CreateTab        settings={settings} />}
      {tab === "list"       && <ListTab          settings={settings} />}
      {tab === "stats"      && <ProblemStatsTab  settings={settings} />}
      {tab === "comparison" && <ComparisonTab    settings={settings} />}
    </div>
  );
}
