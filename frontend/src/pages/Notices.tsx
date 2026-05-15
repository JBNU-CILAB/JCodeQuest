import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiGet, ApiError } from '../lib/api'
import type { Notice } from '../types'

function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

export function Notices() {
  const [notices, setNotices] = useState<Notice[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    apiGet<Notice[]>('/notices')
      .then(setNotices)
      .catch((err) => {
        const msg = err instanceof ApiError
          ? `${err.status} ${err.message}`
          : err instanceof Error ? err.message : 'unknown error'
        setError(msg)
        setNotices(null)
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <main className="max-w-[1180px] mx-auto w-full px-8 pt-8 pb-20">
      <div className="flex items-end justify-between mb-6">
        <h1 className="text-[26px] font-extrabold text-gray-800 tracking-tight">공지사항</h1>
        {notices && (
          <span className="text-sm text-gray-500 tabular-nums">
            {notices.length}개
          </span>
        )}
      </div>

      {loading && (
        <div className="text-center py-16 text-gray-400 text-sm">불러오는 중...</div>
      )}
      {error && (
        <div className="text-center py-16 text-red-500 text-sm">
          공지를 불러오지 못했습니다 — {error}
        </div>
      )}
      {!loading && !error && notices && notices.length === 0 && (
        <div className="text-center py-16 text-gray-400 text-sm">
          등록된 공지가 없습니다.
        </div>
      )}
      {!loading && !error && notices && notices.length > 0 && (
        <ul className="bg-white border border-gray-200 rounded-xl overflow-hidden divide-y divide-gray-100">
          {notices.map((n) => (
            <li key={n.id}>
              <Link
                to={`/notices/${n.id}`}
                className="flex items-center gap-3 px-5 py-4 hover:bg-gray-50 transition"
              >
                {n.pinned && (
                  <span
                    aria-label="고정 공지"
                    className="text-xs font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700"
                  >
                    📌 고정
                  </span>
                )}
                <span className="flex-1 text-[15px] text-gray-800 font-medium truncate">
                  {n.title}
                </span>
                <span className="text-xs text-gray-400 tabular-nums shrink-0">
                  {formatDate(n.created_at)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
