import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardHead } from './Card'
import { apiGet, ApiError } from '../lib/api'
import type { LeaderboardEntry, LeaderboardResponse } from '../types'

const PREVIEW_LIMIT = 5

const MEDAL_BG: Record<number, string> = {
  1: 'bg-yellow-100',
  2: 'bg-gray-200',
  3: 'bg-orange-200',
}
const MEDAL_EMOJI: Record<number, string> = {
  1: '🥇',
  2: '🥈',
  3: '🥉',
}

export function RankingCard() {
  const [entries, setEntries] = useState<LeaderboardEntry[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    apiGet<LeaderboardResponse>(`/leaderboard?period=week&limit=${PREVIEW_LIMIT}`)
      .then((res) => setEntries(res.entries))
      .catch((err) => {
        const msg = err instanceof ApiError
          ? `${err.status}`
          : err instanceof Error ? err.message : 'unknown'
        setError(msg)
      })
      .finally(() => setLoading(false))
  }, [])

  const right = (
    <Link
      to="/ranking"
      className="text-xs font-semibold text-violet-600 hover:text-violet-700"
    >
      전체 보기 →
    </Link>
  )

  return (
    <Card>
      <CardHead title="이번주 랭킹" right={right} />
      <div>
        {loading && (
          <div className="py-8 text-center text-xs text-gray-400">불러오는 중...</div>
        )}
        {error && (
          <div className="py-8 text-center text-xs text-red-500">
            랭킹을 불러오지 못했습니다 — {error}
          </div>
        )}
        {!loading && !error && entries && entries.length === 0 && (
          <div className="py-8 text-center text-xs text-gray-400">
            이번 주 기록이 아직 없습니다.
          </div>
        )}
        {!loading && !error && entries && entries.length > 0 && entries.map((u) => (
          <div
            key={u.user_id}
            className="flex items-center gap-3.5 py-2.5 border-b border-gray-100 last:border-none"
          >
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-base shrink-0 ${
                MEDAL_BG[u.rank] ?? 'bg-gray-100 text-gray-500 text-sm font-bold'
              }`}
            >
              {MEDAL_EMOJI[u.rank] ?? u.rank}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-gray-800 truncate">{u.display_name}</div>
              <div className="text-xs text-gray-500 mt-0.5 uppercase tracking-wider">
                {u.tier}
              </div>
            </div>
            <div className="inline-flex items-center gap-1 bg-violet-50 text-violet-600 font-bold text-[13px] px-3 py-1 rounded-full tabular-nums">
              {u.points.toLocaleString()}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
