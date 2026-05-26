import { useState, useEffect, useRef, useCallback } from "react";
import type { ConnSettings, RunSummaryT, RunDetailT, RunNodeStateT, SpanT, SpansState } from "../types";
import { adminFetch } from "../api";
import { Icon, NodeKindIcon } from "../components/Icons";
import { NODE_DEFS, fmtDuration, fmtTokens, fmtRelTime } from "../runsConfig";

interface Props { settings: ConnSettings }

const EMPTY_STATES: Record<string, RunNodeStateT> = Object.fromEntries(
  NODE_DEFS.map((d) => [d.key, { status: "queued" }])
);

function statusOf(detail: RunDetailT | null, key: string): RunNodeStateT {
  return detail?.node_states?.[key] ?? { status: "queued" };
}

/* ── Runs Sidebar ──────────────────────────────────────────────────────── */
function RunsSidebar({
  runs, selectedId, onSelect, onNew,
}: {
  runs: RunSummaryT[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const [filter, setFilter] = useState<"all" | "failed" | "running" | "done">("all");
  const [search, setSearch] = useState("");

  const filtered = runs.filter((r) => {
    if (filter !== "all" && r.status !== filter) return false;
    if (search) {
      const s = search.toLowerCase();
      return (
        r.id.toLowerCase().includes(s) ||
        (r.problem_title ?? "").toLowerCase().includes(s) ||
        String(r.problem_id ?? "").includes(s)
      );
    }
    return true;
  });

  return (
    <aside className="runs-sidebar">
      <div className="runs-sidebar-head">
        <h3>
          Recent runs <span className="count">{filtered.length}</span>
          <span className="spacer" />
          <button className="btn btn-primary btn-sm" onClick={onNew}>+ 새 run</button>
        </h3>
        <div className="search-box">
          <span className="ico"><Icon.Search /></span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="run / 문제 / id 검색"
          />
        </div>
        <div className="filter-chips">
          {([["all", "전체"], ["failed", "failed"], ["running", "running"], ["done", "done"]] as const).map(
            ([v, label]) => (
              <button
                key={v}
                className={`filter-chip${filter === v ? " active" : ""}`}
                onClick={() => setFilter(v)}
              >{label}</button>
            )
          )}
        </div>
      </div>

      <div className="run-list">
        {filtered.map((r) => (
          <button
            key={r.id}
            className={`run-card${r.id === selectedId ? " active" : ""}`}
            onClick={() => onSelect(r.id)}
          >
            <div className="run-card-head">
              <span className={`pill ${r.status}`} style={{ padding: "2px 7px", fontSize: 10 }}>
                <span className="dot" />{r.status}
              </span>
              <span className="run-card-id">{r.id.slice(0, 12)}…</span>
            </div>
            <div className="run-card-title">
              #{r.problem_id ?? "?"} {r.problem_title ?? "(제목 없음)"}
            </div>
            {r.status === "failed" && r.failed_at_node && (
              <div className="run-card-fail-where">↳ {r.failed_at_node}</div>
            )}
            <div className="run-card-meta">
              <span>{fmtRelTime(r.started_at)}</span>
              <span className="sep">·</span>
              <span>{fmtDuration(r.total_duration_ms)}</span>
              <span className="sep">·</span>
              <span>{r.target_count}개</span>
            </div>
          </button>
        ))}
        {filtered.length === 0 && (
          <div className="empty" style={{ padding: "40px 12px" }}>조건에 맞는 run이 없어요.</div>
        )}
      </div>
    </aside>
  );
}

/* ── Node Card ─────────────────────────────────────────────────────────── */
function NodeCard({
  idx, def, state, selected, onClick,
}: {
  idx: number;
  def: typeof NODE_DEFS[number];
  state: RunNodeStateT;
  selected: boolean;
  onClick: () => void;
}) {
  const isLlm = def.kind === "llm";
  const cands = state.candidate_results ?? [];
  const tokTotal = state.tokens?.total ?? 0;

  return (
    <button
      data-node={def.key}
      className={`node-card ${state.status}${selected ? " selected" : ""}`}
      onClick={onClick}
      type="button"
    >
      {def.side && <span className="badge-side">side-step</span>}
      <div className="node-head">
        <span className="node-idx">{idx + 1}</span>
        <span style={{ color: "var(--muted)", display: "flex", alignItems: "center" }}>
          <NodeKindIcon kind={def.kind} />
        </span>
        <span className="node-name">{def.label}</span>
        <span className="node-pill-slot">
          <span className={`pill ${state.status}`}><span className="dot" />{state.status}</span>
        </span>
      </div>

      <div className="node-metrics">
        <span className="node-metric"><strong>{fmtDuration(state.duration_ms)}</strong></span>
        {!!state.retries && state.retries > 0 && (
          <span className="node-metric" style={{ color: state.status === "failed" ? "var(--st-failed)" : "var(--st-running)" }}>
            ↻ <strong>{state.retries}</strong> retries
          </span>
        )}
        {isLlm && tokTotal > 0 && (
          <span className="node-metric"><strong>{fmtTokens(tokTotal)}</strong> tok</span>
        )}
        {(state.candidates_out != null || state.candidates_in != null) && (
          <span className="node-metric">
            cand <strong>{state.candidates_out ?? "?"}/{state.candidates_in ?? cands.length}</strong>
          </span>
        )}
      </div>

      {cands.length > 0 && (
        <div className="candidates-strip">
          {cands.slice(0, 8).map((c, i) => (
            <span
              key={i}
              className={`cand-dot ${c.status === "pass" ? "passed" : c.status === "warn" ? "warn" : "failed"}`}
              title={`#${c.idx}: ${c.note || c.status}`}
            />
          ))}
          {cands.length > 8 && <span className="cand-count">+{cands.length - 8}</span>}
        </div>
      )}

      {state.error && <div className="node-error">⚠ {state.error.split(".")[0]}</div>}
    </button>
  );
}

/* ── Pipeline Graph ────────────────────────────────────────────────────── */
function PipelineGraph({
  detail, selectedNode, onSelectNode, zoom,
}: {
  detail: RunDetailT | null;
  selectedNode: string | null;
  onSelectNode: (k: string) => void;
  zoom: number;
}) {
  // 실패/선택 노드를 화면 중앙으로 자동 스크롤 — 포렌식 핵심 어포던스.
  useEffect(() => {
    const target = selectedNode || detail?.failed_at_node;
    if (!target) return;
    requestAnimationFrame(() => {
      const el = document.querySelector<HTMLElement>(`[data-node="${target}"]`);
      const wrap = el?.closest<HTMLElement>(".graph-canvas");
      if (!el || !wrap) return;
      const desired = el.offsetLeft - (wrap.clientWidth - el.offsetWidth) / 2;
      wrap.scrollTo({ left: Math.max(0, desired), behavior: "smooth" });
    });
  }, [detail?.id, selectedNode, detail?.failed_at_node]);

  return (
    <div className="graph-stage" style={{ transform: `scale(${zoom})` }}>
      <div className="node-row">
        {NODE_DEFS.map((def, i) => {
          const state = statusOf(detail, def.key);
          const isLast = i === NODE_DEFS.length - 1;
          return (
            <span key={def.key} style={{ display: "contents" }}>
              <NodeCard
                idx={i}
                def={def}
                state={state}
                selected={selectedNode === def.key}
                onClick={() => onSelectNode(def.key)}
              />
              {!isLast && <span className={`arrow ${state.status === "skipped" ? "skipped" : ""}`} />}
            </span>
          );
        })}
      </div>

      <div className="graph-legend">
        <span><span className="cand-dot passed" /> 후보 통과</span>
        <span><span className="cand-dot failed" /> 후보 탈락</span>
        <span><Icon.LLM /> LLM</span>
        <span><Icon.Box /> sandbox</span>
        <span><Icon.DB /> DB I/O</span>
      </div>
    </div>
  );
}

/* ── Node Drawer ───────────────────────────────────────────────────────── */
/* LangSmith span 트리에서 이 노드 서브트리만 추출 — node span(name===nodeKey) + 그 자손.
   재시도로 같은 노드가 여러 번이면 모두 포함. langsmith_tokens.aggregate_node_tokens와 동일한 매핑. */
function collectNodeSpans(spans: SpanT[], nodeKey: string): SpanT[] {
  const byId = new Map(spans.map((s) => [s.id, s]));
  const children = new Map<string | null, string[]>();
  for (const s of spans) {
    const p = s.parent_run_id ?? null;
    (children.get(p) ?? children.set(p, []).get(p)!).push(s.id);
  }
  const out: SpanT[] = [];
  const seen = new Set<string>();
  for (const root of spans.filter((s) => s.name === nodeKey)) {
    const stack = [root.id];
    while (stack.length) {
      const cur = byId.get(stack.pop()!);
      if (!cur || seen.has(cur.id)) continue;
      seen.add(cur.id);
      out.push(cur);
      for (const c of children.get(cur.id) ?? []) stack.push(c);
    }
  }
  out.sort((a, b) => (a.start_time ?? "").localeCompare(b.start_time ?? ""));
  return out;
}

function jsonPreview(v: unknown, max = 16000): string {
  if (v == null) return "—";
  let s: string;
  try { s = JSON.stringify(v, null, 2); } catch { s = String(v); }
  return s.length > max ? s.slice(0, max) + `\n… (${s.length - max} chars 생략)` : s;
}

/* 한 span의 I/O 카드 — run_type 배지 + latency/tokens + inputs/outputs 접이식. */
function SpanCard({ span, depth }: { span: SpanT; depth: number }) {
  const tok = span.tokens?.total ?? 0;
  const isLlm = span.run_type === "llm";
  return (
    <div className="span-card" style={{ marginLeft: depth * 12 }}>
      <div className="span-card-head">
        <span className={`span-type ${isLlm ? "llm" : ""}`}>{span.run_type}</span>
        <span className="span-name">{span.name}</span>
        <span className="span-card-meta">
          {span.latency_seconds != null && <span>{span.latency_seconds.toFixed(2)}s</span>}
          {tok > 0 && <span>{fmtTokens(tok)} tok</span>}
        </span>
      </div>
      {span.error && <div className="drawer-code error" style={{ marginTop: 6 }}>{span.error}</div>}
      <details className="span-io"><summary>inputs</summary>
        <div className="drawer-code">{jsonPreview(span.inputs)}</div>
      </details>
      <details className="span-io" {...(isLlm ? { open: true } : {})}><summary>outputs</summary>
        <div className="drawer-code">{jsonPreview(span.outputs)}</div>
      </details>
    </div>
  );
}

function NodeDrawer({
  detail, nodeKey, onClose, onRetry, traceId, spans, onLoadSpans,
}: {
  detail: RunDetailT;
  nodeKey: string;
  onClose: () => void;
  onRetry: () => void;
  traceId?: string | null;
  spans?: SpansState;
  onLoadSpans: (traceId: string) => void;
}) {
  const def = NODE_DEFS.find((n) => n.key === nodeKey);
  const state = detail.node_states?.[nodeKey] ?? { status: "queued" };
  const [tab, setTab] = useState("overview");
  useEffect(() => { setTab("overview"); }, [nodeKey]);
  // inputs/outputs 탭을 열면 그때 trace span을 lazy 로드 (LangSmith가 느릴 수 있어 on-demand).
  useEffect(() => {
    if (tab === "inputs/outputs" && traceId && spans == null) onLoadSpans(traceId);
  }, [tab, traceId, spans, onLoadSpans]);
  if (!def) return null;

  const tokens = state.tokens ?? {};
  const tokTotal = tokens.total ?? 0;
  const tabs = ["overview", "candidates", state.error ? "error" : "inputs/outputs", "logs"];

  return (
    <div className="drawer">
      <div className="drawer-head">
        <div className="drawer-kind-ico"><NodeKindIcon kind={def.kind} /></div>
        <div className="drawer-head-body">
          <h3 className="drawer-name">{def.label}</h3>
          <div className="drawer-meta">
            <span className={`pill ${state.status}`}><span className="dot" />{state.status}</span>
            <span>{def.kind === "llm" ? "LLM 노드" : def.kind === "db" ? "DB I/O" : "sandbox"}{def.side ? " · side-step" : ""}</span>
          </div>
        </div>
        <button className="drawer-close" onClick={onClose}><Icon.Close /></button>
      </div>

      <div className="drawer-tabs">
        {tabs.map((t) => (
          <button key={t} className={`drawer-tab${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>

      <div className="drawer-body">
        {tab === "overview" && (
          <>
            <p style={{ margin: "0 0 16px", color: "var(--muted)", fontSize: 13, lineHeight: 1.6 }}>{def.note}</p>
            <div className="section-title">실행</div>
            <dl className="kv">
              <dt>status</dt><dd>{state.status}</dd>
              <dt>duration</dt><dd>{fmtDuration(state.duration_ms)}</dd>
              <dt>retries</dt><dd>{state.retries ?? 0}</dd>
              {state.candidates_in != null && (
                <>
                  <dt>candidates</dt>
                  <dd>{state.candidates_out ?? "?"} / {state.candidates_in}</dd>
                </>
              )}
            </dl>
            {def.kind === "llm" && tokTotal > 0 && (
              <>
                <div className="section-title">토큰 사용량</div>
                <div className="tokens-bar">
                  <span className="prompt" style={{ width: `${((tokens.prompt ?? 0) / tokTotal) * 100}%` }} />
                  <span className="completion" style={{ width: `${((tokens.completion ?? 0) / tokTotal) * 100}%` }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: "var(--muted)", fontFamily: "var(--font-mono)" }}>
                  <span>prompt {fmtTokens(tokens.prompt)}</span>
                  <span>completion {fmtTokens(tokens.completion)}</span>
                  <span><strong style={{ color: "var(--ink)" }}>총 {fmtTokens(tokTotal)}</strong></span>
                </div>
              </>
            )}
            {state.error && (
              <>
                <div className="section-title" style={{ color: "var(--st-failed)" }}>에러</div>
                <div className="drawer-code error">{state.error}</div>
              </>
            )}
          </>
        )}

        {tab === "candidates" && (
          (state.candidate_results ?? []).length === 0 ? (
            <div className="empty">이 노드는 후보 단위 결과를 만들지 않아요.</div>
          ) : (
            <div className="cand-list">
              {state.candidate_results!.map((c) => (
                <div key={c.idx} className="cand-row">
                  <span className="num">#{c.idx}</span>
                  <span className="title">{c.note || "—"}</span>
                  <span className={`pill ${c.status === "pass" ? "done" : c.status === "warn" ? "running" : "failed"}`}>
                    <span className="dot" /> {c.status}
                  </span>
                </div>
              ))}
            </div>
          )
        )}

        {tab === "error" && (
          <>
            <div className="section-title" style={{ color: "var(--st-failed)" }}>에러 메시지</div>
            <div className="drawer-code error">{state.error}</div>
            <div className="section-title">예상 원인</div>
            <ul style={{ margin: 0, paddingLeft: 18, color: "var(--ink-2)", fontSize: 13, lineHeight: 1.75 }}>
              {state.error?.includes("Ollama") && (
                <>
                  <li><code>ollama serve</code> 가 떠 있는지 확인 (포트 11434)</li>
                  <li><code>JCQ_SKIP_ENSEMBLE=1</code> 로 임시 우회 가능</li>
                  <li><code>docs/setup-ollama.md</code> 참고</li>
                </>
              )}
              {state.error?.includes("Integrity") && (
                <>
                  <li>같은 제목의 변형이 이미 존재할 가능성</li>
                  <li>변형 제목 생성 프롬프트에 다양성 보강 확인</li>
                </>
              )}
              {(state.error?.includes("Connection") || state.error?.includes("HTTP")) && (
                <li>backend/judge_engine 연결 확인 — JCQ_BACKEND_URL / JCQ_JUDGE_URL</li>
              )}
            </ul>
            <div className="section-title">바로 가기</div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-outline btn-sm" onClick={onRetry}><Icon.Rerun /> 이 run 재실행</button>
            </div>
          </>
        )}

        {tab === "inputs/outputs" && (() => {
          const ready = spans?.status === "ready" ? spans.data : null;
          const nodeSpans = ready ? collectNodeSpans(ready.spans, nodeKey) : [];
          return (
            <>
              {/* LangSmith trace 딥링크 */}
              {(traceId || ready?.trace_url) && (
                <div className="ls-bar">
                  <span className="ls-trace">trace {traceId?.slice(0, 8) ?? "—"}…</span>
                  {ready?.trace_url
                    ? <a className="ls-link" href={ready.trace_url} target="_blank" rel="noreferrer">LangSmith에서 열기 <Icon.External /></a>
                    : <span className="ls-proj">{ready?.project ?? "jcq-authoring"}</span>}
                </div>
              )}

              {/* 트레이스 로드 상태별 분기 */}
              {spans?.status === "loading" && <div className="empty">LangSmith trace 불러오는 중…</div>}
              {spans?.status === "unavailable" && (
                <div className="ls-note">LANGSMITH_API_KEY 미설정 — 실시간 trace 없이 outputs preview만 표시합니다.</div>
              )}
              {spans?.status === "notfound" && (
                <div className="ls-note">이 trace가 아직 LangSmith에 인제스트되지 않았어요. 잠시 후 다시 시도하세요.</div>
              )}
              {spans?.status === "error" && (
                <div className="drawer-code error">{spans.message}</div>
              )}

              {/* 성공 — 이 노드의 span I/O */}
              {ready && nodeSpans.length > 0 && (
                <>
                  <div className="section-title">LangSmith 노드 I/O ({nodeSpans.length} spans)</div>
                  <div className="span-tree">
                    {nodeSpans.map((s) => (
                      <SpanCard key={s.id} span={s} depth={s.name === nodeKey ? 0 : 1} />
                    ))}
                  </div>
                </>
              )}
              {ready && nodeSpans.length === 0 && (
                <div className="ls-note">이 노드의 span이 trace에 없어요 (DB/sandbox 노드는 LLM span이 없을 수 있음).</div>
              )}

              {/* 폴백/보조 — DB 스냅샷 outputs_preview */}
              {state.outputs_preview && (
                <details {...(ready && nodeSpans.length > 0 ? {} : { open: true })}>
                  <summary className="section-title" style={{ cursor: "pointer", display: "list-item" }}>
                    Outputs preview (DB 스냅샷)
                  </summary>
                  <div className="drawer-code">{jsonPreview(state.outputs_preview)}</div>
                </details>
              )}
              {!traceId && !state.outputs_preview && (
                <div className="empty">이 run엔 trace_id가 없어요 — LangSmith 비활성 상태로 생성된 run.</div>
              )}
            </>
          );
        })()}

        {tab === "logs" && (
          <div className="drawer-code dark">
            {[
              `▶ ${def.label} started`,
              state.candidates_in != null && `received ${state.candidates_in} candidates`,
              state.retries ? `retry ×${state.retries} …` : null,
              state.status === "done" && `✓ done in ${fmtDuration(state.duration_ms)}`,
              state.status === "failed" && `✗ ${state.error}`,
            ].filter(Boolean).map((l, i) => <div key={i}>{l as string}</div>)}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── New-run inline form ───────────────────────────────────────────────── */
function NewRunForm({ onStart, onCancel }: { onStart: (pid: number, count: number) => void; onCancel: () => void }) {
  const [pid, setPid] = useState("");
  const [count, setCount] = useState("3");
  return (
    <div style={{ margin: "auto", maxWidth: 420, textAlign: "center" }}>
      <div className="section-title" style={{ textAlign: "left" }}>새 파이프라인 run</div>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", justifyContent: "center" }}>
        <div style={{ textAlign: "left" }}>
          <label style={{ fontSize: 11.5, color: "var(--muted)" }}>원본 문제 ID</label>
          <input className="search-wide" type="number" min={1} value={pid} onChange={(e) => setPid(e.target.value)} placeholder="1" style={{ width: 110, display: "block" }} />
        </div>
        <div style={{ textAlign: "left" }}>
          <label style={{ fontSize: 11.5, color: "var(--muted)" }}>생성 수</label>
          <input className="search-wide" type="number" min={1} max={20} value={count} onChange={(e) => setCount(e.target.value)} style={{ width: 80, display: "block" }} />
        </div>
        <button
          className="btn btn-primary"
          onClick={() => { const p = parseInt(pid, 10); const c = parseInt(count, 10); if (p > 0 && c > 0) onStart(p, c); }}
        >▶ 실행</button>
        <button className="btn btn-ghost" onClick={onCancel}>취소</button>
      </div>
    </div>
  );
}

/* ── Runs View (top-level) ─────────────────────────────────────────────── */
export default function RunsView({ settings }: Props) {
  const [runs, setRuns] = useState<RunSummaryT[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetailT | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [copied, setCopied] = useState(false);
  const [spansCache, setSpansCache] = useState<Record<string, SpansState>>({});
  const streamRef = useRef<AbortController | null>(null);
  const spansInflight = useRef<Set<string>>(new Set());

  // LangSmith span lazy 로드 — trace_id별 1회 (캐시). 503/404를 상태로 구분해 UI에서 안내.
  const loadSpans = useCallback(async (traceId: string) => {
    if (spansInflight.current.has(traceId)) return;
    spansInflight.current.add(traceId);
    setSpansCache((prev) => ({ ...prev, [traceId]: { status: "loading" } }));
    try {
      const r = await adminFetch(`/api/spans/${traceId}`, settings);
      let next: SpansState;
      if (r.ok) next = { status: "ready", data: await r.json() };
      else if (r.status === 503) next = { status: "unavailable" };
      else if (r.status === 404) next = { status: "notfound" };
      else next = { status: "error", message: `[${r.status}] ${(await r.text()).slice(0, 200)}` };
      setSpansCache((prev) => ({ ...prev, [traceId]: next }));
    } catch (e) {
      setSpansCache((prev) => ({ ...prev, [traceId]: { status: "error", message: (e as Error).message } }));
    } finally {
      spansInflight.current.delete(traceId);
    }
  }, [settings]);

  const loadRuns = useCallback(async () => {
    try {
      const r = await adminFetch("/api/runs?limit=100", settings);
      if (!r.ok) { setError(`[${r.status}] runs 목록 로드 실패`); return; }
      const data: RunSummaryT[] = await r.json();
      setRuns(data);
      return data;
    } catch (e) {
      setError((e as Error).message);
    }
  }, [settings]);

  const loadDetail = useCallback(async (id: string) => {
    try {
      const r = await adminFetch(`/api/runs/${id}`, settings);
      if (!r.ok) { setError(`[${r.status}] run 상세 로드 실패`); return; }
      const d: RunDetailT = await r.json();
      setDetail(d);
      setSelectedNode(d.failed_at_node ?? null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [settings]);

  // 초기 로드
  useEffect(() => {
    (async () => {
      const data = await loadRuns();
      if (data && data.length > 0) {
        setSelectedId(data[0].id);
        loadDetail(data[0].id);
      } else {
        setShowNew(true);
      }
    })();
    return () => streamRef.current?.abort();
  }, [loadRuns, loadDetail]);

  function selectRun(id: string) {
    streamRef.current?.abort();
    streamRef.current = null;
    setSelectedId(id);
    setShowNew(false);
    loadDetail(id);
  }

  // SSE 구독 — fetch+ReadableStream (EventSource는 Bearer 헤더 불가)
  const subscribe = useCallback(async (runId: string) => {
    streamRef.current?.abort();
    const ctrl = new AbortController();
    streamRef.current = ctrl;
    try {
      const resp = await adminFetch(`/api/runs/${runId}/events`, settings, { signal: ctrl.signal });
      if (!resp.ok || !resp.body) return;
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const frames = buf.split("\n\n");
        buf = frames.pop() ?? "";
        for (const frame of frames) {
          for (const line of frame.split("\n")) {
            if (!line.startsWith("data:")) continue;
            const raw = line.slice(5).trim();
            try {
              const p = JSON.parse(raw);
              if (p.type === "node") {
                setDetail((prev) => prev && prev.id === runId
                  ? { ...prev, node_states: { ...prev.node_states, [p.node]: p.state } }
                  : prev);
              } else if (p.type === "done" || p.type === "error") {
                await loadDetail(runId);
                loadRuns();
                return;
              }
            } catch { /* ignore */ }
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    }
  }, [settings, loadDetail, loadRuns]);

  async function beginRun(problemId: number, count: number) {
    setShowNew(false);
    setError("");
    try {
      const r = await adminFetch("/api/runs", settings, {
        method: "POST",
        body: JSON.stringify({ problem_id: problemId, count }),
      });
      if (!r.ok) { setError(`[${r.status}] ${(await r.text()).slice(0, 200)}`); return; }
      const { run_id } = await r.json();
      const optimistic: RunSummaryT = {
        id: run_id, problem_id: problemId, problem_title: null, target_count: count,
        status: "running", started_at: new Date().toISOString(), saved_count: 0,
      };
      setRuns((prev) => [optimistic, ...prev]);
      setSelectedId(run_id);
      setDetail({ ...optimistic, node_states: { ...EMPTY_STATES }, saved_problem_ids: [], errors: [] });
      setSelectedNode(null);
      subscribe(run_id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function retryRun() {
    if (!selectedId) return;
    setError("");
    try {
      const r = await adminFetch(`/api/runs/${selectedId}/retry`, settings, { method: "POST", body: "{}" });
      if (!r.ok) { setError(`[${r.status}] ${(await r.text()).slice(0, 200)}`); return; }
      const { run_id } = await r.json();
      const base = detail;
      const optimistic: RunSummaryT = {
        id: run_id, problem_id: base?.problem_id ?? null, problem_title: base?.problem_title ?? null,
        target_count: base?.target_count ?? 1, status: "running",
        started_at: new Date().toISOString(), saved_count: 0,
      };
      setRuns((prev) => [optimistic, ...prev]);
      setSelectedId(run_id);
      setDetail({ ...optimistic, node_states: { ...EMPTY_STATES }, saved_problem_ids: [], errors: [] });
      setSelectedNode(null);
      subscribe(run_id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function copyTrace() {
    if (!detail?.trace_id) return;
    navigator.clipboard?.writeText(detail.trace_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  }

  const drawerOpen = selectedNode != null && detail != null;

  return (
    <div className={`main runs${drawerOpen ? " drawer-open" : ""}`}>
      <RunsSidebar
        runs={runs}
        selectedId={selectedId}
        onSelect={selectRun}
        onNew={() => { setShowNew(true); setSelectedNode(null); }}
      />

      <div className="graph-wrap">
        <div className="graph-toolbar">
          {detail && !showNew ? (
            <>
              <span className="run-head-id">{detail.id.slice(0, 16)}</span>
              <span className="run-head-bullet">·</span>
              <span className="run-head-title">#{detail.problem_id ?? "?"} {detail.problem_title ?? ""}</span>
              <span className={`pill ${detail.status}`} style={{ marginLeft: 4 }}>
                <span className="dot" />
                {detail.status === "failed" ? `failed @ ${detail.failed_at_node ?? "?"}` : detail.status}
              </span>
              <span className="run-head-meta">
                {fmtDuration(detail.total_duration_ms)} · {detail.target_count}개 · 저장 {detail.saved_count}
              </span>
              <div style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>
                {detail.trace_id && (
                  <button className="copy" onClick={copyTrace} title="trace_id 복사">
                    <Icon.Copy /> {copied ? "복사됨!" : `${detail.trace_id.slice(0, 8)}…`}
                  </button>
                )}
                <div className="zoom-controls">
                  <button className="zoom-btn" onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.1).toFixed(2)))}><Icon.ZoomOut /></button>
                  <span className="zoom-label">{Math.round(zoom * 100)}%</span>
                  <button className="zoom-btn" onClick={() => setZoom((z) => Math.min(1.6, +(z + 0.1).toFixed(2)))}><Icon.ZoomIn /></button>
                  <button className="zoom-btn" onClick={() => setZoom(1)} title="reset"><Icon.Reset /></button>
                </div>
                <button className={`btn btn-sm ${detail.status === "failed" ? "btn-primary" : "btn-outline"}`} onClick={retryRun}>
                  <Icon.Rerun /> 재실행
                </button>
              </div>
            </>
          ) : (
            <span className="run-head-title">파이프라인 runs</span>
          )}
        </div>

        <div className="graph-canvas">
          {showNew || !detail ? (
            <div style={{ display: "flex", height: "100%", padding: 40 }}>
              <NewRunForm onStart={beginRun} onCancel={() => { setShowNew(false); if (selectedId) loadDetail(selectedId); }} />
            </div>
          ) : (
            <PipelineGraph detail={detail} selectedNode={selectedNode} onSelectNode={setSelectedNode} zoom={zoom} />
          )}
        </div>

        {error && <div className="output-panel err" style={{ margin: 12 }}>{error}</div>}
      </div>

      {drawerOpen && (
        <NodeDrawer
          detail={detail!}
          nodeKey={selectedNode!}
          onClose={() => setSelectedNode(null)}
          onRetry={retryRun}
          traceId={detail!.trace_id}
          spans={detail!.trace_id ? spansCache[detail!.trace_id] : undefined}
          onLoadSpans={loadSpans}
        />
      )}
    </div>
  );
}
