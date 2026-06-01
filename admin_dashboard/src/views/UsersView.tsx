import { Suspense, use, useCallback, useEffect, useState } from "react";
import type { ConnSettings, UserRow } from "../types";
import { judgeFetch, fmtDate } from "../api";
import { unwrap, useResource } from "../lib/resource";

interface Props { settings: ConnSettings }

type Query = { search: string; offset: number };

/** Suspense 안에서 use(promise) 로 유저 행을 읽어 렌더. mutation 후 refresh() → 이 컴포넌트만 재렌더. */
function UserRows({
  promise,
  onClearKey,
  onDelete,
  onCount,
}: {
  promise: Promise<UserRow[]>;
  onClearKey: (u: UserRow) => void;
  onDelete: (u: UserRow) => void;
  onCount: (n: number) => void;
}) {
  const rows = use(promise);
  useEffect(() => { onCount(rows.length); }, [rows.length, onCount]);
  if (rows.length === 0) {
    return (
      <tr><td colSpan={8}><div className="empty">결과 없음</div></td></tr>
    );
  }
  return (
    <>
      {rows.map((u) => (
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
            <button className="btn btn-ghost btn-sm" disabled={!u.has_api_key} onClick={() => onClearKey(u)}>키 제거</button>
            <button className="btn btn-danger-outline btn-sm" onClick={() => onDelete(u)}>삭제</button>
          </td>
        </tr>
      ))}
    </>
  );
}

export default function UsersView({ settings }: Props) {
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState<Query>({ search: "", offset: 0 });
  const [limit] = useState(50);
  const [count, setCount] = useState(0);
  const [output, setOutput] = useState<{ kind: "ok" | "err" | ""; msg: string }>({ kind: "", msg: "" });

  const fetchUsers = useCallback(async (): Promise<UserRow[]> => {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(query.offset) });
    if (query.search.trim()) qs.set("search", query.search.trim());
    return unwrap<UserRow[]>(await judgeFetch(`/api/users?${qs}`, settings));
  }, [settings, limit, query]);
  const { promise, refresh, isPending } = useResource(fetchUsers, [settings, query]);

  function runSearch() {
    setOutput({ kind: "", msg: "" });
    setQuery({ search: searchInput.trim(), offset: 0 });
  }
  function gotoOffset(off: number) {
    setQuery((q) => ({ ...q, offset: Math.max(0, off) }));
  }

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
        refresh();
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
        refresh();
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
        <span className="sub">
          {count}명 · offset {query.offset}
          {isPending && <> · <span className="spinner" style={{ width: 10, height: 10 }} /> 갱신 중…</>}
        </span>
        <div className="page-head-actions">
          <input
            className="search-wide"
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch()}
            placeholder="이름 · 이메일 검색"
            style={{ minWidth: 220 }}
          />
          <button className="btn btn-primary btn-sm" onClick={runSearch} disabled={isPending}>
            {isPending ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "검색"}
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
          <Suspense
            fallback={
              <tr><td colSpan={8}><div className="empty"><span className="spinner" style={{ width: 12, height: 12 }} /> 불러오는 중…</div></td></tr>
            }
          >
            <UserRows promise={promise} onClearKey={clearApiKey} onDelete={deleteUser} onCount={setCount} />
          </Suspense>
        </tbody>
      </table>

      {count > 0 && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
          <span className="text-muted text-sm">offset {query.offset} · {count}행</span>
          <span className="spacer" />
          <button className="btn btn-outline btn-sm" disabled={query.offset === 0 || isPending} onClick={() => gotoOffset(query.offset - limit)}>← 이전</button>
          <button className="btn btn-outline btn-sm" disabled={count < limit || isPending} onClick={() => gotoOffset(query.offset + limit)}>다음 →</button>
        </div>
      )}
    </div>
  );
}
