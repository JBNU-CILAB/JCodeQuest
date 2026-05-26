import { useState, useCallback } from "react";
import type { ConnSettings, UserRow } from "../types";
import { judgeFetch, fmtDate } from "../api";

interface Props { settings: ConnSettings }

export default function UsersView({ settings }: Props) {
  const [rows, setRows] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [limit] = useState(50);
  const [pageInfo, setPageInfo] = useState("");
  const [output, setOutput] = useState<{ kind: "ok" | "err" | ""; msg: string }>({ kind: "", msg: "" });

  const load = useCallback(async (newOffset = 0) => {
    setLoading(true);
    setOutput({ kind: "", msg: "" });
    const qs = new URLSearchParams({ limit: String(limit), offset: String(newOffset) });
    if (search.trim()) qs.set("search", search.trim());

    try {
      const r = await judgeFetch(`/api/users?${qs}`, settings);
      if (!r.ok) {
        const t = await r.text();
        setOutput({ kind: "err", msg: `[${r.status}] ${t.slice(0, 200)}` });
        return;
      }
      const data: UserRow[] = await r.json();
      setRows(data);
      setOffset(newOffset);
      setPageInfo(`offset ${newOffset} · ${data.length}행`);
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: (err as Error).message });
    } finally {
      setLoading(false);
    }
  }, [search, limit, settings]);

  async function clearApiKey(u: UserRow) {
    if (!confirm(
      `유저 #${u.id} "${u.display_name}"의 API 키를 강제 제거합니다.\n` +
      `· vault.secrets 행도 함께 삭제\n· 유저 자신이 다시 등록 가능\n\n계속할까요?`
    )) return;
    setOutput({ kind: "", msg: `DELETE /api/users/${u.id}/api-key ...` });
    try {
      const r = await judgeFetch(`/api/users/${u.id}/api-key`, settings, { method: "DELETE" });
      const body = await r.json().catch(() => ({}));
      if (r.ok) {
        setOutput({ kind: "ok", msg: `✓ API 키 제거 — user_id=${u.id}` });
        setRows((prev) => prev.map((row) => row.id === u.id ? { ...row, has_api_key: false } : row));
      } else {
        setOutput({ kind: "err", msg: `[${r.status}] ${JSON.stringify(body, null, 2)}` });
      }
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: (err as Error).message });
    }
  }

  async function deleteUser(u: UserRow) {
    if (!confirm(
      `유저 #${u.id} "${u.display_name}"을(를) 영구 삭제합니다.\n` +
      `· 제출 ${u.submission_count}건 cascade 삭제\n· 튜터 메시지·세션·API 키도 삭제\n· 되돌릴 수 없음.\n\n계속할까요?`
    )) return;
    setOutput({ kind: "", msg: `DELETE /api/users/${u.id} ...` });
    try {
      const r = await judgeFetch(`/api/users/${u.id}`, settings, { method: "DELETE" });
      const body = await r.json();
      if (r.ok) {
        const c = body.cascade ?? {};
        setOutput({
          kind: "ok",
          msg: `✓ 삭제 완료 — id=${body.id}\n  submissions: ${c.submissions}\n  tutor_messages: ${c.tutor_messages}\n  sessions: ${c.sessions}`,
        });
        setRows((prev) => prev.filter((row) => row.id !== u.id));
      } else {
        setOutput({ kind: "err", msg: `[${r.status}] ${JSON.stringify(body, null, 2)}` });
      }
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: (err as Error).message });
    }
  }

  return (
    <div className="main users">
      <div className="page-head">
        <h1>유저 / 권한</h1>
        <span className="sub">{rows.length}명{pageInfo ? ` · ${pageInfo}` : ""}</span>
        <div className="page-head-actions">
          <input
            className="search-wide"
            type="text" value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load(0)}
            placeholder="이름 · 이메일 검색"
            style={{ minWidth: 220 }}
          />
          <button className="btn btn-primary btn-sm" onClick={() => load(0)} disabled={loading}>
            {loading ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "검색"}
          </button>
        </div>
      </div>

      {output.msg && <div className={`output-panel ${output.kind}`} style={{ marginBottom: 14 }}>{output.msg}</div>}

      <table className="tbl">
        <thead>
          <tr>
            <th style={{ width: 220 }}>유저</th>
            <th>이메일</th>
            <th style={{ width: 100 }}>Provider</th>
            <th style={{ width: 100 }}>EXP</th>
            <th style={{ width: 70 }}>제출</th>
            <th style={{ width: 90 }}>API Key</th>
            <th style={{ width: 110 }}>가입일</th>
            <th style={{ width: 140 }} />
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td colSpan={8}><div className="empty">결과 없음 — 검색을 눌러주세요</div></td></tr>
          ) : rows.map((u) => (
            <tr key={u.id}>
              <td>
                <span className="avatar-pip">{(u.display_name || "?")[0].toUpperCase()}</span>
                <strong>{u.display_name}</strong>
                {u.nickname && <span style={{ color: "var(--muted)", marginLeft: 6, fontSize: 12 }}>({u.nickname})</span>}
              </td>
              <td className="mono-cell" style={{ fontSize: 12.5 }}>{u.email ?? "—"}</td>
              <td><span className="tag role-student">{u.provider}</span></td>
              <td className="mono-cell" style={{ fontVariantNumeric: "tabular-nums" }}>{u.exp.toLocaleString()} xp</td>
              <td style={{ fontVariantNumeric: "tabular-nums" }}>{u.submission_count}</td>
              <td>
                {u.has_api_key
                  ? <span className="pill done"><span className="dot" />SET</span>
                  : <span className="pill queued"><span className="dot" />없음</span>}
              </td>
              <td className="mono-cell" style={{ fontSize: 12 }}>{fmtDate(u.created_at).slice(0, 10)}</td>
              <td>
                <button className="btn btn-ghost btn-sm" disabled={!u.has_api_key} onClick={() => clearApiKey(u)}>키 제거</button>
                <button className="btn btn-danger-outline btn-sm" onClick={() => deleteUser(u)}>삭제</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {rows.length > 0 && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
          <span className="text-muted text-sm">{pageInfo}</span>
          <span className="spacer" />
          <button className="btn btn-outline btn-sm" disabled={offset === 0} onClick={() => load(Math.max(0, offset - limit))}>← 이전</button>
          <button className="btn btn-outline btn-sm" disabled={rows.length < limit} onClick={() => load(offset + limit)}>다음 →</button>
        </div>
      )}
    </div>
  );
}
