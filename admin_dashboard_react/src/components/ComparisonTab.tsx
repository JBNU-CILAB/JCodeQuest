import { useState, useCallback } from "react";
import type { ConnSettings, ComparisonResponse } from "../types";
import { adminFetch } from "../api";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

interface Props {
  settings: ConnSettings;
  initialId?: number;
}

export default function ComparisonTab({ settings, initialId }: Props) {
  const [oid, setOid] = useState(initialId ? String(initialId) : "");
  const [data, setData] = useState<ComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [output, setOutput] = useState<{ kind: "ok" | "err" | ""; msg: string }>({ kind: "", msg: "" });

  const load = useCallback(async (id?: string) => {
    const idNum = parseInt(id ?? oid, 10);
    if (!idNum || idNum < 1) { setOutput({ kind: "err", msg: "원본 problem_id를 입력하세요" }); return; }
    setLoading(true);
    setData(null);
    setOutput({ kind: "", msg: `GET /api/admin/originals/${idNum}/comparison ...` });
    try {
      const r = await adminFetch(`/api/admin/originals/${idNum}/comparison`, settings);
      const body = await r.json();
      if (!r.ok) {
        setOutput({ kind: "err", msg: `[${r.status}] ${JSON.stringify(body, null, 2)}` });
      } else {
        setData(body);
        setOutput({ kind: "ok", msg: `✓ ${body.variant_count}개 변형 로드` });
      }
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: (err as Error).message });
    } finally {
      setLoading(false);
    }
  }, [oid, settings]);

  function scoreClass(axis: "hal" | "pos", v: number | undefined) {
    if (v == null) return "score-mid";
    if (axis === "hal") return v < 0.3 ? "score-good" : v < 0.6 ? "score-mid" : "score-bad";
    return v > 0.7 ? "score-good" : v > 0.4 ? "score-mid" : "score-bad";
  }

  function ScoreBar({ axis, v }: { axis: "hal" | "pos"; v?: number }) {
    if (v == null) return <span className="text-dim">—</span>;
    const cls = scoreClass(axis, v);
    return (
      <div className={`score-bar-wrap ${cls}`}>
        <div className="score-bar"><div className="score-bar-fill" style={{ width: `${v * 100}%` }} /></div>
        <span className="score-val">{v.toFixed(3)}</span>
      </div>
    );
  }

  const chartData = data?.variants.map((v) => ({
    name: `#${v.problem_id}`,
    hal: v.hallucination_score ?? 0,
    intent: v.intent_similarity ?? 0,
    diff: v.difficulty_similarity ?? 0,
  })) ?? [];

  return (
    <div>
      <div className="card">
        <div className="card-title"><span className="card-icon">◈</span> 원본-변형 비교 점수 조회</div>
        <div className="card-desc">
          LangGraph 변형 파이프라인이 매긴 4축 점수(hallucination / intent / difficulty / judge)를 시각화합니다.
        </div>
        <div className="filter-row">
          <div className="field narrow">
            <label>원본 ID</label>
            <input
              type="number" value={oid} min={1}
              onChange={(e) => setOid(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load()}
              placeholder="1"
            />
          </div>
          <div className="field" style={{ maxWidth: 100, marginTop: "auto" }}>
            <button className="btn btn-primary" onClick={() => load()} disabled={loading}>
              {loading ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "조회"}
            </button>
          </div>
        </div>
        {output.msg && <div className={`output-panel ${output.kind}`}>{output.msg}</div>}
      </div>

      {data && (
        <>
          <div className="grid-3 mb-16">
            {[
              { label: "Hallucination ↓", key: "hallucination" as const, axis: "hal" as const },
              { label: "Intent Similarity ↑", key: "intent_similarity" as const, axis: "pos" as const },
              { label: "Difficulty Similarity ↑", key: "difficulty_similarity" as const, axis: "pos" as const },
            ].map(({ label, key }) => {
              const s = data[key];
              return (
                <div key={key} className="stat-tile">
                  <div className="stat-tile-label">{label}</div>
                  <div className="stat-tile-value">
                    {s?.mean != null ? s.mean.toFixed(3) : "—"}
                  </div>
                  <div className="stat-tile-sub">
                    n={s?.count ?? 0} · min {s?.min?.toFixed(2) ?? "—"} · max {s?.max?.toFixed(2) ?? "—"}
                  </div>
                </div>
              );
            })}
          </div>

          {chartData.length > 0 && (
            <div className="card">
              <div className="card-title"><span className="card-icon">◈</span> 변형별 점수 비교</div>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <XAxis dataKey="name" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                    <YAxis domain={[0, 1]} tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 6, boxShadow: "0 4px 6px -1px rgba(0,0,0,.1)" }} />
                    <Legend />
                    <Bar dataKey="hal"    name="hallucination"        fill="#dc2626" radius={[3,3,0,0]} />
                    <Bar dataKey="intent" name="intent_similarity"    fill="#0DA5E8" radius={[3,3,0,0]} />
                    <Bar dataKey="diff"   name="difficulty_similarity" fill="#16a34a" radius={[3,3,0,0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          <div className="card" style={{ padding: 0 }}>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th><th>제목</th><th>난이도</th>
                    <th>Hallucination ↓</th><th>Intent Similarity ↑</th>
                    <th>Difficulty Similarity ↑</th><th>Judge</th><th>비고</th>
                  </tr>
                </thead>
                <tbody>
                  {data.variants.map((v) => (
                    <tr key={v.problem_id}>
                      <td className="num">{v.problem_id}</td>
                      <td>{v.title ?? "—"}</td>
                      <td>{v.level ?? "—"}</td>
                      <td><ScoreBar axis="hal" v={v.hallucination_score} /></td>
                      <td><ScoreBar axis="pos" v={v.intent_similarity} /></td>
                      <td><ScoreBar axis="pos" v={v.difficulty_similarity} /></td>
                      <td className="num">{v.judge_score?.toFixed(2) ?? "—"}</td>
                      <td className="text-sm text-muted" style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {v.error ? <span style={{ color: "var(--red)" }}>error: {v.error}</span> : v.rationale ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
