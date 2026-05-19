import { useState, useCallback, useEffect, useMemo } from "react";
import type { ConnSettings, VerdictsResponse, JudgesResponse, ProblemRow } from "../types";
import { judgeFetch, adminFetch } from "../api";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid, Cell,
} from "recharts";
import ComparisonTab from "../components/ComparisonTab";

interface Props { settings: ConnSettings }

type StatsTab = "problems" | "comparison";

const JUDGE_COLORS: Record<string, string> = {
  Melchior:  "#0DA5E8",
  Balthasar: "#16a34a",
  Casper:    "#d97706",
};
function colorFor(jid: string, i: number) {
  return JUDGE_COLORS[jid] ?? ["#7c3aed", "#db2777", "#06b6d4"][i % 3];
}

const TOOLTIP_STYLE = {
  background: "#fff",
  border: "1px solid #e2e8f0",
  borderRadius: 6,
  fontSize: 12,
  color: "#0f172a",
  boxShadow: "0 4px 6px -1px rgba(0,0,0,.1)",
};
const TICK_STYLE = { fill: "#64748b", fontSize: 11 };

/* ──────────────────────────────────────────────────────────── */
interface ProblemStat {
  problem: ProblemRow;
  verdicts: VerdictsResponse;
  judges: JudgesResponse;
  /* aggregated metrics */
  total: number;
  ac: number;
  sus: number;
  failed: number;
  pending: number;
  acRate: number;          // ac / total
  totalWithVotes: number;
  unanimous: number;
  split: number;
  unanimousRate: number;   // unanimous / totalWithVotes
  perJudge: Record<string, { ac: number; sus: number; agree: number; agreeRate: number }>;
  avgAgreeRate: number;    // mean of agreeRate across judges
}

function aggregate(p: ProblemRow, v: VerdictsResponse, j: JudgesResponse): ProblemStat {
  const totals = v.series.reduce(
    (a, b) => ({
      total: a.total + b.total,
      ac: a.ac + b.ac,
      sus: a.sus + b.sus,
      failed: a.failed + b.failed,
      pending: a.pending + b.pending,
    }),
    { total: 0, ac: 0, sus: 0, failed: 0, pending: 0 }
  );

  const jt = j.series.reduce(
    (a, b) => ({
      totalWithVotes: a.totalWithVotes + b.total_with_votes,
      unanimous: a.unanimous + b.unanimous,
      split: a.split + b.split,
    }),
    { totalWithVotes: 0, unanimous: 0, split: 0 }
  );

  const perJudge: ProblemStat["perJudge"] = {};
  for (const jid of j.judge_ids) {
    let ac = 0, sus = 0, agree = 0;
    for (const b of j.series) {
      const e = b.judges[jid];
      if (!e) continue;
      ac += e.ac; sus += e.sus; agree += e.agree_with_final;
    }
    perJudge[jid] = {
      ac, sus, agree,
      agreeRate: jt.totalWithVotes > 0 ? agree / jt.totalWithVotes : 0,
    };
  }

  const judgeRates = Object.values(perJudge).map((x) => x.agreeRate);
  const avgAgreeRate = judgeRates.length
    ? judgeRates.reduce((a, b) => a + b, 0) / judgeRates.length
    : 0;

  return {
    problem: p,
    verdicts: v,
    judges: j,
    ...totals,
    acRate: totals.total > 0 ? totals.ac / totals.total : 0,
    ...jt,
    unanimousRate: jt.totalWithVotes > 0 ? jt.unanimous / jt.totalWithVotes : 0,
    perJudge,
    avgAgreeRate,
  };
}

/* ──────────────────────────────────────────────────────────── */
type SortKey = "title" | "total" | "acRate" | "avgAgreeRate" | "unanimousRate";

