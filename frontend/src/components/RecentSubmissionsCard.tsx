import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardHead } from './Card'
import { apiGet, ApiError } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import type {
  RecentSubmissionItem,
  RecentSubmissionsResponse,
  SubmissionListItem,
  SubmissionListResponse,
} from '../types'

type Mode = 'all' | 'mine'

const VERDICT_COLOR: Record<string, string> = {
  AC: 'text-emerald-600',
  SUS: 'text-red-600',
}

const PAGE_SIZE = 10

function formatRelative(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const diff = Date.now() - t
  if (diff < 60_000) return '방금 전'
  const m = Math.floor(diff / 60_000)
  if (m < 60) return `${m}분 전`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}시간 전`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d}일 전`
  const dt = new Date(iso)
  const mm = String(dt.getMonth() + 1).padStart(2, '0')
  const dd = String(dt.getDate()).padStart(2, '0')
  return `${dt.getFullYear()}-${mm}-${dd}`
}

function verdictLabel(item: { final_verdict: string | null; status: string }): string {
  if (item.final_verdict === 'AC') return '맞았습니다'
  if (item.final_verdict === 'SUS') return '틀렸습니다'
  if (item.status === 'queued') return '대기 중'
  if (item.status === 'running') return '채점 중'
  if (item.status === 'failed') return '실패'
  return item.status
}

function formatMs(ms: number | null): string {
  return ms != null ? `${ms} ms` : '-'
}

function formatMem(kb: number | null): string {
  return kb != null ? `${(kb / 1024).toFixed(1)} MB` : '-'
}

type Row = {
  id: number
  problemId: number
  problemLabel: string
  userLabel: string | null
  verdict: string | null
  status: string
  elapsedMs: number | null
  memoryKb: number | null
  pointsAwarded: number | null
  createdAt: string
}

function rowFromRecent(r: RecentSubmissionItem): Row {
  return {
    id: r.id,
    problemId: r.problem_id,
    problemLabel: r.problem_title ?? `#${r.problem_id}`,
    userLabel: r.user_display_name,
    verdict: r.final_verdict,
    status: r.status,
    elapsedMs: r.max_elapsed_ms,
    memoryKb: r.peak_memory_kb,
    pointsAwarded: r.points_awarded,
    createdAt: r.created_at,
  }
}

function rowFromMine(r: SubmissionListItem): Row {
  return {
    id: r.id,
    problemId: r.problem_id,
    problemLabel: `#${r.problem_id}`,
    userLabel: null,
    verdict: r.final_verdict,
    status: r.status,
    elapsedMs: r.max_elapsed_ms,
    memoryKb: r.peak_memory_kb,
    pointsAwarded: r.points_awarded,
    createdAt: r.created_at,
  }
}

export function RecentSubmissionsCard() {
  const { session } = useAuth()
  const [mode, setMode] = useState<Mode>('all')
  const [rows, setRows] = useState<Row[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setRows(null)

    const fetcher: Promise<Row[]> =
      mode === 'all'
        ? apiGet<RecentSubmissionsResponse>(`/submissions/recent?limit=${PAGE_SIZE}`).then((r) =>
            r.items.map(rowFromRecent),
          )
        : apiGet<SubmissionListResponse>(`/me/submissions?limit=${PAGE_SIZE}`).then((r) =>
            r.items.map(rowFromMine),
          )

    fetcher
      .then((items) => {
        if (!cancelled) setRows(items)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [mode, session?.access_token])

  const headers =
    mode === 'all'
      ? ['문제', '사용자', '결과', '시간', '메모리', '제출 시각']
      : ['문제', '결과', '시간', '메모리', '점수', '제출 시각', '']

  return (
    <Card>
      <CardHead
        icon={<span className="font-mono">‹/›</span>}
        title="최근 제출"
        right={
          <div className="flex items-center gap-1 text-xs">
            <button
              type="button"
              onClick={() => setMode('all')}
              className={`px-2 py-1 rounded transition ${
                mode === 'all'
                  ? 'bg-emerald-50 text-emerald-700 font-semibold'
                  : 'text-gray-500 hover:text-emerald-700'
              }`}
            >
              전체 보기
            </button>
            <span className="text-gray-300">·</span>
            <button
              type="button"
              onClick={() => setMode('mine')}
              className={`px-2 py-1 rounded transition ${
                mode === 'mine'
                  ? 'bg-emerald-50 text-emerald-700 font-semibold'
                  : 'text-gray-500 hover:text-emerald-700'
              }`}
            >
              내 제출 보기
            </button>
          </div>
        }
      />

      {loading && <p className="text-xs text-gray-500 px-2 py-3">불러오는 중…</p>}
      {error && (
        <p className="text-xs text-red-600 px-2 py-3">제출 조회 실패: {error}</p>
      )}
      {!loading && !error && rows && rows.length === 0 && (
        <p className="text-xs text-gray-500 px-2 py-3">
          {mode === 'mine' ? (
            <>
              아직 제출한 풀이가 없어요.{' '}
              <Link to="/problems" className="underline text-gray-700">
                문제 풀러 가기 →
              </Link>
            </>
          ) : (
            '아직 제출 기록이 없어요.'
          )}
        </p>
      )}

      {!loading && !error && rows && rows.length > 0 && (
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-gray-500 text-xs font-semibold">
              {headers.map((h) => (
                <th
                  key={h}
                  className="text-left px-2 py-3 border-b border-gray-100 font-semibold"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className="border-b border-gray-50 last:border-none">
                <td className="px-2 py-3">
                  <Link
                    to={`/problems/${s.problemId}`}
                    className="text-gray-900 hover:underline"
                  >
                    {s.problemLabel}
                  </Link>
                </td>
                {mode === 'all' && (
                  <td className="px-2 py-3 text-gray-700">{s.userLabel ?? '-'}</td>
                )}
                <td
                  className={`px-2 py-3 font-bold ${
                    s.verdict ? VERDICT_COLOR[s.verdict] ?? '' : 'text-gray-400'
                  }`}
                >
                  {verdictLabel({ final_verdict: s.verdict, status: s.status })}
                </td>
                <td className="px-2 py-3 tabular-nums text-gray-700">{formatMs(s.elapsedMs)}</td>
                <td className="px-2 py-3 tabular-nums text-gray-700">{formatMem(s.memoryKb)}</td>
                {mode === 'mine' && (
                  <td className="px-2 py-3 tabular-nums text-gray-700">
                    {s.pointsAwarded ?? '-'}
                  </td>
                )}
                <td className="px-2 py-3 text-gray-500 tabular-nums">
                  {formatRelative(s.createdAt)}
                </td>
                {mode === 'mine' && (
                  <td className="px-2 py-3 text-right">
                    <Link
                      to={`/submissions/${s.id}`}
                      className="text-xs text-gray-500 hover:text-gray-900"
                    >
                      상세 →
                    </Link>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}
