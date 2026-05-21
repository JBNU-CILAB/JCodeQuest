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
    <div>
      <p className="card-desc mb-12">
        유저 목록을 조회하고 API 키 강제 제거 및 유저 삭제를 수행합니다.
      </p>

      <div className="card">
        <div className="filter-row">
          <div className="field wide">
            <label>검색</label>
            <input
              type="text" value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load(0)}
              placeholder="이름, 이메일..."
            />
          </div>
          <div className="field" style={{ maxWidth: 100, marginTop: "auto" }}>
            <button className="btn btn-primary" onClick={() => load(0)} disabled={loading}>
              {loading ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "검색"}
            </button>
          </div>
        </div>
        {output.msg && <div className={`output-panel ${output.kind}`}>{output.msg}</div>}
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th><th>이름</th><th>이메일</th><th>Provider</th>
                <th>EXP</th><th>제출 수</th><th>API Key</th><th>가입일</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr className="empty-row"><td colSpan={9}>결과 없음 — 검색을 눌러주세요</td></tr>
              ) : rows.map((u) => (
                <tr key={u.id}>
                  <td className="num">{u.id}</td>
                  <td>
                    {u.display_name}
                    {u.nickname && <span className="hint">({u.nickname})</span>}
                  </td>
                  <td className="text-sm text-muted">{u.email ?? "—"}</td>
                  <td>
                    <span className="badge badge-blue">{u.provider}</span>
                  </td>
                  <td className="num">{u.exp.toLocaleString()}</td>
                  <td className="num">{u.submission_count}</td>
                  <td>
                    {u.has_api_key
                      ? <span className="badge badge-green">SET</span>
                      : <span className="badge badge-gray">없음</span>
                    }
                  </td>
                  <td className="text-sm text-muted">{fmtDate(u.created_at).slice(0, 10)}</td>
                  <td className="actions">
                    <button
                      className="btn btn-ghost btn-sm"
                      disabled={!u.has_api_key}
                      onClick={() => clearApiKey(u)}
                    >
                      키 제거
                    </button>
                    <button className="btn btn-danger btn-sm" onClick={() => deleteUser(u)}>
                      삭제
                    </button>
                  </td>
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
    </div>
  );
}