function ProblemDetail({ stat }: { stat: ProblemStat }) {
  /* 1) 판정 현황 — single horizontal stacked bar */
  const verdictData = [{
    name: "judgments",
    AC: stat.ac, SUS: stat.sus, failed: stat.failed, pending: stat.pending,
  }];

  /* 2) 모델별 일치율 — horizontal bar per judge */
  const agreeData = Object.entries(stat.perJudge).map(([jid, m]) => ({
    name: jid, rate: +(m.agreeRate * 100).toFixed(1),
  }));

  /* 3) 투표 분포 */
  const splitData = [{ name: "votes", unanimous: stat.unanimous, split: stat.split }];

  /* 4) LLM as Judge — AC / SUS 누적 */
  const judgeRawData = Object.entries(stat.perJudge).map(([jid, m]) => ({
    name: jid, AC: m.ac, SUS: m.sus,
  }));

  const hasJudgeData = stat.totalWithVotes > 0;

  return (
    <div style={{ padding: "16px 20px 20px", background: "var(--bg)" }}>
      <div className="grid-2">
        {/* 판정 현황 */}
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-title">
            <span className="card-icon">▸</span> 판정 현황
            <span className="spacer" />
            <span className="text-mono text-sm text-muted">total={stat.total}</span>
          </div>
          {stat.total === 0 ? (
            <div className="text-muted text-sm" style={{ padding: "24px 0", textAlign: "center" }}>
              제출 기록 없음
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={80}>
              <BarChart layout="vertical" data={verdictData}
                margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                <XAxis type="number" tick={TICK_STYLE} />
                <YAxis type="category" dataKey="name" hide />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="AC"      stackId="a" fill="#16a34a" />
                <Bar dataKey="SUS"     stackId="a" fill="#d97706" />
                <Bar dataKey="failed"  stackId="a" fill="#dc2626" />
                <Bar dataKey="pending" stackId="a" fill="#94a3b8" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* 투표 분포 */}
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-title">
            <span className="card-icon">▸</span> 투표 분포 (3:0 vs 2:1)
            <span className="spacer" />
            <span className="text-mono text-sm text-muted">
              만장일치 {(stat.unanimousRate * 100).toFixed(1)}%
            </span>
          </div>
          {!hasJudgeData ? (
            <div className="text-muted text-sm" style={{ padding: "24px 0", textAlign: "center" }}>
              앙상블 투표 기록 없음
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={80}>
              <BarChart layout="vertical" data={splitData}
                margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                <XAxis type="number" tick={TICK_STYLE} />
                <YAxis type="category" dataKey="name" hide />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="unanimous" name="unanimous (3:0)" stackId="a" fill="#16a34a" />
                <Bar dataKey="split"     name="split (2:1)"     stackId="a" fill="#d97706" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* 모델별 일치율 */}
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-title">
            <span className="card-icon">▸</span> 모델별 최종 판정 일치율
          </div>
          {!hasJudgeData || agreeData.length === 0 ? (
            <div className="text-muted text-sm" style={{ padding: "24px 0", textAlign: "center" }}>
              앙상블 투표 기록 없음
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(140, agreeData.length * 38)}>
              <BarChart layout="vertical" data={agreeData}
                margin={{ top: 4, right: 24, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" domain={[0, 100]}
                  tickFormatter={(v) => `${v}%`} tick={TICK_STYLE} />
                <YAxis type="category" dataKey="name" tick={TICK_STYLE} width={84} />
                <Tooltip contentStyle={TOOLTIP_STYLE}
                  formatter={(v: number) => `${v.toFixed(1)}%`} />
                <Bar dataKey="rate" radius={[0, 3, 3, 0]}>
                  {agreeData.map((d, i) => (
                    <Cell key={i} fill={colorFor(d.name, i)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* LLM as Judge 기록 */}
        <div className="card" style={{ marginBottom: 0 }}>
          <div className="card-title">
            <span className="card-icon">▸</span> LLM-as-Judge 누적 카운트 (AC / SUS)
          </div>
          {!hasJudgeData || judgeRawData.length === 0 ? (
            <div className="text-muted text-sm" style={{ padding: "24px 0", textAlign: "center" }}>
              앙상블 투표 기록 없음
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(140, judgeRawData.length * 38)}>
              <BarChart layout="vertical" data={judgeRawData}
                margin={{ top: 4, right: 24, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" tick={TICK_STYLE} />
                <YAxis type="category" dataKey="name" tick={TICK_STYLE} width={84} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="AC"  stackId="a" fill="#16a34a" />
                <Bar dataKey="SUS" stackId="a" fill="#d97706" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────── */
function ProblemStatsTab({ settings }: { settings: ConnSettings }) {
  const [bucket, setBucket] = useState("day");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [limitN, setLimitN] = useState(10);
  const [problems, setProblems] = useState<ProblemRow[]>([]);
  const [problemsSource, setProblemsSource] = useState<"" | "authoring" | "submissions">("");
  const [stats, setStats] = useState<ProblemStat[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [sortKey, setSortKey] = useState<SortKey>("acRate");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  /* ── 1) 문제 제목 best-effort 보충 — 실패해도 stats 조회는 계속 진행 ── */
  useEffect(() => {
    (async () => {
      // (a) authoring engine — 제목 보충
      try {
        const r = await adminFetch("/api/problems?originals_only=false", settings);
        if (r.ok) {
          const list: ProblemRow[] = await r.json();
          if (list.length > 0) {
            list.sort((a, b) => b.id - a.id);
            setProblems(list);
            setProblemsSource("authoring");
            return;
          }
        }
      } catch { /* fallthrough */ }

      // (b) judge submissions — 제목 보충 (best-effort)
      try {
        const r = await judgeFetch("/api/submissions?limit=500", settings);
        if (r.ok) {
          const subs: { problem_id: number; problem_title?: string }[] = await r.json();
          const seen = new Map<number, ProblemRow>();
          for (const s of subs) {
            if (!seen.has(s.problem_id)) {
              seen.set(s.problem_id, {
                id: s.problem_id,
                title: s.problem_title ?? `Problem #${s.problem_id}`,
                category: "—", level: "—", points: 0, time_limit_ms: 0,
                parent_id: null, created_at: "",
              });
            }
          }
          const list = [...seen.values()].sort((a, b) => b.id - a.id);
          if (list.length > 0) {
            setProblems(list);
            setProblemsSource("submissions");
          }
        }
      } catch { /* 제목 못 가져와도 stats 자체는 가능 */ }
    })();
  }, [settings]);

  /* ── 2) stats 직접 조회 — problem_id를 직접 스캔, 문제 목록 비어있어도 동작 ── */
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setStats([]);

    // 타깃 problem_id 결정:
    // - 문제 목록이 있으면 그 ID 사용 (최신 N개)
    // - 없으면 1..N 을 brute-force 스캔
    const scanN = limitN > 0 ? limitN : 50;
    const knownById = new Map<number, ProblemRow>();
    for (const p of problems) knownById.set(p.id, p);

    let targetIds: number[];
    if (problems.length > 0) {
      targetIds = problems.slice(0, scanN).map((p) => p.id);
    } else {
      // problem_id 1..scanN 직접 스캔
      targetIds = Array.from({ length: scanN }, (_, i) => i + 1);
    }

    setProgress({ done: 0, total: targetIds.length });

    const baseP = new URLSearchParams();
    baseP.set("bucket", bucket);
    if (since) baseP.set("since", since + ":00Z");
    if (until) baseP.set("until", until + ":00Z");

    let done = 0;
    const tasks = targetIds.map(async (pid): Promise<ProblemStat | null> => {
      const vp = new URLSearchParams(baseP);
      vp.set("problem_id", String(pid));
      try {
        const [rV, rJ] = await Promise.all([
          judgeFetch(`/api/stats/verdicts?${vp}`, settings),
          judgeFetch(`/api/stats/judges?${vp}`, settings),
        ]);
        if (!rV.ok || !rJ.ok) return null;
        const [dV, dJ] = await Promise.all([rV.json(), rJ.json()]);

        const problem: ProblemRow = knownById.get(pid) ?? {
          id: pid, title: `Problem #${pid}`,
          category: "—", level: "—", points: 0, time_limit_ms: 0,
          parent_id: null, created_at: "",
        };
        const stat = aggregate(problem, dV, dJ);
        // 데이터가 0건이면 스캔 모드일 때만 필터아웃 (문제 목록 모드면 전부 보여줌)
        if (problems.length === 0 && stat.total === 0 && stat.totalWithVotes === 0) {
          return null;
        }
        return stat;
      } catch {
        return null;
      } finally {
        done += 1;
        setProgress({ done, total: targetIds.length });
      }
    });

    try {
      const results = await Promise.all(tasks);
      const valid = results.filter((x): x is ProblemStat => x !== null);
      setStats(valid);
      if (valid.length === 0) {
        setError(
          problems.length === 0
            ? `problem_id 1..${scanN} 스캔에서 데이터를 찾지 못했습니다. 설정에서 judge URL과 토큰을 확인하세요.`
            : "조회 결과 없음 (judge URL/토큰이 올바른지 확인하세요)"
        );
      } else {
        // 백그라운드로 누락된 제목 보충 (placeholder 인 항목만)
        void enrichTitles(valid);
      }
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
      setProgress(null);
    }
  }, [problems, limitN, bucket, since, until, settings]);

  /* ── 제목 보충: placeholder 인 stat 에 대해 /api/problems/{id} 호출 ── */
  const enrichTitles = useCallback(async (currentStats: ProblemStat[]) => {
    const missing = currentStats.filter((s) =>
      s.problem.title.startsWith("Problem #") || s.problem.title === ""
    );
    if (missing.length === 0) return;

    const updates = new Map<number, string>();
    await Promise.all(
      missing.map(async (s) => {
        try {
          const r = await adminFetch(`/api/problems/${s.problem.id}`, settings);
          if (!r.ok) return;
          const data: { title?: string } = await r.json();
          if (data.title) updates.set(s.problem.id, data.title);
        } catch { /* ignore */ }
      })
    );

    if (updates.size > 0) {
      setStats((prev) => prev.map((s) => {
        const t = updates.get(s.problem.id);
        if (!t) return s;
        return { ...s, problem: { ...s.problem, title: t } };
      }));
    }
  }, [settings]);

  /* ── 페이지 진입 → 자동 1회 조회 (문제 목록 유무와 무관) ── */
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── 정렬된 리더보드 ── */
  const sorted = useMemo(() => {
    const arr = [...stats];
    arr.sort((a, b) => {
      let av: number | string, bv: number | string;
      switch (sortKey) {
        case "title":          av = a.problem.title;  bv = b.problem.title;  break;
        case "total":          av = a.total;          bv = b.total;          break;
        case "acRate":         av = a.acRate;         bv = b.acRate;         break;
        case "avgAgreeRate":   av = a.avgAgreeRate;   bv = b.avgAgreeRate;   break;
        case "unanimousRate":  av = a.unanimousRate;  bv = b.unanimousRate;  break;
      }
      if (av === bv) return 0;
      const cmp = av < bv ? -1 : 1;
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [stats, sortKey, sortDir]);

  /* ── 전체 평균 ── */
  const overall = useMemo(() => {
    if (stats.length === 0) return null;
    const sum = stats.reduce(
      (a, s) => ({
        total: a.total + s.total,
        ac: a.ac + s.ac,
        totalWithVotes: a.totalWithVotes + s.totalWithVotes,
        unanimous: a.unanimous + s.unanimous,
        agreeSum: a.agreeSum + s.avgAgreeRate * (s.totalWithVotes > 0 ? 1 : 0),
        weightedProblems: a.weightedProblems + (s.totalWithVotes > 0 ? 1 : 0),
      }),
      { total: 0, ac: 0, totalWithVotes: 0, unanimous: 0, agreeSum: 0, weightedProblems: 0 }
    );
    return {
      totalSubs: sum.total,
      acRate: sum.total > 0 ? sum.ac / sum.total : 0,
      unanimousRate: sum.totalWithVotes > 0 ? sum.unanimous / sum.totalWithVotes : 0,
      avgAgreeRate: sum.weightedProblems > 0 ? sum.agreeSum / sum.weightedProblems : 0,
      problemsWithData: stats.filter((s) => s.total > 0).length,
    };
  }, [stats]);

  function toggleExpand(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function setSort(k: SortKey) {
    if (sortKey === k) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir("desc"); }
  }

  function sortIndicator(k: SortKey) {
    if (sortKey !== k) return <span style={{ opacity: 0.3 }}> ↕</span>;
    return <span style={{ color: "var(--accent)" }}> {sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  function ratePill(rate: number, type: "ac" | "agree" | "unanimous") {
    const pct = (rate * 100).toFixed(1);
    const colorClass = type === "ac"
      ? (rate >= 0.7 ? "score-good" : rate >= 0.4 ? "score-mid" : "score-bad")
      : (rate >= 0.7 ? "score-good" : rate >= 0.5 ? "score-mid" : "score-bad");
    return (
      <div className={`score-bar-wrap ${colorClass}`} style={{ minWidth: 120 }}>
        <div className="score-bar"><div className="score-bar-fill" style={{ width: `${pct}%` }} /></div>
        <span className="score-val">{pct}%</span>
      </div>
    );
  }

  return (
    <div>
      {/* ── 필터 ── */}
      <div className="card">
        <div className="filter-row">
          <div className="field narrow">
            <label>버킷</label>
            <select value={bucket} onChange={(e) => setBucket(e.target.value)}>
              {(["hour","day","week"] as const).map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Since</label>
            <input type="datetime-local" value={since} onChange={(e) => setSince(e.target.value)} />
          </div>
          <div className="field">
            <label>Until</label>
            <input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} />
          </div>
          <div className="field narrow">
            <label>대상 개수</label>
            <select value={limitN} onChange={(e) => setLimitN(Number(e.target.value))}>
              <option value={10}>상위 10</option>
              <option value={25}>상위 25</option>
              <option value={50}>상위 50</option>
              <option value={0}>전체</option>
            </select>
          </div>
          <div className="field" style={{ maxWidth: 200, marginTop: "auto" }}>
            <button className="btn btn-primary" onClick={load} disabled={loading}>
              {loading
                ? <><span className="spinner" />&nbsp;수집 중...</>
                : (problems.length > 0
                    ? `↻ 조회 (${Math.min(limitN || problems.length, problems.length)} / ${problems.length}문제)`
                    : `↻ 조회 (problem_id 1..${limitN || 50} 스캔)`
                  )
              }
            </button>
          </div>
          {progress && (
            <div className="field" style={{ marginTop: "auto" }}>
              <span className="text-mono text-sm text-muted">
                {progress.done}/{progress.total}
              </span>
            </div>
          )}
        </div>
        <div className="text-muted text-sm mt-8" style={{ paddingTop: 4 }}>
          {problemsSource === "authoring" && (
            <>제목 소스: <span className="text-mono">authoring engine /api/problems</span></>
          )}
          {problemsSource === "submissions" && (
            <>제목 소스: <span className="text-mono">judge engine /api/submissions</span></>
          )}
          {!problemsSource && (
            <>제목 미수신 — <span className="text-mono">problem_id 1..{limitN || 50}</span> 직접 스캔 모드</>
          )}
        </div>
        {error && <div className="output-panel err">{error}</div>}
      </div>

      {/* ── 전체 평균 카드 ── */}
      {overall && (
        <div className="grid-3 mb-16">
          <div className="stat-tile">
            <div className="stat-tile-label">전체 AC율</div>
            <div className="stat-tile-value" style={{ color: "var(--green)" }}>
              {(overall.acRate * 100).toFixed(1)}%
            </div>
            <div className="stat-tile-sub">{overall.totalSubs.toLocaleString()}건 제출 기준</div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile-label">평균 모델 일치율</div>
            <div className="stat-tile-value" style={{ color: "var(--accent)" }}>
              {(overall.avgAgreeRate * 100).toFixed(1)}%
            </div>
            <div className="stat-tile-sub">
              앙상블 투표가 있는 {overall.problemsWithData}개 문제 평균
            </div>
          </div>
          <div className="stat-tile">
            <div className="stat-tile-label">만장일치 비율 (3:0)</div>
            <div className="stat-tile-value" style={{ color: "var(--purple)" }}>
              {(overall.unanimousRate * 100).toFixed(1)}%
            </div>
            <div className="stat-tile-sub">의견 분기 비율 = {((1 - overall.unanimousRate) * 100).toFixed(1)}%</div>
          </div>
        </div>
      )}

      {/* ── 리더보드 ── */}
      {sorted.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid var(--border)" }}>
            <div className="card-title" style={{ marginBottom: 4 }}>
              <span className="card-icon">◈</span> 문제별 평균 리더보드
            </div>
            <div className="text-muted text-sm">
              행을 클릭하면 해당 문제의 상세 차트가 펼쳐집니다. 헤더 클릭 = 정렬.
            </div>
          </div>
          <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
            <table>
              <thead>
                <tr>
                  <th style={{ cursor: "pointer" }} onClick={() => setSort("title")}>
                    문제{sortIndicator("title")}
                  </th>
                  <th style={{ cursor: "pointer", width: 100 }} onClick={() => setSort("total")}>
                    제출 수{sortIndicator("total")}
                  </th>
                  <th style={{ cursor: "pointer", width: 200 }} onClick={() => setSort("acRate")}>
                    AC율{sortIndicator("acRate")}
                  </th>
                  <th style={{ cursor: "pointer", width: 200 }} onClick={() => setSort("avgAgreeRate")}>
                    평균 모델 일치율{sortIndicator("avgAgreeRate")}
                  </th>
                  <th style={{ cursor: "pointer", width: 200 }} onClick={() => setSort("unanimousRate")}>
                    만장일치 비율{sortIndicator("unanimousRate")}
                  </th>
                  <th style={{ width: 40 }}></th>
                </tr>
              </thead>
              <tbody>
                {sorted.flatMap((s) => {
                  const isOpen = expanded.has(s.problem.id);
                  const placeholder = s.problem.title.startsWith("Problem #");
                  const rows = [
                    <tr
                      key={s.problem.id}
                      style={{ cursor: "pointer" }}
                      onClick={() => toggleExpand(s.problem.id)}
                    >
                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{
                            fontWeight: 500,
                            color: placeholder ? "var(--text-muted)" : "var(--text)",
                            fontStyle: placeholder ? "italic" : "normal",
                          }}>
                            {s.problem.title}
                          </span>
                          <span className="hint">#{s.problem.id}</span>
                          {s.problem.parent_id && <span className="badge badge-purple">변형</span>}
                        </div>
                      </td>
                      <td className="num">{s.total.toLocaleString()}</td>
                      <td>{ratePill(s.acRate, "ac")}</td>
                      <td>
                        {s.totalWithVotes > 0
                          ? ratePill(s.avgAgreeRate, "agree")
                          : <span className="text-dim text-sm">—</span>
                        }
                      </td>
                      <td>
                        {s.totalWithVotes > 0
                          ? ratePill(s.unanimousRate, "unanimous")
                          : <span className="text-dim text-sm">—</span>
                        }
                      </td>
                      <td className="text-muted text-mono text-sm" style={{ textAlign: "center" }}>
                        {isOpen ? "▾" : "▸"}
                      </td>
                    </tr>,
                  ];
                  if (isOpen) {
                    rows.push(
                      <tr key={`${s.problem.id}-detail`}>
                        <td colSpan={6} style={{ padding: 0, background: "var(--bg)" }}>
                          <ProblemDetail stat={s} />
                        </td>
                      </tr>
                    );
                  }
                  return rows;
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && stats.length === 0 && (
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <div className="text-muted">조회 버튼을 눌러 통계를 불러오세요</div>
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────── */
export default function StatsView({ settings }: Props) {
  const [tab, setTab] = useState<StatsTab>("problems");

  return (
    <div>
      <p className="card-desc mb-12">
        {tab === "problems"
          ? "문제별 채점 통계와 LLM-as-Judge 앙상블 동향을 한눈에 확인합니다. 행을 클릭하면 상세 차트가 펼쳐집니다."
          : "LangGraph 변형 파이프라인이 매긴 원본-변형 4축 점수를 시각화합니다."
        }
      </p>

      <div className="tabs">
        {([
          ["problems",   "문제별 통계"],
          ["comparison", "원본-변형 비교 점수"],
        ] as [StatsTab, string][]).map(([t, label]) => (
          <button key={t} className={`tab-btn${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "problems"   && <ProblemStatsTab settings={settings} />}
      {tab === "comparison" && <ComparisonTab    settings={settings} />}
    </div>
  );
}
