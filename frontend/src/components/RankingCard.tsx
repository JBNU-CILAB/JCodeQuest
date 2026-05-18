import { useEffect, useState } from 'react'
import { Card, CardHead } from './Card'
import { apiGet } from '../lib/api'

type LeaderboardEntry = {
  rank: number
  user_id: number
  display_name: string
  tier: string
  points: number
  avatar_url?: string | null
}

type LeaderboardResponse = {
  period: 'all' | 'week'
  week: string | null
  entries: LeaderboardEntry[]
}

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

const LIMIT = 5

export function RankingCard() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    apiGet<LeaderboardResponse>(`/leaderboard?period=week&limit=${LIMIT}`)
      .then((res) => {
        if (cancelled) return
        setEntries(res.entries)
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'fetch failed')
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <Card>
      <CardHead title="이번주 랭킹" />
      <div>
        {loading && (
          <div className="py-8 text-center text-sm text-gray-400">
            불러오는 중…
          </div>
        )}
        {!loading && error && (
          <div className="py-8 text-center text-sm text-red-500">
            랭킹을 불러오지 못했습니다 · {error}
          </div>
        )}
        {!loading && !error && entries.length === 0 && (
          <div className="py-8 text-center text-sm text-gray-400">
            이번 주 첫 AC의 주인공이 되어보세요.
          </div>
        )}
        {!loading && !error &&
          entries.map((u) => (
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
                <div className="text-sm font-semibold text-gray-800 truncate">
                  {u.display_name}
                </div>
                {u.tier && (
                  <div className="text-xs text-gray-500 mt-0.5 lowercase">
                    {u.tier}
                  </div>
                )}
              </div>
              <div className="inline-flex items-center gap-1 bg-violet-50 text-violet-600 font-bold text-[13px] px-3 py-1 rounded-full tabular-nums">
                💎 {u.points.toLocaleString()}
              </div>
            </div>
          ))}
      </div>
    </Card>
  )
}
