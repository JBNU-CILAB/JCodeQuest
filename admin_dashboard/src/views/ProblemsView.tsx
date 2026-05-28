import { useState, useRef, useCallback } from "react";
import type { ConnSettings, ProblemRow, TestCase, ProblemDetail } from "../types";
import { adminFetch, fmtDate } from "../api";
import AuthoringMetaPanel from "../components/AuthoringMetaPanel";

interface Props { settings: ConnSettings }

type Tab = "create" | "variant" | "list";

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
interface StreamLine { ts: string; tag: string; kind: "ok" | "err" | "info" | "warn" | "plain"; body: string }

function VariantTab({ settings }: Props) {
  const [problemId, setProblemId] = useState("");
  const [count, setCount] = useState("3");
  const [lines, setLines] = useState<StreamLine[]>([]);
  const [running, setRunning] = useState(false);
  const [traceUrl, setTraceUrl] = useState<string | null>(null);
  const ctrlRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  function addLine(kind: StreamLine["kind"], tag: string, body: string) {
    const ts = new Date().toLocaleTimeString("ko-KR", { hour12: false });
    setLines((p) => [...p, { ts, tag, kind, body }]);
    setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  function handlePayload(p: Record<string, unknown>) {
    if (p.event === "node_start") {
      addLine("info", "NODE", `▶ ${p.node}`);
    } else if (p.event === "node_end") {
      const node = p.node as string | undefined;
      const data = p.data as Record<string, unknown> | undefined;
      if (node === "persist_approved" && data?.approved_ids) {
        addLine("ok", "DONE", `approved: ${JSON.stringify(data.approved_ids)}`);
      } else {
        addLine("ok", "END", `◼ ${node} — ${JSON.stringify(data ?? {}).slice(0, 120)}`);
      }
    } else if (p.event === "error") {
      addLine("err", "ERR", String(p.message ?? p));
    } else {
      addLine("plain", "EVT", JSON.stringify(p).slice(0, 200));
    }
  }

  async function start() {
    const pid = parseInt(problemId, 10);
    const cnt = parseInt(count, 10);
    if (!pid || pid < 1) { addLine("err", "ERR", "problem_id를 입력하세요"); return; }
    if (!cnt || cnt < 1) { addLine("err", "ERR", "count를 입력하세요"); return; }

    setLines([]);
    setTraceUrl(null);
    setRunning(true);
    ctrlRef.current = new AbortController();

    addLine("info", "POST", `/api/runs problem_id=${pid} count=${cnt}`);
    try {
      const r = await adminFetch("/api/runs", settings, {
        method: "POST",
        body: JSON.stringify({ problem_id: pid, count: cnt }),
        signal: ctrlRef.current.signal,
      });
      if (!r.ok) {
        const body = await r.text();
        addLine("err", "ERR", `[${r.status}] ${body.slice(0, 300)}`);
        setRunning(false);
        return;
      }
      const { run_id, langsmith_trace_url } = await r.json();
      addLine("ok", "RUN", `run_id=${run_id}`);
      if (langsmith_trace_url) setTraceUrl(langsmith_trace_url);
      addLine("info", "STREAM", `구독 시작 /api/runs/${run_id}/events`);

      const resp = await adminFetch(`/api/runs/${run_id}/events`, settings, {
        signal: ctrlRef.current.signal,
      });
      const reader = resp.body!.getReader();
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
            if (raw === "[DONE]") { addLine("ok", "DONE", "스트림 완료"); break; }
            try { handlePayload(JSON.parse(raw)); } catch { addLine("plain", "RAW", raw); }
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== "AbortError")
        addLine("err", "ERR", `오류: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }

  function stop() { ctrlRef.current?.abort(); setRunning(false); }

  return (
    <div>
      <div className="card">
        <div className="card-title"><span className="card-icon">◈</span> 변형 출제</div>
        <div className="card-desc">기존 원본 문제를 시드로 LangGraph 파이프라인을 실행하여 변형 문제를 자동 생성합니다.</div>
        <div className="filter-row">
          <div className="field narrow">
            <label>원본 ID</label>
            <input type="number" value={problemId} onChange={(e) => setProblemId(e.target.value)} placeholder="1" min={1} />
          </div>
          <div className="field narrow">
            <label>생성 수</label>
            <input type="number" value={count} onChange={(e) => setCount(e.target.value)} min={1} max={10} />
          </div>
          <div className="field" style={{ maxWidth: 100, marginTop: "auto" }}>
            {running
              ? <button type="button" className="btn btn-danger" onClick={stop}>■ 중단</button>
              : <button type="button" className="btn btn-primary" onClick={start}>▶ 실행</button>
            }
          </div>
          {traceUrl && (
            <div className="field" style={{ marginTop: "auto" }}>
              <a href={traceUrl} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">
                ↗ LangSmith 트레이스
              </a>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <span className="card-icon">◈</span> 실행 로그
          {running && <span className="spinner" style={{ marginLeft: 8 }} />}
          <span className="spacer" />
          <button className="btn btn-ghost btn-sm" onClick={() => setLines([])}>지우기</button>
        </div>
        <div className="output-panel" style={{ maxHeight: 440 }}>
          {lines.length === 0 && <span className="text-muted">대기 중...</span>}
          {lines.map((l, i) => (
            <div key={i} className="stream-line">
              <span className="stream-ts">{l.ts}</span>
              <span className={`stream-tag ${l.kind}`}>{l.tag}</span>
              <span className="stream-body">{l.body}</span>
            </div>
          ))}
          <div ref={endRef} />
        </div>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────── */
function ListTab({ settings }: Props) {
  const [problems, setProblems] = useState<ProblemRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [includeVariants, setIncludeVariants] = useState(false);
  const [output, setOutput] = useState<{ kind: "ok" | "err" | ""; msg: string }>({ kind: "", msg: "" });
  const [detail, setDetail] = useState<ProblemDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  async function showDetail(pid: number) {
    setDetailLoading(true);
    setDetail(null);
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

  const load = useCallback(async () => {
    setLoading(true);
    setOutput({ kind: "", msg: "" });
    try {
      const r = await adminFetch(`/api/problems?originals_only=${includeVariants ? "false" : "true"}`, settings);
      if (!r.ok) {
        const t = await r.text();
        setOutput({ kind: "err", msg: `[${r.status}] ${t.slice(0, 200)}` });
        return;
      }
      setProblems(await r.json());
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: (err as Error).message });
    } finally {
      setLoading(false);
    }
  }, [settings, includeVariants]);

  async function deleteProblem(pid: number, title: string) {
    if (!confirm(`문제 #${pid} "${title}"을(를) 삭제할까요?\n변형 문제도 함께 삭제됩니다.`)) return;
    setOutput({ kind: "", msg: `DELETE /api/problems/${pid} ...` });
    try {
      const r = await adminFetch(`/api/problems/${pid}?cascade_children=true`, settings, { method: "DELETE" });
      const body = await r.json().catch(() => ({}));
      if (r.ok) {
        setOutput({ kind: "ok", msg: `✓ 삭제 완료 — id=${pid}` });
        setProblems((p) => p.filter((pr) => pr.id !== pid));
      } else {
        setOutput({ kind: "err", msg: `[${r.status}] ${JSON.stringify(body, null, 2)}` });
      }
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: (err as Error).message });
    }
  }

  const levelColor: Record<string, string> = {
    bronze: "badge-amber", silver: "badge-gray", gold: "badge-amber",
    platinum: "badge-blue", diamond: "badge-purple",
  };

  return (
    <div>
      <div className="card">
        <div className="filter-row">
          <label className="checkbox-row">
            <input type="checkbox" checked={includeVariants} onChange={(e) => setIncludeVariants(e.target.checked)} />
            <span>변형 문제 포함</span>
          </label>
          <button className="btn btn-primary btn-sm" onClick={load} disabled={loading}>
            {loading ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "↻"}&nbsp;불러오기
          </button>
        </div>
        <div className="card-desc" style={{ marginTop: 8 }}>
          행을 클릭하면 RAG 과정과 LLM-as-a-Judge 지표(품질·변별력·비교·신규성)를 확인할 수 있습니다.
          변형 문제에 메타가 채워집니다 — "변형 문제 포함"을 켜고 조회하세요.
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th><th>제목</th><th>카테고리</th><th>난이도</th>
                <th>점수</th><th>시간 (ms)</th><th>상위 ID</th><th>등록일</th><th></th>
              </tr>
            </thead>
            <tbody>
              {problems.length === 0 ? (
                <tr className="empty-row"><td colSpan={9}>문제 없음 — 불러오기를 눌러주세요</td></tr>
              ) : problems.map((p) => (
                <tr key={p.id} style={{ cursor: "pointer" }} onClick={() => showDetail(p.id)}>
                  <td className="num">{p.id}</td>
                  <td>{p.title}</td>
                  <td><span className="badge badge-blue">{p.category}</span></td>
                  <td><span className={`badge ${levelColor[p.level] ?? "badge-gray"}`}>{p.level}</span></td>
                  <td className="num">{p.points}</td>
                  <td className="num">{p.time_limit_ms}</td>
                  <td className="num">{p.parent_id ?? "—"}</td>
                  <td className="text-sm text-muted">{fmtDate(p.created_at).slice(0, 10)}</td>
                  <td className="actions">
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={(e) => { e.stopPropagation(); deleteProblem(p.id, p.title); }}
                    >
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
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
        onUpdated={(updated) => {
          setDetail(updated);
          // 목록의 표시값(제목/카테고리/난이도/점수/시간)도 즉시 반영
          setProblems((prev) =>
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

  return (
    <div className="main problems">
      <div className="page-head">
        <h1>문제 관리</h1>
        <span className="sub">원본 등록 · LangGraph 변형 출제 · 출제 메타 조회</span>
      </div>

      <div className="tabs">
        {([
          ["create",  "원본 등록"],
          ["variant", "변형 출제"],
          ["list",    "원본 목록"],
        ] as [Tab, string][]).map(([t, label]) => (
          <button key={t} className={`tab-btn${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "create"  && <CreateTab  settings={settings} />}
      {tab === "variant" && <VariantTab settings={settings} />}
      {tab === "list"    && <ListTab    settings={settings} />}
    </div>
  );
}
