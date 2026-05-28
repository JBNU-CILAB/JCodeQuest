import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiGet, ApiError } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import { TierBadge } from '../components/TierBadge'
import type { LeaderboardEntry, LeaderboardPeriod, LeaderboardResponse } from '../types'

const TOP_N = 50

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

const POINTS_LABEL: Record<LeaderboardPeriod, string> = {
  all: '누적 EXP',
  week: '이번주 점수',
}

export function Ranking() {
  const { profile } = useAuth()
  const [period, setPeriod] = useState<LeaderboardPeriod>('week')
  const [data, setData] = useState<LeaderboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    apiGet<LeaderboardResponse>(`/leaderboard?period=${period}&limit=${TOP_N}`)
      .then(setData)
      .catch((err) => {
        const msg = err instanceof ApiError
          ? `${err.status} ${err.message}`
          : err instanceof Error ? err.message : 'unknown error'
        setError(msg)
        setData(null)
      })
      .finally(() => setLoading(false))
  }, [period])

  const entries = data?.entries ?? []
  const meEntry: LeaderboardEntry | undefined = profile
    ? entries.find((e) => e.user_id === profile.id)
    : undefined
  const meInTop = meEntry !== undefined

  return (
    <main className="max-w-[920px] mx-auto w-full px-8 pt-8 pb-20">
      <div className="flex items-end justify-between mb-6 gap-4 flex-wrap">
        <div>
          <h1 className="text-[26px] font-extrabold text-gray-800 tracking-tight">
            랭킹
          </h1>
          {period === 'week' && data?.week && (
            <p className="text-xs text-gray-500 mt-1 tabular-nums">
              집계 주차: <span className="font-semibold">{data.week}</span>
            </p>
          )}
        </div>

        <div className="inline-flex bg-gray-100 rounded-full p-0.5">
          {(['week', 'all'] as LeaderboardPeriod[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-4 py-1.5 rounded-full text-sm font-semibold transition ${
                period === p ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'
              }`}
            >
              {p === 'week' ? '이번주' : '전체 누적'}
            </button>
          ))}
        </div>
      </div>

      {profile && !loading && !error && data && (
        <MyRankCard
          period={period}
          meEntry={meEntry}
          inTop={meInTop}
          topN={TOP_N}
        />
      )}

      {loading && (
        <div className="text-center py-16 text-gray-400 text-sm">불러오는 중...</div>
      )}
      {error && (
        <div className="text-center py-16 text-red-500 text-sm">
          랭킹을 불러오지 못했습니다 — {error}
        </div>
      )}
      {!loading && !error && entries.length === 0 && (
        <div className="text-center py-16 text-gray-400 text-sm">
          {period === 'week'
            ? '이번 주에는 아직 기록된 점수가 없습니다.'
            : '아직 누적 EXP를 보유한 사용자가 없습니다.'}
        </div>
      )}
      {!loading && !error && entries.length > 0 && (
        <ul className="bg-white border border-gray-200 rounded-2xl overflow-hidden divide-y divide-gray-100">
          {entries.map((u) => {
            const isMe = profile?.id === u.user_id
            // 나를 누르면 내 마이페이지, 남을 누르면 공개 프로필.
            const to = isMe ? '/mypage' : `/users/${u.user_id}`
            return (
              <li
                key={u.user_id}
                className={isMe ? 'bg-violet-50/70' : 'hover:bg-gray-50'}
              >
                <Link
                  to={to}
                  className="flex items-center gap-4 px-5 py-3.5 transition"
                >
                  <div
                    className={`w-9 h-9 rounded-full flex items-center justify-center text-base shrink-0 ${
                      MEDAL_BG[u.rank] ?? 'bg-gray-100 text-gray-600 text-sm font-bold tabular-nums'
                    }`}
                  >
                    {MEDAL_EMOJI[u.rank] ?? u.rank}
                  </div>
                  <div className="flex-1 min-w-0 flex items-center gap-2">
                    <span className="text-[15px] font-semibold text-gray-800 truncate">
                      {u.display_name}
                    </span>
                    {isMe && (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-violet-600 text-white">
                        나
                      </span>
                    )}
                    {/* Top 3 는 한 단계 큰 배지. 모든 행은 emphasize=true 라 master면 후광이 깜빡인다. */}
                    <TierBadge
                      tier={u.tier}
                      size={u.rank <= 3 ? 'md' : 'sm'}
                      emphasize
                    />
                  </div>
                  <div className="inline-flex items-center gap-1 bg-violet-50 text-violet-700 font-bold text-sm px-3 py-1 rounded-full tabular-nums shrink-0">
                    {u.points.toLocaleString()}
                    <span className="font-normal text-[10px] text-violet-500 ml-0.5">
                      {POINTS_LABEL[period]}
                    </span>
                  </div>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </main>
  )
}

interface MyRankCardProps {
  period: LeaderboardPeriod
  meEntry: LeaderboardEntry | undefined
  inTop: boolean
  topN: number
}

function MyRankCard({ period, meEntry, inTop, topN }: MyRankCardProps) {
  return (
    <div className="mb-4 bg-gradient-to-r from-violet-50 to-indigo-50 border border-violet-200 rounded-2xl px-5 py-3 flex items-center gap-4">
      <span className="text-2xl">🐾</span>
      <div className="flex-1 min-w-0 text-sm">
        {inTop && meEntry ? (
          <span className="text-gray-700">
            현재 내 순위는{' '}
            <strong className="text-violet-700 text-base tabular-nums">
              #{meEntry.rank}
            </strong>
            {' '}({meEntry.points.toLocaleString()} {POINTS_LABEL[period]})
          </span>
        ) : (
          <span className="text-gray-600">
            아직 Top {topN} 안에 들어있지 않아요.{' '}
            {period === 'week'
              ? '이번 주에 문제를 풀고 랭킹에 들어가 보세요!'
              : '문제를 풀어 EXP를 모아 보세요!'}
          </span>
        )}
      </div>
    </div>
  )
}
