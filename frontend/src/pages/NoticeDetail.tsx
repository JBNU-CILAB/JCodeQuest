import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { apiGet, ApiError } from '../lib/api'
import type { Notice } from '../types'

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function NoticeDetail() {
  const { id } = useParams<{ id: string }>()
  const noticeId = id ? parseInt(id, 10) : NaN

  const [notice, setNotice] = useState<Notice | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (Number.isNaN(noticeId)) {
      setError('유효하지 않은 공지 ID')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    apiGet<Notice>(`/notices/${noticeId}`)
      .then(setNotice)
      .catch((err) => {
        const msg = err instanceof ApiError
          ? `${err.status} ${err.message}`
          : err instanceof Error ? err.message : 'unknown error'
        setError(msg)
        setNotice(null)
      })
      .finally(() => setLoading(false))
  }, [noticeId])

  return (
    <main className="max-w-[860px] mx-auto w-full px-8 pt-8 pb-20">
      <Link
        to="/notices"
        className="inline-flex items-center text-sm text-gray-500 hover:text-gray-800 transition mb-6"
      >
        ← 공지 목록
      </Link>

      {loading && (
        <div className="text-center py-16 text-gray-400 text-sm">불러오는 중...</div>
      )}
      {error && (
        <div className="text-center py-16 text-red-500 text-sm">
          공지를 불러오지 못했습니다 — {error}
        </div>
      )}
      {!loading && !error && notice && (
        <article className="bg-white border border-gray-200 rounded-xl p-8">
          <header className="border-b border-gray-100 pb-5 mb-6">
            <div className="flex items-center gap-2 mb-2">
              {notice.pinned && (
                <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700">
                  📌 고정
                </span>
              )}
            </div>
            <h1 className="text-2xl font-extrabold text-gray-800 tracking-tight">
              {notice.title}
            </h1>
            <p className="mt-2 text-xs text-gray-400 tabular-nums">
              {formatDateTime(notice.created_at)}
              {notice.updated_at !== notice.created_at && (
                <span className="ml-2 text-gray-300">
                  (수정 {formatDateTime(notice.updated_at)})
                </span>
              )}
            </p>
          </header>

          <div className="prose prose-sm max-w-none text-gray-700 [&_pre]:bg-gray-900 [&_pre]:text-gray-100 [&_pre]:rounded-lg [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[12px] [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_a]:text-blue-600 [&_a]:underline">
            <ReactMarkdown>{notice.body}</ReactMarkdown>
          </div>
        </article>
      )}
    </main>
  )
}
