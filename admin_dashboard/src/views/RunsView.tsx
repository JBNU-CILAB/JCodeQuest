import { useState, useEffect, useLayoutEffect, useRef, useCallback } from "react";
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

/* raw status(예외 없이 실행됨)를 '결과 기반' 표시 상태로 재해석:
   게이트가 후보를 전멸(candidates_out===0)시키면 그 노드는 'blocked', 이후 done 노드는
   사실상 no-op이므로 'skipped'. 예외(failed)/running/queued는 그대로. 프론트 파생(백엔드 무변경). */
function deriveNodeStatuses(detail: RunDetailT | null): Record<string, string> {
  const ns = detail?.node_states ?? {};
  const order = NODE_DEFS.map((d) => d.key);
  const out: Record<string, string> = {};
  for (const k of order) out[k] = ns[k]?.status ?? "queued";

  // 첫 dead-end = done이고 candidates_out===0이며 (유입이 없거나 >0)인 게이트
  let deadIdx = -1;
  for (let i = 0; i < order.length; i++) {
    const s = ns[order[i]];
    if (!s || s.status !== "done") continue;
    const co = s.candidates_out;
    if (typeof co === "number" && co === 0 && (s.candidates_in == null || s.candidates_in > 0)) {
      deadIdx = i;
      break;
    }
  }
  if (deadIdx === -1) return out;

  out[order[deadIdx]] = "blocked";
  for (let i = deadIdx + 1; i < order.length; i++) {
    if (out[order[i]] === "done") out[order[i]] = "skipped";
  }
  return out;
}

/* 삭제 확인 대상 — 개별(one) 또는 status별 일괄(bulk). */
type PendingDelete =
  | { kind: "one"; id: string; title: string }
  | { kind: "many"; ids: string[] };

/* ── run 결과 판정 (오판 방지) ──────────────────────────────────────────
   인프라 실패(failed) vs 전량 탈락(done·saved 0) vs 부분/완전 성공을 구분.
   거친 라벨은 RunSummary만으로, 상세 사유는 node_states 탈락 퍼널로 계산. */
type OutcomeTone = "gray" | "red" | "amber" | "blue" | "green";
interface RunOutcome { kind: "running" | "failed" | "empty" | "partial" | "success"; chip: string; tone: OutcomeTone; }

function runOutcome(r: { status: string; saved_count?: number; target_count?: number }): RunOutcome {
  if (r.status === "running") return { kind: "running", chip: "진행 중", tone: "gray" };
  if (r.status === "failed") return { kind: "failed", chip: "실패", tone: "red" };
  const saved = r.saved_count ?? 0;
  const target = r.target_count ?? 0;
  if (saved === 0) return { kind: "empty", chip: "전량 탈락", tone: "amber" };
  if (target && saved < target) return { kind: "partial", chip: `부분 ${saved}/${target}`, tone: "blue" };
  return { kind: "success", chip: `성공 ${saved}`, tone: "green" };
}

/* 게이트 노드 순서 + 사람이 읽는 라벨 — 탈락 퍼널 산출용. persist는 sink라 제외. */
const GATE_ORDER = ["verify_candidates", "judge_candidates", "solve_candidates", "attack_candidates", "compare_to_original"];
const GATE_LABEL: Record<string, string> = {
  verify_candidates: "verify(레퍼런스 실행)",
  judge_candidates: "judge(품질 심사)",
  solve_candidates: "solve(풀이 가능성)",
  attack_candidates: "attack(테스트 변별력)",
  compare_to_original: "compare(환각/의도)",
};

/* node_states의 candidates_in/out 을 게이트 순서로 이어 '어디서 가장 많이 떨어졌나' 산출. */
function attritionReason(detail: RunDetailT): { gen0: boolean; text: string | null } {
  const ns = detail.node_states || {};
  const gen = ns["generate_variants"];
  if (gen && gen.status === "done" && (gen.candidates_out ?? 0) === 0) {
    return { gen0: true, text: "generate_variants가 후보를 만들지 못함" };
  }
  let worst: { node: string; inn: number; drop: number } | null = null;
  const drops: string[] = [];
  for (const g of GATE_ORDER) {
    const s = ns[g];
    if (!s || s.candidates_in == null || s.candidates_out == null) continue;
    const drop = s.candidates_in - s.candidates_out;
    if (drop > 0) {
      drops.push(`${GATE_LABEL[g] ?? g} −${drop}`);
      if (!worst || drop > worst.drop) worst = { node: g, inn: s.candidates_in, drop };
    }
  }
  if (worst) {
    const lead = `${GATE_LABEL[worst.node] ?? worst.node}에서 ${worst.drop}/${worst.inn} 탈락`;
    return { gen0: false, text: drops.length > 1 ? `${lead} · 분산(${drops.join(", ")})` : lead };
  }
  return { gen0: false, text: null };
}

/* run 상단 결과 요약 배너 — outcome 칩 + 한 줄 사유 + fail-open 경고. */
function RunOutcomeBanner({ detail }: { detail: RunDetailT }) {
  const oc = runOutcome(detail);
  if (oc.kind === "running") return null;
  const failOpen = detail.errors?.length ?? 0;
  let long = "";
  let reason: string | null = null;
  if (oc.kind === "failed") {
    long = detail.failed_at_node ? `인프라 실패 — ${detail.failed_at_node} 노드에서 중단` : "인프라 실패";
    reason = (detail.node_states?.[detail.failed_at_node ?? ""]?.error ?? "").slice(0, 140) || null;
  } else if (oc.kind === "empty") {
    const a = attritionReason(detail);
    long = a.gen0 ? "생성 0 — 후보가 만들어지지 않음" : "전량 탈락 — 모든 후보가 게이트에서 탈락";
    reason = a.text;
  } else if (oc.kind === "partial") {
    long = `부분 성공 — ${detail.saved_count}/${detail.target_count} 저장`;
    reason = attritionReason(detail).text;
  } else {
    long = `성공 — ${detail.saved_count}개 저장`;
  }
  return (
    <div className={`run-outcome tone-${oc.tone}`}>
      <span className={`outcome-chip tone-${oc.tone}`}>{oc.chip}</span>
      <span className="run-outcome-text">{long}{reason ? ` · ${reason}` : ""}</span>
      {failOpen > 0 && (
        <span className="outcome-warn" title="fail-open으로 무시된 오류 — 일부 게이트가 우회됐을 수 있음">
          ⚠ fail-open {failOpen}
        </span>
      )}
    </div>
  );
}

