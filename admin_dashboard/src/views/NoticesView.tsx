import { useState, useCallback, useEffect } from "react";
import type { ConnSettings, NoticeRow } from "../types";
import { adminFetch, fmtDate } from "../api";

interface Props { settings: ConnSettings }

const empty = { id: "", title: "", body: "", pinned: false };

export default function NoticesView({ settings }: Props) {
  const [notices, setNotices] = useState<NoticeRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState(empty);
  const [submitting, setSubmitting] = useState(false);
  const [output, setOutput] = useState<{ kind: "ok" | "err" | ""; msg: string }>({ kind: "", msg: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await adminFetch("/api/notices?limit=200", settings);
      if (!r.ok) {
        const t = await r.text();
        setOutput({ kind: "err", msg: `[${r.status}] ${t.slice(0, 200)}` });
        return;
      }
      setNotices(await r.json());
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: (err as Error).message });
    } finally {
      setLoading(false);
    }
  }, [settings]);

  useEffect(() => { load(); }, []);

  function editNotice(n: NoticeRow) {
    setForm({ id: String(n.id), title: n.title, body: n.body, pinned: n.pinned });
    setOutput({ kind: "", msg: "" });
  }

  function resetForm() {
    setForm(empty);
    setOutput({ kind: "", msg: "" });
  }

  async function deleteNotice(nid: number, title: string) {
    if (!confirm(`공지 #${nid} "${title}"을(를) 삭제할까요?`)) return;
    setOutput({ kind: "", msg: `DELETE /api/notices/${nid} ...` });
    try {
      const r = await adminFetch(`/api/notices/${nid}`, settings, { method: "DELETE" });
      const body = await r.json().catch(() => ({}));
      if (r.ok) {
        setOutput({ kind: "ok", msg: `✓ 삭제 완료 — id=${nid}` });
        if (form.id === String(nid)) resetForm();
        setNotices((p) => p.filter((n) => n.id !== nid));
      } else {
        setOutput({ kind: "err", msg: `[${r.status}] ${JSON.stringify(body, null, 2)}` });
      }
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: (err as Error).message });
    }
  }

  async function submitForm(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim() || !form.body.trim()) {
      setOutput({ kind: "err", msg: "제목과 본문은 필수입니다" });
      return;
    }
    setSubmitting(true);
    const path = form.id ? `/api/notices/${form.id}` : "/api/notices";
    const method = form.id ? "PATCH" : "POST";
    try {
      const r = await adminFetch(path, settings, {
        method,
        body: JSON.stringify({ title: form.title, body: form.body, pinned: form.pinned }),
      });
      const body = await r.text();
      let pretty = body;
      try { pretty = JSON.stringify(JSON.parse(body), null, 2); } catch {}
      setOutput({ kind: r.ok ? "ok" : "err", msg: `[${r.status}] ${r.ok ? "성공" : "실패"}\n\n${pretty}` });
      if (r.ok) { resetForm(); load(); }
    } catch (err: unknown) {
      setOutput({ kind: "err", msg: (err as Error).message });
    } finally {
      setSubmitting(false);
    }
  }

  const isEditing = !!form.id;

  return (
    <div>
      <p className="card-desc mb-12">
        유저에게 노출되는 공지를 작성·수정·삭제합니다.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16, alignItems: "start" }}>
        {/* 공지 목록 */}
        <div className="card" style={{ padding: "16px 20px" }}>
          <div className="card-title" style={{ marginBottom: 0 }}>
            <span className="card-icon">◈</span> 공지 목록
            <span className="spacer" />
            <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
              {loading ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "↻"}&nbsp;새로고침
            </button>
          </div>
          <div className="divider" style={{ margin: "12px 0" }} />
          {notices.length === 0
            ? <div className="text-muted text-sm" style={{ padding: "24px 0", textAlign: "center" }}>공지 없음</div>
            : notices.map((n) => (
              <div key={n.id} className="notice-item">
                <div className="notice-info">
                  <div className="notice-title-row">
                    {n.pinned && <span className="badge badge-amber">📌 고정</span>}
                    <span className="notice-name">{n.title}</span>
                  </div>
                  <div className="notice-meta">
                    #{n.id} · 등록 {fmtDate(n.created_at).slice(0, 10)}
                    {n.updated_at !== n.created_at && ` · 수정 ${fmtDate(n.updated_at).slice(0, 10)}`}
                  </div>
                </div>
                <div className="notice-actions">
                  <button className="btn btn-ghost btn-sm" onClick={() => editNotice(n)}>수정</button>
                  <button className="btn btn-danger btn-sm" onClick={() => deleteNotice(n.id, n.title)}>삭제</button>
                </div>
              </div>
          ))}
        </div>

        {/* 작성/수정 폼 */}
        <div className="card">
          <div className="card-title">
            <span className="card-icon">◈</span>
            {isEditing ? `공지 #${form.id} 수정` : "새 공지 작성"}
          </div>
          <form onSubmit={submitForm}>
            <div className="field mb-12">
              <label>제목</label>
              <input
                type="text"
                value={form.title}
                onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))}
                placeholder="공지 제목"
                required
              />
            </div>
            <div className="field mb-12">
              <label>본문 (Markdown)</label>
              <textarea
                value={form.body}
                onChange={(e) => setForm((p) => ({ ...p, body: e.target.value }))}
                placeholder="공지 내용..."
                rows={8}
                required
              />
            </div>
            <div className="mb-12">
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={form.pinned}
                  onChange={(e) => setForm((p) => ({ ...p, pinned: e.target.checked }))}
                />
                <span>상단 고정</span>
              </label>
            </div>

            {output.msg && <div className={`output-panel ${output.kind}`} style={{ marginBottom: 12 }}>{output.msg}</div>}

            <div className="row">
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? <span className="spinner" style={{ width: 12, height: 12 }} /> : (isEditing ? "수정 저장" : "등록")}
              </button>
              {isEditing && (
                <button type="button" className="btn btn-ghost" onClick={resetForm}>취소</button>
              )}
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
