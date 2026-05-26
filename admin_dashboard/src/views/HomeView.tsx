import { useState, useEffect, useCallback, useMemo } from "react";
import type {
  ConnSettings, VerdictsResponse, JudgesResponse, ProblemRow, RunSummaryT, UserRow,
  SubmissionRow, SubmissionDetail,
} from "../types";
import { adminFetch, judgeFetch, fmtDate } from "../api";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from "recharts";

interface Props { settings: ConnSettings }

/* ── 색상/스타일 (StatsView 와 통일) ─────────────────────────────── */
const JUDGE_COLORS: Record<string, string> = {
  Melchior: "#3182F6", Balthasar: "#16a34a", Casper: "#d97706",
};
const judgeColor = (jid: string, i: number) =>
  JUDGE_COLORS[jid] ?? ["#7c3aed", "#db2777", "#06b6d4"][i % 3];

const VERDICT_COLORS = { ac: "#16a34a", sus: "#d97706", failed: "#ef4444", pending: "#94a3b8" };
const CAT_COLORS = ["#3182F6", "#16a34a", "#d97706", "#7c3aed", "#06b6d4", "#db2777", "#0284c7", "#65a30d"];

const TOOLTIP_STYLE = {
  background: "#fff", border: "1px solid #e5e7eb", borderRadius: 6,
  fontSize: 12, color: "#0f172a", boxShadow: "0 4px 6px -1px rgba(0,0,0,.1)",
};
const TICK = { fill: "#64748b", fontSize: 11 };

/* ── ISO since helper ─────────────────────────────────────────────── */
const sinceISO = (days: number) => new Date(Date.now() - days * 864e5).toISOString();

/* ── 빈 차트 placeholder ──────────────────────────────────────────── */
function EmptyChart({ msg }: { msg: string }) {
  return (
    <div className="text-muted text-sm" style={{ height: 200, display: "flex", alignItems: "center", justifyContent: "center" }}>
      {msg}
    </div>
  );
}

/* ── 도넛 (가운데 합계 오버레이) ──────────────────────────────────── */
function Donut({ data, total, unit }: { data: { name: string; value: number; color: string }[]; total: number; unit?: string }) {
  const shown = data.filter((d) => d.value > 0);
  if (shown.length === 0) return <EmptyChart msg="데이터 없음" />;
  return (
    <div style={{ position: "relative", height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={shown} dataKey="value" nameKey="name" cx="50%" cy="50%"
            innerRadius={58} outerRadius={86} paddingAngle={2} stroke="none">
            {shown.map((d, i) => <Cell key={i} fill={d.color} />)}
          </Pie>
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
      <div style={{
        position: "absolute", top: "42%", left: 0, right: 0, transform: "translateY(-50%)",
        textAlign: "center", pointerEvents: "none",
      }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 26, fontWeight: 800, color: "var(--ink)", lineHeight: 1.1 }}>
          {total.toLocaleString()}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)" }}>{unit ?? "합계"}</div>
      </div>
    </div>
  );
}

/* ── votes 파싱 → AC/SUS 배열 (저장 형태가 list 또는 {votes:[]} 모두 대응) ── */
function parseVotes(v: unknown): ("AC" | "SUS")[] {
  const arr: unknown[] = Array.isArray(v)
    ? v
    : (v && typeof v === "object" && Array.isArray((v as { votes?: unknown[] }).votes))
      ? (v as { votes: unknown[] }).votes
      : [];
  return arr
    .map((x) => (typeof x === "string" ? x : (x as { verdict?: string })?.verdict))
    .filter((x): x is "AC" | "SUS" => x === "AC" || x === "SUS");
}

/* ── 검토 필요 제출 — 앙상블 AC 득표율 낮은 순 (기존 SUS) ──────────── */
interface ReviewRow { id: number; problem: string; user: string; created_at: string; ac: number; n: number; ratio: number; }