/* ── Runs Sidebar ──────────────────────────────────────────────────────── */
function RunsSidebar({
  runs, selectedId, onSelect, onNew, onRequestDelete,
  selectMode, selectedIds, onEnterSelect, onExitSelect, onToggleSelect, onSetSelection, onDeleteSelected,
}: {
  runs: RunSummaryT[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRequestDelete: (run: RunSummaryT) => void;
  selectMode: boolean;
  selectedIds: Set<string>;
  onEnterSelect: () => void;
  onExitSelect: () => void;
  onToggleSelect: (id: string) => void;
  onSetSelection: (ids: string[]) => void;
  onDeleteSelected: () => void;
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

  const allChecked = filtered.length > 0 && filtered.every((r) => selectedIds.has(r.id));
  const toggleAll = () => onSetSelection(allChecked ? [] : filtered.map((r) => r.id));

  return (
    <aside className="runs-sidebar">
      <div className="runs-sidebar-head">
        <h3>
          {selectMode ? (
            <>
              <button className={`check-box${allChecked ? " on" : ""}`} onClick={toggleAll} title="전체 선택/해제">
                {allChecked && <Icon.Check />}
              </button>
              <span className="count">{selectedIds.size}개 선택</span>
              <span className="spacer" />
              <button className="btn btn-ghost btn-sm" onClick={onExitSelect}>취소</button>
              <button className="btn btn-danger btn-sm" disabled={selectedIds.size === 0} onClick={onDeleteSelected}>
                삭제 {selectedIds.size}
              </button>
            </>
          ) : (
            <>
              Recent runs <span className="count">{filtered.length}</span>
              <span className="spacer" />
              <button className="btn btn-ghost btn-sm" disabled={runs.length === 0} onClick={onEnterSelect}>선택</button>
              <button className="btn btn-primary btn-sm" onClick={onNew}>+ 새 run</button>
            </>
          )}
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
        {filtered.map((r) => {
          const checked = selectedIds.has(r.id);
          return (
            <div key={r.id} className={`run-card-wrap${selectMode && checked ? " checked" : ""}`}>
              <button
                className={`run-card${!selectMode && r.id === selectedId ? " active" : ""}${selectMode && checked ? " sel" : ""}`}
                onClick={() => (selectMode ? onToggleSelect(r.id) : onSelect(r.id))}
              >
                <div className="run-card-head">
                  {(() => { const oc = runOutcome(r); return <span className={`outcome-chip tone-${oc.tone}`}>{oc.chip}</span>; })()}
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
              {selectMode ? (
                <span className={`run-check${checked ? " on" : ""}`} aria-hidden>
                  {checked && <Icon.Check />}
                </span>
              ) : (
                <button className="run-del" title="이 run 삭제" onClick={() => onRequestDelete(r)}>
                  <Icon.Trash />
                </button>
              )}
            </div>
          );
        })}
        {filtered.length === 0 && (
          <div className="empty" style={{ padding: "40px 12px" }}>조건에 맞는 run이 없어요.</div>
        )}
      </div>
    </aside>
  );
}

/* ── Node Card ─────────────────────────────────────────────────────────── */
// 노드 pill 라벨 — "done"은 '작업 성공'을 더 직관적으로 표시하려 "Success"로 바꾼다.
// (.pill의 text-transform: uppercase로 최종 표시는 SUCCESS — FAILED/RUNNING과 일관.)
function nodeStatusLabel(s: string): string {
  return s === "done" ? "Success" : s;
}

function NodeCard({
  idx, def, state, selected, onClick, displayStatus,
}: {
  idx: number;
  def: typeof NODE_DEFS[number];
  state: RunNodeStateT;
  selected: boolean;
  onClick: () => void;
  displayStatus?: string;
}) {
  const isLlm = def.kind === "llm";
  const cands = state.candidate_results ?? [];
  const tokTotal = state.tokens?.total ?? 0;
  const st = displayStatus ?? state.status;

  return (
    <button
      data-node={def.key}
      className={`node-card ${st}${selected ? " selected" : ""}`}
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
          <span className={`pill ${st}`}><span className="dot" />{nodeStatusLabel(st)}</span>
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
  detail, selectedNode, selectedJudge, onSelectNode, onSelectJudge, zoom,
}: {
  detail: RunDetailT | null;
  selectedNode: string | null;
  selectedJudge: string | null;
  onSelectNode: (k: string) => void;
  onSelectJudge: (nodeKey: string, judgeId: string) => void;
  zoom: number;
}) {
  // 앙상블 노드 펼침 상태 (노드 key → 펼침). 판사 서브노드를 클릭하면 자동으로 펼친다.
  const [openEnsembles, setOpenEnsembles] = useState<Set<string>>(new Set());
  const toggleEnsemble = (key: string) =>
    setOpenEnsembles((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  const derived = deriveNodeStatuses(detail);
  const blockedNode = NODE_DEFS.find((d) => derived[d.key] === "blocked")?.key ?? null;

  // ── 역방향 루프 화살표 측정 ─────────────────────────────────────────────
  // loopback이 지정된 노드(strengthen→attack, revise→verify)에 대해
  // SVG 곡선으로 source 우측에서 target 우측까지 활처럼 그린다. 화살표 끝은
  // target 노드 우측 가장자리에 점선으로 표시 → "조건 만족 시 되돌아감" 의미.
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [loopEdges, setLoopEdges] = useState<Array<{
    key: string; targetKey: string; d: string; midX: number; midY: number;
    active: boolean;
  }>>([]);
  const [resizeTick, setResizeTick] = useState(0);
  useEffect(() => {
    const onResize = () => setResizeTick((t) => t + 1);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  useLayoutEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const stageRect = stage.getBoundingClientRect();
    const next: typeof loopEdges = [];
    for (const def of NODE_DEFS) {
      if (!def.loopback) continue;
      const src = stage.querySelector<HTMLElement>(`[data-node="${def.key}"]`);
      const tgt = stage.querySelector<HTMLElement>(`[data-node="${def.loopback}"]`);
      if (!src || !tgt) continue;
      const sr = src.getBoundingClientRect();
      const tr = tgt.getBoundingClientRect();
      // stage가 scale(zoom)된 상태 → 좌표를 unscaled로 환산해 SVG도 함께 스케일되게.
      const sx = (sr.right - stageRect.left) / zoom;
      const sy = (sr.top + sr.height / 2 - stageRect.top) / zoom;
      const tx = (tr.right - stageRect.left) / zoom;
      const ty = (tr.top + tr.height / 2 - stageRect.top) / zoom;
      const bow = 80; // 활(curve)이 노드 우측으로 부풀어 나가는 거리
      const d = `M ${sx} ${sy} C ${sx + bow} ${sy}, ${tx + bow} ${ty}, ${tx} ${ty}`;
      const midX = (sx + tx) / 2 + bow * 0.75;
      const midY = (sy + ty) / 2;
      // 이 루프가 실제로 돌았는지(되돌아간 적 있는지) — node_states.retries > 0 또는 done.
      const srcState = detail?.node_states?.[def.key];
      const active = !!srcState && (
        (typeof srcState.retries === "number" && srcState.retries > 0) ||
        srcState.status === "done" || srcState.status === "running"
      );
      next.push({ key: def.key, targetKey: def.loopback, d, midX, midY, active });
    }
    setLoopEdges(next);
  }, [detail?.id, detail?.node_states, zoom, openEnsembles, resizeTick]);

  // 실패/막힌/선택 노드를 세로 중앙으로 자동 스크롤 — 포렌식 핵심 어포던스.
  useEffect(() => {
    const target = selectedNode || detail?.failed_at_node || blockedNode;
    if (!target) return;
    requestAnimationFrame(() => {
      const el = document.querySelector<HTMLElement>(`[data-node="${target}"]`);
      const wrap = el?.closest<HTMLElement>(".graph-canvas");
      if (!el || !wrap) return;
      const desired = el.offsetTop - (wrap.clientHeight - el.offsetHeight) / 2;
      wrap.scrollTo({ top: Math.max(0, desired), behavior: "smooth" });
    });
  }, [detail?.id, selectedNode, detail?.failed_at_node, blockedNode]);

  // 판사 서브노드가 선택되면 해당 앙상블 노드를 자동으로 펼친다.
  useEffect(() => {
    if (selectedJudge && selectedNode) {
      setOpenEnsembles((p) => (p.has(selectedNode) ? p : new Set(p).add(selectedNode)));
    }
  }, [selectedJudge, selectedNode]);

  return (
    <div ref={stageRef} className="graph-stage vertical" style={{ transform: `scale(${zoom})` }}>
      {loopEdges.length > 0 && (
        <svg className="loop-edge-svg" aria-hidden="true">
          <defs>
            <marker
              id="loop-back-arrow" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="7" markerHeight="7" orient="auto"
            >
              {/* fill="context-stroke"는 사용처 path의 stroke 색을 그대로 받아온다 →
                  loop가 active로 보라색이 되면 화살촉도 보라로 자동 전환. */}
              <path d="M0 0 L10 5 L0 10 z" fill="context-stroke" />
            </marker>
          </defs>
          {loopEdges.map((e) => (
            <g key={e.key} className={`loop-edge${e.active ? " active" : ""}`}>
              <path className="loop-back" d={e.d} markerEnd="url(#loop-back-arrow)" />
              <text x={e.midX} y={e.midY} className="loop-label">↻ loop back</text>
            </g>
          ))}
        </svg>
      )}
      <div className="node-row">
        {NODE_DEFS.map((def, i) => {
          const state = statusOf(detail, def.key);
          const isLast = i === NODE_DEFS.length - 1;
          const open = openEnsembles.has(def.key);
          return (
            <span key={def.key} style={{ display: "contents" }}>
              {def.ensemble ? (
                <div className="ensemble-group">
                  <div className="ensemble-main">
                    <NodeCard
                      idx={i}
                      def={def}
                      state={state}
                      displayStatus={derived[def.key]}
                      selected={selectedNode === def.key && !selectedJudge}
                      onClick={() => onSelectNode(def.key)}
                    />
                    <button
                      className={`ensemble-toggle${open ? " open" : ""}`}
                      onClick={() => toggleEnsemble(def.key)}
                      title={open ? "판사 접기" : "3 판사 펼치기"}
                    >
                      <span className="ensemble-caret"><Icon.Chevron /></span>
                      {open ? "판사 접기" : `${def.ensemble.length} 판사 펼치기`}
                    </button>
                  </div>
                  {open && (
                    <div className="ensemble-children">
                      <div className="ensemble-tree">
                        {def.ensemble.map((m, k) => (
                          <div className="ensemble-leaf" key={m.id}>
                            <button
                              className={`sub-node${selectedNode === def.key && selectedJudge === m.id ? " selected" : ""}`}
                              style={{ animationDelay: `${k * 70}ms` }}
                              onClick={() => onSelectJudge(def.key, m.id)}
                            >
                              <span className="sub-node-ico"><Icon.LLM /></span>
                              <span className="sub-node-name">{m.id}</span>
                              <span className="sub-node-model">{m.model}</span>
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <NodeCard
                  idx={i}
                  def={def}
                  state={state}
                  displayStatus={derived[def.key]}
                  selected={selectedNode === def.key}
                  onClick={() => onSelectNode(def.key)}
                />
              )}
              {!isLast && <span className={`arrow ${derived[def.key] === "skipped" || derived[def.key] === "blocked" ? "skipped" : ""}`} />}
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

/* ── LangChain I/O → 사람이 읽기 좋은 형태 추출 (실패 시 raw JSON 폴백) ── */
type ChatMsg = { role: string; content: string };

const _ROLE: Record<string, string> = {
  human: "user", ai: "assistant", system: "system", tool: "tool",
  function: "tool", chat: "assistant", user: "user", assistant: "assistant",
};
function normRole(r: string): string { return _ROLE[r?.toLowerCase?.()] ?? (r || "msg"); }

/* content가 문자열/파트배열/객체 무엇이든 평문 텍스트로. */
function asText(content: unknown): string {
  if (content == null) return "";
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((p) => {
      if (typeof p === "string") return p;
      if (p && typeof p === "object") return String((p as Record<string, unknown>).text ?? (p as Record<string, unknown>).content ?? "");
      return "";
    }).join("");
  }
  if (typeof content === "object") {
    const o = content as Record<string, unknown>;
    if (typeof o.content === "string") return o.content;
  }
  try { return JSON.stringify(content); } catch { return String(content); }
}

/* 메시지 dict 1개 → {role, content}. lc serialized({id:[..,'HumanMessage'],kwargs}) 및 {type/role,content} 모두 처리. */
function msgFromDict(m: unknown): ChatMsg | null {
  if (!m || typeof m !== "object") return typeof m === "string" ? { role: "user", content: m } : null;
  const o = m as Record<string, unknown>;
  if (Array.isArray(o.id) && o.kwargs && typeof o.kwargs === "object") {
    const cls = String((o.id as unknown[])[(o.id as unknown[]).length - 1] ?? "");
    const role = cls.replace(/Message$/, "").toLowerCase();
    return { role: normRole(role), content: asText((o.kwargs as Record<string, unknown>).content) };
  }
  if ("content" in o || "type" in o || "role" in o) {
    return { role: normRole(String(o.type ?? o.role ?? "msg")), content: asText(o.content) };
  }
  return null;
}

/* inputs에서 프롬프트 메시지 목록 추출. messages가 [[...]](batch)로 중첩될 수 있음. */
function findMessages(io: unknown): ChatMsg[] | null {
  if (!io || typeof io !== "object") return null;
  const raw = (io as Record<string, unknown>).messages ?? (io as Record<string, unknown>).input;
  if (!Array.isArray(raw)) return null;
  const flat = (raw.length && Array.isArray(raw[0]) ? (raw as unknown[][]).flat() : raw) as unknown[];
  const msgs = flat.map(msgFromDict).filter(Boolean) as ChatMsg[];
  return msgs.length ? msgs : null;
}

/* outputs에서 모델 완성 텍스트 추출. generations / output / text / content 형태 대응. */
function findCompletion(io: unknown): string | null {
  if (!io || typeof io !== "object") return null;
  const o = io as Record<string, unknown>;
  const gens = o.generations;
  if (Array.isArray(gens)) {
    const flat = (gens.length && Array.isArray(gens[0]) ? (gens as unknown[][]).flat() : gens) as unknown[];
    const parts = flat.map((g) => {
      if (typeof g === "string") return g;
      const go = g as Record<string, unknown>;
      if (go?.text) return String(go.text);
      if (go?.message) return msgFromDict(go.message)?.content ?? "";
      return "";
    }).filter(Boolean);
    if (parts.length) return parts.join("\n");
  }
  if (typeof o.text === "string") return o.text;
  if (typeof o.output === "string") return o.output;
  if (o.output && typeof o.output === "object") {
    const c = asText((o.output as Record<string, unknown>).content ?? o.output);
    if (c) return c;
  }
  if (o.content != null) return asText(o.content);
  return null;
}

/* 복사 버튼 달린 코드 블록 — 길면 스크롤. */
function CodeBlock({ text, kind }: { text: string; kind?: "error" | "plain" }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(text);
    setCopied(true); setTimeout(() => setCopied(false), 1200);
  };
  return (
    <div className="code-wrap">
      <button className="code-copy" onClick={copy} title="복사">
        {copied ? "복사됨" : <Icon.Copy />}
      </button>
      <div className={`drawer-code${kind === "error" ? " error" : ""}`}>{text}</div>
    </div>
  );
}

/* 문자열이 JSON(객체/배열)이면 파싱해서 반환 — ```json 펜스/앞뒤 잡텍스트 관대 처리. 아니면 null. */
function tryParseJson(text: string): unknown {
  if (!text) return null;
  let t = text.trim();
  const fence = t.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  if (fence) t = fence[1].trim();
  if (!(t.startsWith("{") || t.startsWith("["))) {
    const s = t.indexOf("{"), e = t.lastIndexOf("}");
    if (s >= 0 && e > s) t = t.slice(s, e + 1); else return null;
  }
  try {
    const v = JSON.parse(t);
    return v && typeof v === "object" ? v : null;
  } catch { return null; }
}

/* 단일 JSON 값 렌더 — 숫자(0~1이면 가로 막대)·불리언(칩)·문자열·배열·중첩객체. */
function JsonValue({ v }: { v: unknown }) {
  if (typeof v === "number") {
    if (Number.isFinite(v) && v >= 0 && v <= 1) {
      return (
        <div className="jbar">
          <div className="jbar-track"><div className="jbar-fill" style={{ width: `${v * 100}%` }} /></div>
          <span className="jbar-val">{v.toFixed(3)}</span>
        </div>
      );
    }
    return <span className="jnum">{v}</span>;
  }
  if (typeof v === "boolean") return <span className={`jbool ${v ? "on" : "off"}`}>{v ? "✓ true" : "✗ false"}</span>;
  if (v == null) return <span className="text-dim">null</span>;
  if (typeof v === "string") return v ? <div className="jstr">{v}</div> : <span className="text-dim">""</span>;
  if (Array.isArray(v)) {
    if (!v.length) return <span className="text-dim">비어 있음</span>;
    const prim = v.every((x) => x == null || typeof x !== "object");
    if (prim) return <ul className="jlist">{v.map((x, i) => <li key={i}>{String(x)}</li>)}</ul>;
    return <div className="jnest">{v.map((x, i) => <div key={i}><StructuredJson data={x} /></div>)}</div>;
  }
  if (typeof v === "object") return <div className="jnest"><StructuredJson data={v} /></div>;
  return <span>{String(v)}</span>;
}

/* JSON 객체/배열 → key·value 행 목록. 숫자 비율은 막대, 점수/불리언이 한눈에. */
function StructuredJson({ data }: { data: unknown }) {
  const entries: [string, unknown][] = Array.isArray(data)
    ? data.map((v, i) => [String(i), v])
    : data && typeof data === "object"
      ? Object.entries(data as Record<string, unknown>)
      : [];
  if (!entries.length) return <JsonValue v={data} />;
  return (
    <div className="jview">
      {entries.map(([k, v]) => (
        <div className="jrow" key={k}>
          <span className="jkey">{k}</span>
          <div className="jval"><JsonValue v={v} /></div>
        </div>
      ))}
    </div>
  );
}

/* span.inputs/outputs(이미 객체) 렌더 — 객체/JSON이면 구조화, 너무 크면 raw 폴백. */
function IOValue({ v }: { v: unknown }) {
  if (v == null) return <span className="text-dim">—</span>;
  let obj: unknown = v;
  if (typeof v === "string") {
    const j = tryParseJson(v);
    if (!j) return <CodeBlock text={v} />;
    obj = j;
  }
  if (typeof obj !== "object") return <JsonValue v={obj} />;
  let size = 0;
  try { size = JSON.stringify(obj).length; } catch { size = Infinity; }
  // 거대한 LangGraph state는 구조화 트리가 무거우니 raw로 표시(스크롤·복사 가능)
  if (size > 40000) return <CodeBlock text={jsonPreview(obj)} />;
  return <StructuredJson data={obj} />;
}

/* 메시지 말풍선 묶음 — system 외 메시지가 JSON이면 구조화 렌더. */
function ChatView({ messages }: { messages: ChatMsg[] }) {
  return (
    <div className="chat-view">
      {messages.map((m, i) => {
        const j = m.role !== "system" ? tryParseJson(m.content) : null;
        return (
          <div key={i} className={`chat-msg role-${m.role}`}>
            <div className="chat-role">{m.role}{j ? " · json" : ""}</div>
            {j
              ? <div className="chat-content struct"><StructuredJson data={j} /></div>
              : <div className="chat-content">{m.content || "—"}</div>}
          </div>
        );
      })}
    </div>
  );
}

/* 입력/출력 구분 블록 — IN(파랑·↓) / OUT(초록·↑) 헤더로 시각 분리. */
function IOBlock({ dir, label, children }: { dir: "in" | "out"; label: string; children: React.ReactNode }) {
  return (
    <div className={`io-block ${dir}`}>
      <div className="io-block-head"><span className="io-arrow">{dir === "in" ? "↓" : "↑"}</span> {label}</div>
      <div className="io-block-body">{children}</div>
    </div>
  );
}

/* ── generate_variants 필드 스팬: LLM 입출력 JSON을 핵심 요소 막대로 분해 ──────
   draft_problem / author_solution 출력 JSON에서 prompts.py 규칙에 대응하는 핵심
   요소를 뽑아 라벨+막대+제약검사로 보여준다. 어떤 요소가 요건을 못 채워 후보가
   탈락했는지가 막대 색(ok 초록 / warn 주황 / bad 빨강)으로 즉시 드러난다.
   규칙 동기화(authoring_engine/authoring/pipeline/prompts.py · jcq_shared IntentRubric):
   - draft: intent_rubric 필수 4 필드(expected_approach·expected_complexity·
     key_insight·one_line_summary) 중 하나라도 비면 IntentRubric 검증 실패로 폐기.
     must_handle·forbidden_patterns는 품질 신호(≥1 권장, 기본 []이라 폐기 사유는 아님).
   - solution: test_inputs ≥ 5 (절대 요건), is_sample 정확히 1개, reference_code 비어있지 않음. */
type FieldTone = "ok" | "warn" | "bad" | "neutral";
interface FieldSpan { label: string; display: string; ratio: number; tone: FieldTone; hint?: string }
interface GenFields { kind: "draft" | "solution"; fields: FieldSpan[]; blockers: string[] }

const RUBRIC_REQUIRED = ["expected_approach", "expected_complexity", "key_insight", "one_line_summary"] as const;
const MIN_TESTS = 5;
const GEN_KIND_LABEL: Record<string, string> = { draft: "draft_problem", solution: "author_solution" };

const _clamp01 = (n: number) => (n < 0 ? 0 : n > 1 ? 1 : n);
const _isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const _gstr = (v: unknown) => (typeof v === "string" ? v : "");
const _garr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const _filled = (v: unknown) => typeof v === "string" && v.trim().length > 0;

/* 출력 JSON 모양으로 draft/solution 판별 — 다른 노드(judge/compare 등) 출력과 겹치지 않는다. */
function genKindOf(obj: unknown): "draft" | "solution" | null {
  if (!_isObj(obj)) return null;
  if ("reference_code" in obj || "test_inputs" in obj) return "solution";
  if ("intent_rubric" in obj || ("title" in obj && "statement" in obj)) return "draft";
  return null;
}

function draftFields(obj: Record<string, unknown>): GenFields {
  const blockers: string[] = [];
  const title = _gstr(obj.title);
  const statement = _gstr(obj.statement);
  const rubric = _isObj(obj.intent_rubric) ? obj.intent_rubric : {};
  const missing = RUBRIC_REQUIRED.filter((k) => !_filled(rubric[k]));
  const present = RUBRIC_REQUIRED.length - missing.length;
  const mustN = _garr(rubric.must_handle).length;
  const forbN = _garr(rubric.forbidden_patterns).length;

  if (!title.trim()) blockers.push("title 비어 있음");
  if (missing.length) blockers.push(`intent_rubric 필수 필드 누락(${missing.join(", ")}) → 검증 실패로 폐기`);

  const fields: FieldSpan[] = [
    {
      label: "intent_rubric 필수", display: `${present} / ${RUBRIC_REQUIRED.length}`,
      ratio: present / RUBRIC_REQUIRED.length, tone: missing.length ? "bad" : "ok",
      hint: missing.length ? `누락: ${missing.join(", ")} — IntentRubric 검증 실패로 후보 폐기` : undefined,
    },
    {
      label: "statement 길이", display: `${statement.length.toLocaleString()}자`,
      ratio: _clamp01(statement.length / 1200),
      tone: statement.length < 80 ? "bad" : statement.length < 300 ? "warn" : "ok",
      hint: statement.length < 80 ? "본문이 너무 짧음 — 입출력 형식/제약 누락 의심" : undefined,
    },
    { label: "title 길이", display: title ? `${title.length}자` : "없음", ratio: _clamp01(title.length / 30), tone: title.trim() ? "ok" : "bad" },
    {
      label: "must_handle", display: `${mustN}개`, ratio: _clamp01(mustN / 4), tone: mustN >= 1 ? "ok" : "warn",
      hint: mustN === 0 ? "엣지 케이스 미정의 — 이후 judge/attack 게이트 탈락 위험" : undefined,
    },
    {
      label: "forbidden_patterns", display: `${forbN}개`, ratio: _clamp01(forbN / 4), tone: forbN >= 1 ? "ok" : "warn",
      hint: forbN === 0 ? "안티패턴 미정의 — 채점 변별력 약화" : undefined,
    },
  ];
  return { kind: "draft", fields, blockers };
}

function solutionFields(obj: Record<string, unknown>): GenFields {
  const blockers: string[] = [];
  const code = _gstr(obj.reference_code);
  const tests = _garr(obj.test_inputs);
  const sampleN = tests.filter((t) => _isObj(t) && t.is_sample === true).length;
  const codeLines = code ? code.split("\n").length : 0;

  if (!code.trim()) blockers.push("reference_code 비어 있음");
  if (tests.length < MIN_TESTS) blockers.push(`test_inputs ${tests.length}개 (< ${MIN_TESTS} 절대 요건)`);

  const fields: FieldSpan[] = [
    {
      label: "test_inputs", display: `${tests.length}개`, ratio: _clamp01(tests.length / 8),
      tone: tests.length >= MIN_TESTS ? "ok" : "bad",
      hint: tests.length < MIN_TESTS ? `${MIN_TESTS}개 이상 필요(절대 요건) — 부족 시 폐기` : undefined,
    },
    {
      label: "is_sample 수", display: `${sampleN}개`, ratio: _clamp01(sampleN / 2),
      tone: sampleN === 1 ? "ok" : sampleN === 0 ? "bad" : "warn",
      hint: sampleN === 1 ? undefined : sampleN === 0 ? "예제 0개 — 학생 노출 샘플 없음" : "예제 과다 — 정확히 1개 권장",
    },
    {
      label: "reference_code", display: code ? `${codeLines}줄` : "없음", ratio: _clamp01(code.length / 2000),
      tone: code.trim() ? "ok" : "bad", hint: code.trim() ? undefined : "레퍼런스 코드 없음 — verify 단계에서 실패",
    },
  ];
  return { kind: "solution", fields, blockers };
}

function extractGenFields(obj: unknown): GenFields | null {
  const kind = genKindOf(obj);
  if (kind === "draft") return draftFields(obj as Record<string, unknown>);
  if (kind === "solution") return solutionFields(obj as Record<string, unknown>);
  return null;
}

/* draft/solution 입력 프롬프트(텍스트)에서 요청 파라미터를 best-effort로 추출 — 칩으로 표시.
   DRAFT_USER/SOLUTION_USER 템플릿이 고정 형식이라 정규식이 안전하고, 못 찾으면 그 칩은 생략. */
function genInputSpans(kind: "draft" | "solution", msgs: ChatMsg[]): FieldSpan[] {
  const userMsg = msgs.filter((m) => m.role === "user").map((m) => m.content).join("\n");
  if (!userMsg) return [];
  const grab = (re: RegExp) => userMsg.match(re)?.[1]?.trim();
  const out: FieldSpan[] = [];
  if (kind === "draft") {
    const vi = grab(/variant index:\s*(\d+)/i); if (vi) out.push({ label: "변형 #", display: vi, ratio: 0, tone: "neutral" });
    const cat = grab(/category:\s*([^\n]+)/i); if (cat) out.push({ label: "category", display: cat, ratio: 0, tone: "neutral" });
    const lvl = grab(/level:\s*([^\n]+)/i); if (lvl) out.push({ label: "level", display: lvl, ratio: 0, tone: "neutral" });
    out.push({ label: "grounding", display: userMsg.includes("Reference problems in the same category") ? "RAG exemplar" : "seed 폴백", ratio: 0, tone: "neutral" });
    if (userMsg.includes("[NOVELTY]")) out.push({ label: "novelty 재draft", display: "재시도", ratio: 0, tone: "warn", hint: "이전 draft가 기존 문제와 유사해 재생성됨" });
  } else {
    const cmp = grab(/expected_complexity[^\n:]*:\s*([^\n]+)/i); if (cmp) out.push({ label: "expected_complexity", display: cmp, ratio: 0, tone: "neutral" });
    const mh = grab(/must_handle:\s*([^\n]*)/i);
    const mhN = mh ? mh.split(",").filter((s) => s.trim()).length : 0;
    out.push({ label: "must_handle 전달", display: `${mhN}개`, ratio: 0, tone: mhN ? "neutral" : "warn", hint: mhN ? undefined : "전달된 엣지 케이스 없음 — solution이 커버할 케이스 부재" });
  }
  return out;
}

/* 핵심 요소 막대 묶음 — 라벨/막대/값 + 위반 사유 힌트. */
function FieldBars({ gf }: { gf: GenFields }) {
  const hints = gf.fields.filter((f) => f.hint);
  return (
    <div className="fspans">
      <div className="fspans-head">
        <span className={`fspan-kind ${gf.kind}`}>{GEN_KIND_LABEL[gf.kind]}</span>
        {gf.blockers.length === 0
          ? <span className="fspan-verdict ok">구조 합격</span>
          : <span className="fspan-verdict bad">탈락 요인 {gf.blockers.length}</span>}
      </div>
      <div className="fspan-list">
        {gf.fields.map((f, i) => (
          <div className="fspan" key={i}>
            <span className="fspan-label">{f.label}</span>
            <div className="fspan-track"><div className={`fspan-fill ${f.tone}`} style={{ width: `${Math.max(f.ratio * 100, f.ratio > 0 ? 4 : 0)}%` }} /></div>
            <span className={`fspan-val ${f.tone}`}>{f.display}</span>
          </div>
        ))}
      </div>
      {hints.length > 0 && (
        <ul className="fspan-hints">
          {hints.map((f, i) => <li key={i} className={f.tone}><b>{f.label}</b> · {f.hint}</li>)}
        </ul>
      )}
    </div>
  );
}

/* 입력 컨텍스트 칩 묶음 (categorical — 막대 대신 칩). */
function FieldChips({ spans }: { spans: FieldSpan[] }) {
  if (!spans.length) return null;
  return (
    <div className="fchips">
      {spans.map((s, i) => (
        <span key={i} className={`fchip ${s.tone}`} title={s.hint}><b>{s.label}</b> {s.display}</span>
      ))}
    </div>
  );
}

/* 입력 프롬프트로 draft/solution 호출을 판별 — 출력 JSON이 깨져도 '어떤 호출인지'는 알 수 있다.
   DRAFT_*엔 [Target]/variant index, SOLUTION_*엔 reference_code/[Intent specification]가 들어간다. */
function genCallKind(span: SpanT): "draft" | "solution" | null {
  const msgs = findMessages(span.inputs);
  const text = msgs ? msgs.map((m) => m.content).join("\n") : "";
  if (/reference_code|\[Intent specification\]|test_inputs/i.test(text)) return "solution";
  if (/\[Target\]|variant index/i.test(text)) return "draft";
  return genKindOf(tryParseJson(findCompletion(span.outputs) ?? "")); // 폴백: 출력 모양
}

type DiagStatus = "ok" | "blocked" | "parsefail" | "nooutput" | "badshape" | "error";
function diagLabel(status: DiagStatus, n: number): string {
  switch (status) {
    case "ok": return "✓ 구조 합격";
    case "parsefail": return "✗ JSON 파싱 실패";
    case "nooutput": return "✗ 출력 없음";
    case "badshape": return "⚠ 예상 밖 구조";
    case "error": return "✗ LLM 에러";
    default: return `✗ 탈락 요인 ${n}`;
  }
}

/* generate_variants 전용 — 노드의 모든 LLM span을 호출별로 진단해 보여주는 배너.
   핵심: ① 호출을 절대 누락하지 않는다(분류 실패도 행으로 노출), ② 입력 프롬프트로 호출 종류를
   식별해 출력이 깨져도 draft/solution을 라벨링, ③ 노드가 후보 0개(BLOCKED)면 호출이 다 정상
   보여도 무조건 실패(빨강)로 표시한다 — 후보가 안 만들어졌다는 사실이 진단의 ground truth다. */
function GenVariantsDiagnosis({ spans, candidatesOut }: { spans: SpanT[]; candidatesOut: number | null }) {
  type DiagRow = { kind: string; status: DiagStatus; blockers: string[]; error?: string };
  const rows: DiagRow[] = [];
  for (const s of spans) {
    if (s.run_type !== "llm") continue;
    const label = GEN_KIND_LABEL[genCallKind(s) ?? ""] ?? "LLM 호출";
    if (s.error) { rows.push({ kind: label, status: "error", blockers: [], error: s.error }); continue; }
    const comp = findCompletion(s.outputs);
    if (comp == null || comp.trim() === "") {
      rows.push({ kind: label, status: "nooutput", blockers: ["LLM이 응답을 반환하지 않음 — 타임아웃/중단 가능"] });
      continue;
    }
    const cj = tryParseJson(comp);
    if (!cj) {
      rows.push({ kind: label, status: "parsefail", blockers: [`출력이 JSON으로 파싱되지 않음 → _clean_json 단계에서 폐기 (${comp.length.toLocaleString()}자 · 응답 잘림/잡텍스트 의심)`] });
      continue;
    }
    const gf = extractGenFields(cj);
    if (!gf) { rows.push({ kind: label, status: "badshape", blockers: ["JSON이지만 draft/solution 구조가 아님 — 핵심 키 누락 의심"] }); continue; }
    rows.push({ kind: GEN_KIND_LABEL[gf.kind], status: gf.blockers.length ? "blocked" : "ok", blockers: gf.blockers });
  }
  if (!rows.length) return null;

  const bad = rows.filter((r) => r.status !== "ok");
  const producedNothing = candidatesOut === 0;
  const failed = producedNothing || bad.length > 0;
  // 모든 LLM 호출은 정상인데 후보 0개 → 사유는 노드 내부 단계(주로 author_solution 파싱/검증)에 있음.
  const silentDrop = producedNothing && bad.length === 0;

  return (
    <div className={`gen-diag ${failed ? "has-block" : "clean"}`}>
      <div className="gen-diag-head">
        <span className="gen-diag-title">출제 실패 진단</span>
        {!failed
          ? <span className="gen-diag-chip ok">구조 위반 없음 · {rows.length} 호출</span>
          : producedNothing
            ? <span className="gen-diag-chip bad">후보 0개 · BLOCKED</span>
            : <span className="gen-diag-chip bad">{bad.length} / {rows.length} 호출에서 탈락 요인</span>}
      </div>
      {producedNothing && (
        <div className="gen-diag-summary">
          이 노드는 후보를 <b>0개</b> 생성해 <code>_route_after_generate</code>가 곧바로 END로 보냈습니다
          {bad.length > 0
            ? <> — 아래 <b>{bad.length}개 호출</b>의 출력이 폐기됐습니다.</>
            : silentDrop
              ? <> — LLM 출력은 형식상 정상이라 사유는 노드 내부(주로 author_solution 파싱/검증)에 있습니다. 아래 raw 출력 또는 run errors를 확인하세요.</>
              : null}
        </div>
      )}
      <div className="gen-diag-rows">
        {rows.map((r, i) => (
          <div key={i} className={`gen-diag-row ${r.status}`}>
            <span className="gen-diag-kind">{r.kind}</span>
            <span className={`gen-diag-st ${r.status}`}>{diagLabel(r.status, r.blockers.length)}</span>
            {(r.blockers.length > 0 || r.error) && (
              <ul className="gen-diag-blockers">
                {r.blockers.map((b, j) => <li key={j}>{b}</li>)}
                {r.error && <li>{r.error.slice(0, 160)}</li>}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── persist_approved 전용: 후보를 생성/탈락으로 분류 ──────────────────── */
type Cand = Record<string, unknown>;
const _snum = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/* persist span의 inputs/outputs에서 candidates 배열을 찾는다. */
function findCandidates(span: SpanT): Cand[] | null {
  for (const src of [span.outputs, span.inputs]) {
    const c = src && (src as Record<string, unknown>).candidates;
    if (Array.isArray(c) && c.length) return c as Cand[];
  }
  return null;
}

/* 탈락 1차 사유 — persist 게이트(solver·discrimination·compare) + judge 순. */
function failReason(c: Cand): string {
  if (c.solver_passed === false) return "풀이 불가 (solve)";
  if (c.discrimination_passed === false) return "테스트 변별력 부족 (attack)";
  if (c.compare_passed === false) return "환각/의도 불일치 (compare)";
  if (c.judge_passed === false) return "품질 미달 (judge)";
  if (c.verify_passed === false) return "레퍼런스 검증 실패 (verify)";
  return "저장 실패";
}

function GateChip({ label, st, val }: { label: string; st: "ok" | "bad" | "na"; val?: number | null }) {
  return (
    <span className={`gate-chip ${st}`}>
      {st === "ok" ? "✓" : st === "bad" ? "✗" : "·"} {label}
      {typeof val === "number" ? ` ${val.toFixed(2)}` : ""}
    </span>
  );
}

function CandRow({ c, saved, onPreview }: { c: Cand; saved: boolean; onPreview?: (c: Cand) => void }) {
  const gate = (k: string): "ok" | "bad" | "na" => (c[k] === true ? "ok" : c[k] === false ? "bad" : "na");
  const hall = _snum(c.comparison_hallucination);
  const intent = _snum(c.comparison_intent_similarity);
  const quality = _snum(c.judge_score);
  const note = (c.comparison_error || c.comparison_rationale) as string | undefined;
  const title = (typeof c.title === "string" && c.title) || `후보 #${c.index ?? "?"}`;
  return (
    <button
      className={`pcand ${saved ? "saved" : "failed"}`}
      onClick={() => onPreview?.(c)}
      title="문제 미리보기 열기"
    >
      <div className="pcand-head">
        <span className="pcand-title">{title}</span>
        {saved
          ? <span className="pcand-tag ok">생성 #{String(c.saved_id)}</span>
          : <span className="pcand-tag bad">탈락 · {failReason(c)}</span>}
      </div>
      <div className="pcand-gates">
        <GateChip label="judge" st={gate("judge_passed")} val={quality} />
        <GateChip label="solve" st={gate("solver_passed")} />
        <GateChip label="attack" st={gate("discrimination_passed")} val={_snum(c.discrimination_score)} />
        <GateChip label="compare" st={gate("compare_passed")} />
      </div>
      {(hall != null || intent != null) && (
        <div className="pcand-metrics">
          {hall != null && <span>환각 {hall.toFixed(2)}</span>}
          {intent != null && <span>의도 {intent.toFixed(2)}</span>}
        </div>
      )}
      {!saved && note && <div className="pcand-note">{note.slice(0, 180)}</div>}
      <span className="pcand-go">문제 미리보기 →</span>
    </button>
  );
}

function PersistClassification({ cands, onPreview }: { cands: Cand[]; onPreview?: (c: Cand) => void }) {
  const savedC = cands.filter((c) => c.saved_id != null);
  const failedC = cands.filter((c) => c.saved_id == null);
  return (
    <div className="persist-class">
      <div className="pclass-group">
        <div className="pclass-head ok">생성 <span className="n">{savedC.length}</span></div>
        {savedC.length
          ? savedC.map((c, i) => <CandRow key={i} c={c} saved onPreview={onPreview} />)
          : <div className="pclass-empty">없음</div>}
      </div>
      <div className="pclass-group">
        <div className="pclass-head bad">탈락 <span className="n">{failedC.length}</span></div>
        {failedC.length
          ? failedC.map((c, i) => <CandRow key={i} c={c} saved={false} onPreview={onPreview} />)
          : <div className="pclass-empty">없음</div>}
      </div>
    </div>
  );
}

/* 후보 → 실제 문제 페이지 미리보기 (학생 화면처럼 statement·예제·제약). */
function ProblemPreview({ cand, onBack }: { cand: Cand; onBack: () => void }) {
  const s = (v: unknown) => (typeof v === "string" ? v : "");
  const title = s(cand.title) || `후보 #${cand.index ?? "?"}`;
  const saved = cand.saved_id != null;
  const tests = (Array.isArray(cand.test_cases) ? cand.test_cases : []) as Record<string, unknown>[];
  let samples = tests.filter((t) => t && t.is_sample === true);
  if (!samples.length) samples = tests.slice(0, 2);
  const refCode = s(cand.reference_code);
  const pts = _snum(cand.points), tl = _snum(cand.time_limit_ms), mem = _snum(cand.memory_limit_mb);
  return (
    <div className="prob-preview">
      <div className="prob-preview-bar">
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← 후보 목록</button>
        {saved
          ? <span className="pcand-tag ok">생성 #{String(cand.saved_id)}</span>
          : <span className="pcand-tag bad">탈락 후보 · 미리보기</span>}
      </div>
      <article className="prob-doc">
        <h1 className="prob-title">{title}</h1>
        <div className="prob-meta">
          {s(cand.category) && <span className="prob-chip cat">{s(cand.category)}</span>}
          {s(cand.level) && <span className="prob-chip lvl">{s(cand.level)}</span>}
          {pts != null && <span className="prob-meta-item">{pts}점</span>}
          {tl != null && <span className="prob-meta-item">{tl}ms</span>}
          {mem != null && <span className="prob-meta-item">{mem}MB</span>}
        </div>
        <section className="prob-section">
          <h3>문제</h3>
          <div className="prob-statement">{s(cand.statement) || "—"}</div>
        </section>
        {samples.length > 0 && (
          <section className="prob-section">
            <h3>예제</h3>
            <div className="prob-samples">
              {samples.map((t, i) => (
                <div className="prob-sample" key={i}>
                  <div className="prob-sample-col">
                    <div className="prob-io-label">입력 {i + 1}</div>
                    <pre className="prob-io">{s(t.stdin) || "—"}</pre>
                  </div>
                  <div className="prob-sample-col">
                    <div className="prob-io-label">출력 {i + 1}</div>
                    <pre className="prob-io">{s(t.expected_stdout) || "—"}</pre>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
        {refCode && (
          <details className="prob-section prob-ref">
            <summary>레퍼런스 코드</summary>
            <pre className="prob-code">{refCode}</pre>
          </details>
        )}
      </article>
    </div>
  );
}

/* 한 span의 I/O 카드 — 헤더 클릭으로 카드 전체를 접고 폄(길이 조절).
   persist_approved는 생성/탈락 분류, LLM이면 프롬프트/완성, 그 외 JSON. raw 토글 제공. */
function SpanCard({ span, depth, onPreview }: { span: SpanT; depth: number; onPreview?: (c: Cand) => void }) {
  const tok = span.tokens?.total ?? 0;
  const isLlm = span.run_type === "llm";
  const msgs = isLlm ? findMessages(span.inputs) : null;
  const completion = isLlm ? findCompletion(span.outputs) : null;
  const pretty = msgs != null || completion != null;
  // persist_approved span은 후보 생성/탈락 분류 뷰로 특별 처리
  const persistCands = span.name === "persist_approved" ? findCandidates(span) : null;
  // LLM/persist/에러 span은 기본 펼침(흥미로운 내용), 래퍼 chain은 기본 접힘 → 목록이 간결.
  const [open, setOpen] = useState(isLlm || !!span.error || persistCands != null);

  return (
    <div className={`span-card${open ? " open" : ""}`} style={{ marginLeft: depth * 12 }}>
      <button className="span-card-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="span-chevron"><Icon.Chevron /></span>
        <span className={`span-type ${isLlm ? "llm" : ""}`}>{span.run_type}</span>
        <span className="span-name">{span.name}</span>
        <span className="span-card-meta">
          {span.latency_seconds != null && <span>{span.latency_seconds.toFixed(2)}s</span>}
          {tok > 0 && <span>{fmtTokens(tok)} tok</span>}
        </span>
      </button>

      {open && (
        <div className="span-card-body">
          {span.error && <CodeBlock text={span.error} kind="error" />}

          {persistCands ? (
            <>
              <PersistClassification cands={persistCands} onPreview={onPreview} />
              <details className="span-io span-raw"><summary>raw JSON</summary>
                <div className="span-io-label" style={{ marginTop: 6 }}>inputs</div>
                <CodeBlock text={jsonPreview(span.inputs)} />
                <div className="span-io-label">outputs</div>
                <CodeBlock text={jsonPreview(span.outputs)} />
              </details>
            </>
          ) : pretty ? (() => {
            const cj = completion != null ? tryParseJson(completion) : null;
            const gf = cj ? extractGenFields(cj) : null;          // generate_variants 출력이면 필드 분해
            const inSpans = gf && msgs ? genInputSpans(gf.kind, msgs) : [];
            return (
            <>
              {msgs && (
                <IOBlock dir="in" label={`Input · prompt (${msgs.length} messages)`}>
                  {inSpans.length > 0 && <FieldChips spans={inSpans} />}
                  <ChatView messages={msgs} />
                </IOBlock>
              )}
              {completion != null && (
                <IOBlock dir="out" label={cj ? (gf ? `Output · 필드 분석 — ${GEN_KIND_LABEL[gf.kind]}` : "Output · completion (구조화)") : "Output · completion"}>
                  {gf && <FieldBars gf={gf} />}
                  {cj ? <StructuredJson data={cj} /> : <CodeBlock text={completion || "—"} />}
                </IOBlock>
              )}
              <details className="span-io span-raw"><summary>raw JSON</summary>
                <div className="span-io-label" style={{ marginTop: 6 }}>inputs</div>
                <CodeBlock text={jsonPreview(span.inputs)} />
                <div className="span-io-label">outputs</div>
                <CodeBlock text={jsonPreview(span.outputs)} />
              </details>
            </>
            );
          })() : (
            <>
              <IOBlock dir="in" label="Input"><IOValue v={span.inputs} /></IOBlock>
              <IOBlock dir="out" label="Output"><IOValue v={span.outputs} /></IOBlock>
              <details className="span-io span-raw"><summary>raw JSON</summary>
                <div className="span-io-label" style={{ marginTop: 6 }}>inputs</div>
                <CodeBlock text={jsonPreview(span.inputs)} />
                <div className="span-io-label">outputs</div>
                <CodeBlock text={jsonPreview(span.outputs)} />
              </details>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function NodeDrawer({
  detail, nodeKey, judgeFilter, onClose, onRetry, traceId, spans, onLoadSpans, wide, onToggleWide,
}: {
  detail: RunDetailT;
  nodeKey: string;
  judgeFilter?: string | null;
  onClose: () => void;
  onRetry: () => void;
  traceId?: string | null;
  spans?: SpansState;
  onLoadSpans: (traceId: string) => void;
  wide: boolean;
  onToggleWide: () => void;
}) {
  const def = NODE_DEFS.find((n) => n.key === nodeKey);
  const state = detail.node_states?.[nodeKey] ?? { status: "queued" };
  const dStatus = deriveNodeStatuses(detail)[nodeKey] ?? state.status;
  const [tab, setTab] = useState("overview");
  const [collapsed, setCollapsed] = useState(false);
  const [preview, setPreview] = useState<Cand | null>(null);
  const prevPreviewOpen = useRef(false);
  // 판사 서브노드를 선택해 열면 해당 LLM I/O가 핵심이므로 inputs/outputs 탭으로 시작.
  useEffect(() => { setTab(judgeFilter ? "inputs/outputs" : "overview"); setCollapsed(false); setPreview(null); }, [nodeKey, judgeFilter]);
  // inputs/outputs 탭을 열면 그때 trace span을 lazy 로드 (LangSmith가 느릴 수 있어 on-demand).
  useEffect(() => {
    if (tab === "inputs/outputs" && !collapsed && traceId && spans == null) onLoadSpans(traceId);
  }, [tab, collapsed, traceId, spans, onLoadSpans]);
  // 미리보기를 '열 때 한 번만' 드로어를 넓힌다 — 이후 사용자가 좁히면 그대로 둔다.
  useEffect(() => {
    const isOpen = preview != null;
    if (isOpen && !prevPreviewOpen.current && !wide) onToggleWide();
    prevPreviewOpen.current = isOpen;
  }, [preview, wide, onToggleWide]);
  if (!def) return null;

  const tokens = state.tokens ?? {};
  const tokTotal = tokens.total ?? 0;
  const tabs = ["overview", "candidates", state.error ? "error" : "inputs/outputs", "logs"];

  // 활성 탭을 다시 누르면 내용 패널 접기/펴기 토글, 다른 탭은 그 탭으로 펼치며 전환.
  function onTabClick(t: string) {
    if (t === tab) setCollapsed((c) => !c);
    else { setTab(t); setCollapsed(false); }
  }

  return (
    <div className="drawer">
      <div className="drawer-head">
        <div className="drawer-kind-ico"><NodeKindIcon kind={def.kind} /></div>
        <div className="drawer-head-body">
          <h3 className="drawer-name">
            {def.label}
            {judgeFilter && <span className="judge-badge"><Icon.LLM /> {judgeFilter}</span>}
          </h3>
          <div className="drawer-meta">
            <span className={`pill ${dStatus}`}><span className="dot" />{dStatus}</span>
            {dStatus !== state.status && <span className="raw-status">실행: {state.status}</span>}
            <span>
              {judgeFilter
                ? `${judgeFilter} 판사 LLM`
                : def.kind === "llm" ? "LLM 노드" : def.kind === "db" ? "DB I/O" : "sandbox"}
              {def.side ? " · side-step" : ""}
            </span>
          </div>
        </div>
        <div className="drawer-head-actions">
          <button className="drawer-close" onClick={onToggleWide} title={wide ? "드로어 좁히기" : "드로어 넓히기"}>
            {wide ? <Icon.Collapse /> : <Icon.Expand />}
          </button>
          <button className="drawer-close" onClick={onClose} title="닫기"><Icon.Close /></button>
        </div>
      </div>

      {preview && <ProblemPreview cand={preview} onBack={() => setPreview(null)} />}

      <div className="drawer-main" hidden={!!preview}>
      <div className="drawer-tabs">
        {tabs.map((t) => {
          const active = tab === t;
          return (
            <button
              key={t}
              className={`drawer-tab${active ? " active" : ""}${active && collapsed ? " collapsed" : ""}`}
              onClick={() => onTabClick(t)}
              title={active ? (collapsed ? "내용 펼치기" : "내용 접기") : t}
            >
              {t}
              {active && <span className="drawer-tab-caret"><Icon.Chevron /></span>}
            </button>
          );
        })}
      </div>

      {collapsed && (
        <button className="drawer-collapsed-hint" onClick={() => setCollapsed(false)}>
          <span className="drawer-tab-caret"><Icon.Chevron /></span> {tab} 내용이 접혔습니다 — 탭을 눌러 펼치기
        </button>
      )}

      <div className="drawer-body" hidden={collapsed}>
        {tab === "overview" && (
          <>
            <p style={{ margin: "0 0 16px", color: "var(--muted)", fontSize: 13, lineHeight: 1.6 }}>{def.note}</p>
            <div className="section-title">실행</div>
            <dl className="kv">
              <dt>status</dt><dd>{dStatus}{dStatus !== state.status ? ` (실행: ${state.status})` : ""}</dd>
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
          const allSpans = ready ? collectNodeSpans(ready.spans, nodeKey) : [];
          // 판사가 선택되면 그 판사의 LLM span만 (trace run_name: judge_quality/{id}#n)
          const nodeSpans = judgeFilter
            ? allSpans.filter((s) => s.name !== nodeKey && s.name.toLowerCase().includes(judgeFilter.toLowerCase()))
            : allSpans;
          const ioLabel = judgeFilter ? `${judgeFilter} 판사 LLM I/O` : `LangSmith 노드 I/O`;
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

              {/* generate_variants 전용 — draft/solution 호출별 구조 위반 한눈 진단 */}
              {ready && nodeKey === "generate_variants" && !judgeFilter && nodeSpans.length > 0 && (
                <GenVariantsDiagnosis spans={nodeSpans} candidatesOut={state.candidates_out ?? null} />
              )}

              {/* 성공 — 이 노드(또는 선택 판사)의 span I/O */}
              {ready && nodeSpans.length > 0 && (
                <>
                  <div className="section-title">{ioLabel} ({nodeSpans.length} spans)</div>
                  <div className="span-tree">
                    {nodeSpans.map((s) => (
                      <SpanCard key={s.id} span={s} depth={!judgeFilter && s.name === nodeKey ? 0 : 1} onPreview={setPreview} />
                    ))}
                  </div>
                </>
              )}
              {ready && nodeSpans.length === 0 && (
                <div className="ls-note">
                  {judgeFilter
                    ? `${judgeFilter} 판사의 LLM span을 찾지 못했어요 — trace 미인제스트이거나 이 run이 해당 판사를 호출하지 않았습니다.`
                    : "이 노드의 span이 trace에 없어요 (DB/sandbox 노드는 LLM span이 없을 수 있음)."}
                </div>
              )}

              {/* 폴백/보조 — DB 스냅샷 outputs_preview (노드 단위, 판사 뷰에선 숨김) */}
              {!judgeFilter && state.outputs_preview && (
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
  const [selectedJudge, setSelectedJudge] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [copied, setCopied] = useState(false);
  const [drawerWide, setDrawerWide] = useState(false);
  const [pendingDel, setPendingDel] = useState<PendingDelete | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
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

  function clearSelectionIfGone(stillPresent: (id: string) => boolean) {
    if (selectedId && !stillPresent(selectedId)) {
      streamRef.current?.abort();
      setSelectedId(null);
      setDetail(null);
      setSelectedNode(null);
    }
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  function exitSelect() {
    setSelectMode(false);
    setSelectedIds(new Set());
  }

  async function confirmDelete() {
    if (!pendingDel) return;
    setDeleting(true);
    setError("");
    try {
      if (pendingDel.kind === "one") {
        const id = pendingDel.id;
        const r = await adminFetch(`/api/runs/${id}`, settings, { method: "DELETE" });
        if (!r.ok && r.status !== 404) { setError(`[${r.status}] ${(await r.text()).slice(0, 200)}`); return; }
        setRuns((prev) => prev.filter((x) => x.id !== id));
        clearSelectionIfGone((sid) => sid !== id);
      } else {
        const ids = pendingDel.ids;
        const r = await adminFetch(`/api/runs/delete`, settings, {
          method: "POST",
          body: JSON.stringify({ ids }),
        });
        if (!r.ok) { setError(`[${r.status}] ${(await r.text()).slice(0, 200)}`); return; }
        const del = new Set(ids);
        setRuns((prev) => prev.filter((x) => !del.has(x.id)));
        clearSelectionIfGone((sid) => !del.has(sid));
        exitSelect();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDeleting(false);
      setPendingDel(null);
    }
  }

  const drawerOpen = selectedNode != null && detail != null;

  return (
    <div className={`main runs${drawerOpen ? " drawer-open" : ""}${drawerOpen && drawerWide ? " drawer-wide" : ""}`}>
      <RunsSidebar
        runs={runs}
        selectedId={selectedId}
        onSelect={selectRun}
        onNew={() => { setShowNew(true); setSelectedNode(null); }}
        onRequestDelete={(r) => setPendingDel({ kind: "one", id: r.id, title: `#${r.problem_id ?? "?"} ${r.problem_title ?? r.id.slice(0, 12)}` })}
        selectMode={selectMode}
        selectedIds={selectedIds}
        onEnterSelect={() => { setSelectMode(true); setSelectedIds(new Set()); }}
        onExitSelect={exitSelect}
        onToggleSelect={toggleSelect}
        onSetSelection={(ids) => setSelectedIds(new Set(ids))}
        onDeleteSelected={() => { if (selectedIds.size > 0) setPendingDel({ kind: "many", ids: [...selectedIds] }); }}
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

        {detail && !showNew && <RunOutcomeBanner detail={detail} />}

        <div className="graph-canvas">
          {showNew || !detail ? (
            <div style={{ display: "flex", height: "100%", padding: 40 }}>
              <NewRunForm onStart={beginRun} onCancel={() => { setShowNew(false); if (selectedId) loadDetail(selectedId); }} />
            </div>
          ) : (
            <PipelineGraph
              detail={detail}
              selectedNode={selectedNode}
              selectedJudge={selectedJudge}
              onSelectNode={(k) => { setSelectedNode(k); setSelectedJudge(null); }}
              onSelectJudge={(k, j) => { setSelectedNode(k); setSelectedJudge(j); }}
              zoom={zoom}
            />
          )}
        </div>

        {error && <div className="output-panel err" style={{ margin: 12 }}>{error}</div>}
      </div>

      {drawerOpen && (
        <NodeDrawer
          detail={detail!}
          nodeKey={selectedNode!}
          judgeFilter={selectedJudge}
          onClose={() => { setSelectedNode(null); setSelectedJudge(null); }}
          onRetry={retryRun}
          traceId={detail!.trace_id}
          spans={detail!.trace_id ? spansCache[detail!.trace_id] : undefined}
          onLoadSpans={loadSpans}
          wide={drawerWide}
          onToggleWide={() => setDrawerWide((w) => !w)}
        />
      )}

      {pendingDel && (
        <div className="confirm-overlay" onClick={() => !deleting && setPendingDel(null)}>
          <div className="confirm-card" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-ico"><Icon.Trash /></div>
            <h4>
              {pendingDel.kind === "one"
                ? "이 run을 삭제할까요?"
                : `선택한 run ${pendingDel.ids.length}개를 삭제할까요?`}
            </h4>
            <p className="confirm-sub">
              {pendingDel.kind === "one"
                ? pendingDel.title
                : "선택한 run 기록이 모두 삭제됩니다."}
              <br />삭제하면 되돌릴 수 없습니다.
            </p>
            <div className="confirm-actions">
              <button className="btn btn-outline btn-sm" disabled={deleting} onClick={() => setPendingDel(null)}>취소</button>
              <button className="btn btn-danger btn-sm" disabled={deleting} onClick={confirmDelete}>
                {deleting ? "삭제 중…" : "삭제"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
