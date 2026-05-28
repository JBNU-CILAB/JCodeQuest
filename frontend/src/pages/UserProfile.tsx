import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Card, CardHead } from '../components/Card'
import { Stat, StreakGrass } from '../components/StreakGrass'
import { apiGet, ApiError } from '../lib/api'
import { identiconUrl } from '../lib/avatar'
import { tierLabel } from '../lib/tiers'
import { TierBadge } from '../components/TierBadge'
import type { PublicProfile } from '../types'

const GRADE_LABEL: Record<number, string> = {
  1: '1학년',
  2: '2학년',
  3: '3학년',
  4: '4학년',
  5: '대학원',
  6: '대학원',
}

export function UserProfile() {
  const { userId } = useParams()
  const [data, setData] = useState<PublicProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!userId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    apiGet<PublicProfile>(`/users/${userId}`)
      .then((r) => {
        if (!cancelled) setData(r)
      })
      .catch((err) => {
        if (cancelled) return
        const msg =
          err instanceof ApiError
            ? err.status === 404
              ? '존재하지 않는 사용자입니다.'
              : `${err.status} ${err.message}`
            : err instanceof Error
            ? err.message
            : 'unknown error'
        setError(msg)
        setData(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [userId])

  const stats = data?.stats ?? null
  // 익명 유저는 서버가 avatar_url을 null로 내려주므로 식별 아바타를 띄우지 않는다.
  const avatarUrl = useMemo(
    () =>
      data && !data.is_anonymous
        ? data.avatar_url || identiconUrl(String(data.user_id))
        : null,
    [data],
  )

  return (
    <main className="px-10 py-10 max-w-[1100px] mx-auto w-full">
      <div className="mb-6 flex items-center gap-3">
        <Link to="/ranking" className="text-sm text-gray-500 hover:text-gray-900">
          ← 랭킹
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">프로필</h1>
      </div>

      {loading && <p className="text-sm text-gray-500">로딩 중…</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {!loading && !error && data && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 프로필 카드 */}
          <Card className="lg:col-span-1">
            <CardHead title="프로필" icon={<span>👤</span>} />
            <div className="flex flex-col items-center gap-3 mb-2">
              {avatarUrl ? (
                <img
                  src={avatarUrl}
                  alt={data.display_name}
                  referrerPolicy="no-referrer"
                  className="w-20 h-20 rounded-full border-2 border-black/10 object-cover bg-gray-50"
                />
              ) : (
                <div className="w-20 h-20 rounded-full border-2 border-black/10 bg-gray-100 flex items-center justify-center text-2xl">
                  🐾
                </div>
              )}
              <div className="text-center">
                <div className="text-base font-semibold text-gray-900">
                  {data.display_name}
                </div>
                {data.is_anonymous && (
                  <div className="text-[11px] text-gray-400 mt-0.5">익명 사용자</div>
                )}
              </div>
              <div className="flex items-center gap-2">
                {/* MyPage와 동일 위계 — 공개 프로필도 lg + emphasize. */}
                <TierBadge tier={data.tier} size="lg" emphasize />
                <span className="text-xs text-gray-700 tabular-nums">
                  {data.exp.toLocaleString()} XP
                </span>
                {data.rank != null && (
                  <span className="text-xs text-violet-700 font-semibold tabular-nums">
                    #{data.rank}
                  </span>
                )}
              </div>
              {data.tier_progress && (
                <div className="w-full px-1">
                  <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1">
                    <span>
                      {data.tier_progress.next === null
                        ? '최고 티어'
                        : `다음 ${tierLabel(data.tier_progress.next)}까지 ${data.tier_progress.exp_to_next.toLocaleString()} XP`}
                    </span>
                    <span className="tabular-nums">
                      {Math.round(data.tier_progress.progress_pct)}%
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-gray-200 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        data.tier_progress.next === null ? 'bg-rose-500' : 'bg-indigo-500'
                      }`}
                      style={{
                        width: `${Math.min(100, Math.max(0, data.tier_progress.progress_pct))}%`,
                      }}
                    />
                  </div>
                </div>
              )}
            </div>

            {!data.is_anonymous && (
              <dl className="grid grid-cols-[80px_1fr] gap-x-4 gap-y-2.5 text-[13px] border-t border-gray-100 pt-4 mt-3">
                <dt className="text-gray-500">학년</dt>
                <dd className="text-gray-900">
                  {data.grade ? GRADE_LABEL[data.grade] ?? `${data.grade}학년` : '-'}
                </dd>
                <dt className="text-gray-500">학과</dt>
                <dd className="text-gray-900">{data.department ?? '-'}</dd>
              </dl>
            )}
          </Card>

          {/* 활동 요약 — 비익명일 때만 */}
          {!data.is_anonymous && stats ? (
            <div className="lg:col-span-2 flex flex-col gap-6">
              <Card>
                <CardHead title="활동 요약" icon={<span>📈</span>} />
                <div className="mb-3 rounded-lg border border-gray-200 bg-white px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-wider text-gray-500">
                        현재 스트릭
                      </div>
                      <div className="text-xl font-bold tabular-nums text-gray-900">
                        {stats.current_streak}일
                      </div>
                    </div>
                    <div className="flex flex-col items-end text-right">
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                        최장
                      </span>
                      <span className="text-sm font-semibold tabular-nums text-gray-700">
                        {stats.longest_streak}일
                      </span>
                    </div>
                  </div>
                  {stats.daily_solves.length > 0 && (
                    <StreakGrass days={stats.daily_solves} />
                  )}
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <Stat label="누적 제출" value={stats.total_submissions} />
                  <Stat label="해결 문제" value={stats.solved} />
                  <Stat label="누적 EXP" value={data.exp} valueClass="text-violet-600" />
                </div>
              </Card>
            </div>
          ) : (
            <div className="lg:col-span-2">
              <Card>
                <p className="text-sm text-gray-500 py-6 text-center">
                  이 사용자는 익명 표시를 설정해 활동 정보를 공개하지 않습니다.
                </p>
              </Card>
            </div>
          )}
        </div>
      )}
    </main>
  )
}