function ReviewPanel({ settings }: { settings: ConnSettings }) {
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [thresh, setThresh] = useState<33 | 0>(33); // ≤33%(의심 전체) | =0%(만장 SUS)
  const [err, setErr] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setErr(false);
    try {
      // verdict=SUS = AC 득표율 ≤ 33% 인 제출 (테스트 통과 + 앙상블 의심)
      const r = await judgeFetch("/api/submissions?verdict=SUS&limit=50", settings);
      if (!r.ok) { setErr(true); setRows([]); return; }
      const list: SubmissionRow[] = await r.json();
      const detailed = await Promise.all(list.map(async (s): Promise<ReviewRow | null> => {
        try {
          const d = await judgeFetch(`/api/submissions/${s.id}`, settings);
          if (!d.ok) return null;
          const det: SubmissionDetail = await d.json();
          const votes = parseVotes(det.votes);
          const n = votes.length;
          const ac = votes.filter((x) => x === "AC").length;
          return {
            id: s.id,
            problem: s.problem_title ?? `문제 #${s.problem_id}`,
            user: s.user_display_name ?? `user ${s.user_id}`,
            created_at: s.created_at,
            ac, n, ratio: n > 0 ? Math.round((ac / n) * 100) : 0,
          };
        } catch { return null; }
      }));
      const valid = detailed.filter((x): x is ReviewRow => x !== null)
        .sort((a, b) => a.ratio - b.ratio || (a.created_at < b.created_at ? 1 : -1));
      setRows(valid);
    } catch { setErr(true); } finally { setLoading(false); }
  }, [settings]);

  useEffect(() => { load(); }, [load]);

  const shown = rows.filter((r) => (thresh === 0 ? r.ratio === 0 : r.ratio <= 33));

  return (
    <div className="chart-card" style={{ marginTop: 16 }}>
      <div className="chart-card-head">
        <h3>검토 필요 제출</h3>
        <span className="text-muted text-sm">AC 표기지만 앙상블 AC 득표율이 낮은 제출 (기존 SUS)</span>
        <div className="page-head-actions" style={{ marginLeft: "auto", alignItems: "center" }}>
          <div className="filter-chips">
            <button className={`filter-chip${thresh === 33 ? " active" : ""}`} onClick={() => setThresh(33)}>≤ 33% (의심 전체)</button>
            <button className={`filter-chip${thresh === 0 ? " active" : ""}`} onClick={() => setThresh(0)}>= 0% (만장 SUS)</button>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            {loading ? <><span className="spinner" />&nbsp;</> : "↻"}
          </button>
        </div>
      </div>

      {err ? (
        <div className="text-muted text-sm" style={{ padding: "20px 0", textAlign: "center" }}>제출 데이터를 불러오지 못했습니다 (judge URL/토큰 확인).</div>
      ) : loading ? (
        <div className="text-muted text-sm" style={{ padding: "20px 0", textAlign: "center" }}><span className="spinner" /> 불러오는 중...</div>
      ) : shown.length === 0 ? (
        <div className="text-muted text-sm" style={{ padding: "20px 0", textAlign: "center" }}>
          {thresh === 0 ? "만장일치 SUS(0%) 제출 없음" : "검토 대상 없음 — 앙상블이 의심한 제출이 없습니다"}
        </div>
      ) : (
        <table className="tbl">
          <thead>
            <tr>
              <th>문제</th>
              <th>유저</th>
              <th style={{ width: 130 }}>AC 득표율</th>
              <th style={{ width: 90 }}>표기</th>
              <th style={{ width: 160 }}>제출 시각</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id}>
                <td>{r.problem} <span className="hint">#{r.id}</span></td>
                <td>{r.user}</td>
                <td>
                  <span className="badge" style={{
                    background: r.ratio === 0 ? "var(--red-bg)" : "var(--amber-bg)",
                    color: r.ratio === 0 ? "var(--red)" : "var(--amber)",
                    fontFamily: "var(--font-mono)",
                  }}>
                    {r.ratio}% · {r.ac}/{r.n} AC
                  </span>
                </td>
                <td><span className="verdict-AC badge">AC</span></td>
                <td className="mono-cell">{fmtDate(r.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════ */
export default function HomeView({ settings }: Props) {
  const [days, setDays] = useState(14);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const [verdicts, setVerdicts] = useState<VerdictsResponse | null>(null);
  const [judges, setJudges] = useState<JudgesResponse | null>(null);
  const [problems, setProblems] = useState<ProblemRow[] | null>(null);
  const [runs, setRuns] = useState<RunSummaryT[] | null>(null);
  const [users, setUsers] = useState<UserRow[] | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const since = sinceISO(days);
    const okJson = async <T,>(p: Promise<Response>): Promise<T | null> => {
      try { const r = await p; return r.ok ? (await r.json()) as T : null; }
      catch { return null; }
    };
    const [v, j, p, r, u] = await Promise.all([
      okJson<VerdictsResponse>(judgeFetch(`/api/stats/verdicts?bucket=day&since=${encodeURIComponent(since)}`, settings)),
      okJson<JudgesResponse>(judgeFetch(`/api/stats/judges?bucket=day&since=${encodeURIComponent(since)}`, settings)),
      okJson<ProblemRow[]>(adminFetch("/api/problems?originals_only=false", settings)),
      okJson<RunSummaryT[]>(adminFetch("/api/runs?limit=100", settings)),
      okJson<UserRow[]>(judgeFetch("/api/users?limit=1000", settings)),
    ]);
    setVerdicts(v); setJudges(j); setProblems(p); setRuns(r); setUsers(u);
    setUpdatedAt(new Date());
    setLoading(false);
  }, [settings, days]);

  useEffect(() => { load(); }, [load]);

  /* ── 집계 ─────────────────────────────────────────────────────── */
  const agg = useMemo(() => {
    const vt = (verdicts?.series ?? []).reduce(
      (a, b) => ({ total: a.total + b.total, ac: a.ac + b.ac, sus: a.sus + b.sus, failed: a.failed + b.failed, pending: a.pending + b.pending }),
      { total: 0, ac: 0, sus: 0, failed: 0, pending: 0 },
    );
    // SUS(테스트 통과 + 앙상블 의심)는 대시보드에서 AC로 합산 표기한다.
    const passed = vt.ac + vt.sus;
    const acRate = vt.total > 0 ? passed / vt.total : 0;

    const jt = (judges?.series ?? []).reduce(
      (a, b) => ({ totalWithVotes: a.totalWithVotes + b.total_with_votes, unanimous: a.unanimous + b.unanimous, split: a.split + b.split }),
      { totalWithVotes: 0, unanimous: 0, split: 0 },
    );
    const unanimousRate = jt.totalWithVotes > 0 ? jt.unanimous / jt.totalWithVotes : 0;

    const perJudge: { name: string; rate: number; ac: number; sus: number }[] = [];
    for (const jid of judges?.judge_ids ?? []) {
      let agree = 0, ac = 0, sus = 0;
      for (const b of judges?.series ?? []) {
        const e = b.judges[jid]; if (!e) continue;
        agree += e.agree_with_final; ac += e.ac; sus += e.sus;
      }
      perJudge.push({ name: jid, rate: jt.totalWithVotes > 0 ? +(agree / jt.totalWithVotes * 100).toFixed(1) : 0, ac, sus });
    }
    const avgAgree = perJudge.length ? perJudge.reduce((s, x) => s + x.rate, 0) / perJudge.length : 0;

    const variants = (problems ?? []).filter((p) => p.parent_id != null).length;
    const originals = (problems?.length ?? 0) - variants;
    const catMap: Record<string, number> = {};
    for (const p of problems ?? []) { const c = p.category || "—"; catMap[c] = (catMap[c] ?? 0) + 1; }
    const categories = Object.entries(catMap).sort((a, b) => b[1] - a[1]).slice(0, 8)
      .map(([name, count]) => ({ name, count }));

    const runStatus = { done: 0, failed: 0, running: 0, other: 0 };
    for (const r of runs ?? []) {
      if (r.status === "done") runStatus.done++;
      else if (r.status === "failed") runStatus.failed++;
      else if (r.status === "running") runStatus.running++;
      else runStatus.other++;
    }

    const trend = (verdicts?.series ?? []).map((b) => ({
      bucket: b.bucket.length > 10 ? b.bucket.slice(5, 16).replace("T", " ") : b.bucket.slice(5),
      AC: b.ac + b.sus, 실패: b.failed, 대기: b.pending,
    }));

    return {
      vt, passed, acRate, jt, unanimousRate, perJudge, avgAgree,
      total: problems?.length ?? 0, variants, originals, categories,
      runStatus, runTotal: runs?.length ?? 0,
      userCount: users?.length ?? 0, withKey: (users ?? []).filter((u) => u.has_api_key).length,
      trend,
    };
  }, [verdicts, judges, problems, runs, users]);

  const disconnected = !loading && !verdicts && !judges && !problems && !runs && !users;

  /* ── KPI 타일 ──────────────────────────────────────────────────── */
  const kpis: { label: string; value: string; sub: string; color?: string }[] = [
    { label: "등록 문제", value: agg.total.toLocaleString(), sub: `원본 ${agg.originals} · 변형 ${agg.variants}`, color: "var(--brand-dark)" },
    { label: `채점 건수 (${days}일)`, value: agg.vt.total.toLocaleString(), sub: `AC ${agg.passed} · 실패 ${agg.vt.failed} · 대기 ${agg.vt.pending}`, color: "var(--ink)" },
    { label: "전체 AC율", value: `${(agg.acRate * 100).toFixed(1)}%`, sub: `${agg.passed.toLocaleString()} / ${agg.vt.total.toLocaleString()} 제출 (의심 포함)`, color: "var(--green)" },
    { label: "평균 모델 일치율", value: `${agg.avgAgree.toFixed(1)}%`, sub: `앙상블 투표 ${agg.jt.totalWithVotes.toLocaleString()}건`, color: "var(--brand-dark)" },
    { label: "만장일치율 (3:0)", value: `${(agg.unanimousRate * 100).toFixed(1)}%`, sub: `분기(2:1) ${agg.jt.split.toLocaleString()}건`, color: "var(--purple)" },
    { label: "파이프라인 run", value: agg.runTotal.toLocaleString(), sub: `완료 ${agg.runStatus.done} · 실패 ${agg.runStatus.failed} · 진행 ${agg.runStatus.running}`, color: "var(--sky)" },
    { label: "유저", value: agg.userCount.toLocaleString(), sub: `API 키 보유 ${agg.withKey}`, color: "var(--ink)" },
  ];

  return (
    <div className="main home">
      <div className="page-head">
        <h1>통합 현황</h1>
        <span className="sub">JCode-Quest 전체 채점 · 앙상블 · 출제 파이프라인 한눈에 보기</span>
        <div className="page-head-actions">
          <div className="filter-chips">
            {[7, 14, 30].map((d) => (
              <button key={d} className={`filter-chip${days === d ? " active" : ""}`} onClick={() => setDays(d)}>
                {d}일
              </button>
            ))}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            {loading ? <><span className="spinner" />&nbsp;갱신 중</> : "↻ 새로고침"}
          </button>
        </div>
      </div>

      {updatedAt && !loading && (
        <div className="text-muted text-sm mb-16" style={{ marginTop: -12 }}>
          마지막 갱신 {updatedAt.toLocaleTimeString("ko-KR")} · 채점/앙상블 지표는 최근 {days}일, 문제/유저/run은 전체 기준
        </div>
      )}

      {disconnected && (
        <div className="output-panel err">
          데이터를 불러오지 못했습니다. 우상단 ⚙ 설정에서 authoring(:8001)·judge(:8002) URL과 토큰을 확인하세요.
        </div>
      )}

      {/* ── KPI 그리드 ── */}
      <div className="stat-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))" }}>
        {kpis.map((k) => (
          <div className="stat-card" key={k.label}>
            <div className="label">{k.label}</div>
            <div className="value" style={{ color: k.color }}>{loading ? "—" : k.value}</div>
            <div className="delta flat">{k.sub}</div>
          </div>
        ))}
      </div>

      {/* ── 판정 분포 + 채점 추세 ── */}
      <div className="grid-2">
        <div className="chart-card" style={{ marginBottom: 0 }}>
          <div className="chart-card-head"><h3>판정 분포</h3>
            <span className="text-muted text-sm" style={{ marginLeft: "auto" }}>최근 {days}일 · AC=의심 포함</span>
          </div>
          <Donut total={agg.vt.total} unit="채점" data={[
            { name: "AC", value: agg.passed, color: VERDICT_COLORS.ac },
            { name: "실패", value: agg.vt.failed, color: VERDICT_COLORS.failed },
            { name: "대기", value: agg.vt.pending, color: VERDICT_COLORS.pending },
          ]} />
        </div>

        <div className="chart-card" style={{ marginBottom: 0 }}>
          <div className="chart-card-head"><h3>채점 추세</h3>
            <span className="text-muted text-sm" style={{ marginLeft: "auto" }}>일별 판정 카운트</span>
          </div>
          {agg.trend.length === 0 ? <EmptyChart msg="채점 기록 없음" /> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={agg.trend} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" vertical={false} />
                <XAxis dataKey="bucket" tick={TICK} />
                <YAxis tick={TICK} allowDecimals={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="AC" stackId="a" fill={VERDICT_COLORS.ac} radius={[0, 0, 0, 0]} />
                <Bar dataKey="실패" stackId="a" fill={VERDICT_COLORS.failed} />
                <Bar dataKey="대기" stackId="a" fill={VERDICT_COLORS.pending} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* ── 모델별 일치율 + 만장일치 분포 ── */}
      <div className="grid-2" style={{ marginTop: 16 }}>
        <div className="chart-card" style={{ marginBottom: 0 }}>
          <div className="chart-card-head"><h3>LLM-as-Judge 모델별 최종판정 일치율</h3></div>
          {agg.perJudge.length === 0 || agg.jt.totalWithVotes === 0 ? <EmptyChart msg="앙상블 투표 기록 없음" /> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart layout="vertical" data={agg.perJudge} margin={{ top: 4, right: 28, left: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={TICK} />
                <YAxis type="category" dataKey="name" tick={TICK} width={84} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => `${v.toFixed(1)}%`} />
                <Bar dataKey="rate" radius={[0, 3, 3, 0]} barSize={26}>
                  {agg.perJudge.map((d, i) => <Cell key={i} fill={judgeColor(d.name, i)} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="chart-card" style={{ marginBottom: 0 }}>
          <div className="chart-card-head"><h3>앙상블 합의 분포</h3>
            <span className="text-muted text-sm" style={{ marginLeft: "auto" }}>3:0 vs 2:1</span>
          </div>
          <Donut total={agg.jt.totalWithVotes} unit="투표" data={[
            { name: "만장일치 (3:0)", value: agg.jt.unanimous, color: "#16a34a" },
            { name: "분기 (2:1)", value: agg.jt.split, color: "#d97706" },
          ]} />
        </div>
      </div>

      {/* ── 문제 카테고리 + 파이프라인 run 상태 ── */}
      <div className="grid-2" style={{ marginTop: 16 }}>
        <div className="chart-card" style={{ marginBottom: 0 }}>
          <div className="chart-card-head"><h3>문제 카테고리 분포</h3>
            <span className="text-muted text-sm" style={{ marginLeft: "auto" }}>전체 {agg.total}문제</span>
          </div>
          {agg.categories.length === 0 ? <EmptyChart msg="문제 없음" /> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={agg.categories} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" vertical={false} />
                <XAxis dataKey="name" tick={TICK} interval={0} />
                <YAxis tick={TICK} allowDecimals={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Bar dataKey="count" name="문제 수" radius={[3, 3, 0, 0]} barSize={36}>
                  {agg.categories.map((_, i) => <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="chart-card" style={{ marginBottom: 0 }}>
          <div className="chart-card-head"><h3>출제 파이프라인 run 상태</h3>
            <span className="text-muted text-sm" style={{ marginLeft: "auto" }}>최근 {agg.runTotal}건</span>
          </div>
          <Donut total={agg.runTotal} unit="run" data={[
            { name: "완료", value: agg.runStatus.done, color: "#16a34a" },
            { name: "실패", value: agg.runStatus.failed, color: "#ef4444" },
            { name: "진행", value: agg.runStatus.running, color: "#f59e0b" },
            { name: "기타", value: agg.runStatus.other, color: "#94a3b8" },
          ]} />
        </div>
      </div>

      {/* ── 검토 필요 제출 (AC 득표율 필터) ── */}
      <ReviewPanel settings={settings} />
    </div>
  );
}
