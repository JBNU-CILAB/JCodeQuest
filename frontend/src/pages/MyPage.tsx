import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { AvatarEditorModal } from '../components/AvatarEditorModal'
import { Card, CardHead } from '../components/Card'
import { ProfileSetupModal } from '../components/ProfileSetupModal'
import { useAuth } from '../lib/AuthContext'
import { apiGet, apiPatch, ApiError } from '../lib/api'
import { resolveAvatarUrl } from '../lib/avatar'
import { supabase } from '../lib/supabase'
import type { StreakResponse, SubmissionListResponse } from '../types'

const TIER_STYLES: Record<string, string> = {
  bronze: 'bg-amber-700/80 text-amber-50',
  silver: 'bg-slate-400/80 text-slate-50',
  gold: 'bg-yellow-500/90 text-yellow-50',
}

const GRADE_LABEL: Record<number, string> = {
  1: '1학년',
  2: '2학년',
  3: '3학년',
  4: '4학년',
  5: '대학원',
  6: '대학원',
}

const VERDICT_COLOR: Record<string, string> = {
  AC: 'text-emerald-600',
  SUS: 'text-red-600',
}

const GRASS_COLOR = (count: number): string => {
  if (count <= 0) return 'bg-gray-200'
  if (count === 1) return 'bg-emerald-200'
  if (count === 2) return 'bg-emerald-400'
  if (count === 3) return 'bg-emerald-600'
  return 'bg-emerald-800'
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const yy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${yy}-${mm}-${dd} ${hh}:${mi}`
}

export function MyPage() {
  const { session, profile, loading, profileError, refreshProfile } = useAuth()
  const navigate = useNavigate()
  const [submissions, setSubmissions] = useState<SubmissionListResponse | null>(null)
  const [subsError, setSubsError] = useState<string | null>(null)
  const [subsLoading, setSubsLoading] = useState(false)
  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [avatarModalOpen, setAvatarModalOpen] = useState(false)
  const [anonymousPending, setAnonymousPending] = useState(false)
  const [anonymousError, setAnonymousError] = useState<string | null>(null)
  const [streak, setStreak] = useState<StreakResponse | null>(null)
  const [streakError, setStreakError] = useState<string | null>(null)

  const metadata = (session?.user.user_metadata ?? {}) as {
    custom_avatar_url?: string | null
    avatar_url?: string
    picture?: string
    full_name?: string
    grade?: number
    department?: string
    nickname?: string
    anonymous?: boolean
  }
  const avatarSeed = session?.user.id ?? session?.user.email ?? 'anon'
  const avatarUrl = resolveAvatarUrl(metadata, avatarSeed)
  const hasCustomAvatar = !!metadata.custom_avatar_url

  const grade = profile?.grade ?? metadata.grade ?? null
  const department = profile?.department ?? metadata.department ?? null
  const nickname = profile?.nickname ?? metadata.nickname ?? null
  // 익명 표시는 backend가 단일 source of truth. profile이 로드되기 전엔
  // Supabase user_metadata를 임시로 보여주되, 토글 갱신은 PATCH /me로만 한다.
  const anonymous =
    profile?.is_anonymous ?? metadata.anonymous ?? null

  useEffect(() => {
    if (!session) return
    let cancelled = false
    setSubsLoading(true)
    apiGet<SubmissionListResponse>('/me/submissions?limit=20')
      .then((r) => {
        if (!cancelled) setSubmissions(r)
      })
      .catch((err) => {
        if (cancelled) return
        setSubsError(err instanceof ApiError ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setSubsLoading(false)
      })

    apiGet<StreakResponse>('/me/streak')
      .then((r) => {
        if (!cancelled) setStreak(r)
      })
      .catch((err) => {
        if (cancelled) return
        setStreakError(err instanceof ApiError ? err.message : String(err))
      })

    return () => {
      cancelled = true
    }
  }, [session?.access_token])

  const handleToggleAnonymous = async (next: boolean) => {
    setAnonymousPending(true)
    setAnonymousError(null)
    try {
      // backend가 단일 source of truth — 리더보드/최근 제출 마스킹이 이 값을 쓴다.
      await apiPatch('/me', { is_anonymous: next })
      // Supabase user_metadata는 ProblemCard의 "프로필 완료" 체크 같은 클라이언트 측
      // 분기에서 아직 참조하므로 동기적으로 같이 업데이트한다. 실패해도 토글 자체는
      // backend에 이미 반영됐으니 무시.
      await supabase.auth
        .updateUser({ data: { anonymous: next } })
        .catch(() => undefined)
      await refreshProfile()
    } catch (e) {
      setAnonymousError(e instanceof Error ? e.message : '저장 실패')
    } finally {
      setAnonymousPending(false)
    }
  }

  const stats = useMemo(() => {
    const items = submissions?.items ?? []
    const ac = items.filter((s) => s.final_verdict === 'AC').length
    const sus = items.filter((s) => s.final_verdict === 'SUS').length
    const solved = new Set(
      items.filter((s) => s.final_verdict === 'AC').map((s) => s.problem_id),
    ).size
    return { total: submissions?.total ?? items.length, ac, sus, solved }
  }, [submissions])

  if (loading) {
    return <main className="px-10 py-10 text-sm text-gray-500">로딩 중…</main>
  }

  if (!session) {
    return <Navigate to="/" replace />
  }

  const displayName = profile?.display_name ?? metadata.full_name ?? session.user.email ?? ''
  const tier = profile?.tier ?? 'bronze'
  const exp = profile?.exp ?? 0
  const email = profile?.email ?? session.user.email ?? null

  return (
    <main className="px-10 py-10 max-w-[1100px] mx-auto w-full">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">마이페이지</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 프로필 카드 */}
        <Card className="lg:col-span-1">
          <CardHead title="내 프로필" icon={<span>👤</span>} />
          <div className="flex flex-col items-center gap-3 mb-5">
            <button
              type="button"
              onClick={() => setAvatarModalOpen(true)}
              aria-label="프로필 이미지 변경"
              title="프로필 이미지 변경"
              className="group relative rounded-full focus:outline-none focus:ring-2 focus:ring-gray-800/30"
            >
              <img
                src={avatarUrl}
                alt={displayName}
                referrerPolicy="no-referrer"
                className="w-20 h-20 rounded-full border-2 border-black/10 object-cover bg-gray-50"
              />
              <span className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-full bg-black/0 group-hover:bg-black/40 transition">
                <span className="text-[11px] font-medium text-white opacity-0 group-hover:opacity-100 transition">
                  변경
                </span>
              </span>
            </button>
            <div className="text-center">
              <div className="text-base font-semibold text-gray-900">{displayName}</div>
              {email && <div className="text-xs text-gray-500 mt-0.5">{email}</div>}
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                  TIER_STYLES[tier] ?? TIER_STYLES.bronze
                }`}
              >
                {tier}
              </span>
              <span className="text-xs text-gray-700 tabular-nums">
                {exp.toLocaleString()} XP
              </span>
              <label
                className="ml-1 inline-flex items-center gap-1 text-xs text-gray-700 cursor-pointer select-none"
                title={
                  anonymous === null
                    ? '미설정'
                    : anonymous
                    ? '닉네임으로 표시'
                    : '실명으로 표시'
                }
              >
                <input
                  type="checkbox"
                  checked={anonymous === true}
                  disabled={anonymousPending}
                  onChange={(e) => handleToggleAnonymous(e.target.checked)}
                  className="h-3.5 w-3.5 rounded accent-gray-900 cursor-pointer disabled:opacity-50"
                />
                <span>익명 표시</span>
              </label>
            </div>
            {anonymousError && (
              <p className="text-[11px] text-red-600">{anonymousError}</p>
            )}
          </div>

          <dl className="grid grid-cols-[80px_1fr] gap-x-4 gap-y-2.5 text-[13px] border-t border-gray-100 pt-4">
            <dt className="text-gray-500">학년</dt>
            <dd className="text-gray-900">{grade ? GRADE_LABEL[grade] ?? `${grade}학년` : '-'}</dd>
            <dt className="text-gray-500">학과</dt>
            <dd className="text-gray-900">{department ?? '-'}</dd>
            <dt className="text-gray-500">닉네임</dt>
            <dd className="text-gray-900">{nickname ?? '-'}</dd>
            <dt className="text-gray-500">API 키</dt>
            <dd className="text-gray-900">
              {profile?.has_api_key ? (
                'true'
              ) : (
                <Link to="/settings/api-key" className="text-amber-700 underline underline-offset-2">
                  false — 등록하기 →
                </Link>
              )}
            </dd>
          </dl>

          <div className="mt-5 flex gap-2">
            <button
              type="button"
              onClick={() => setProfileModalOpen(true)}
              className="flex-1 rounded-md bg-gray-900 px-3 py-2 text-xs font-semibold text-white hover:bg-gray-800 transition"
            >
              프로필 수정
            </button>
            <button
              type="button"
              onClick={() => supabase.auth.signOut().then(() => navigate('/', { replace: true }))}
              className="flex-1 rounded-md bg-gray-100 px-3 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-200 transition"
            >
              로그아웃
            </button>
          </div>

          {profileError && (
            <p className="mt-4 text-[11px] text-red-600">
              프로필 조회 실패: {profileError}
            </p>
          )}
        </Card>

        {/* 통계 + 최근 제출 */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          <Card>
            <CardHead title="활동 요약" icon={<span>📈</span>} />
            <div className="mb-3 rounded-lg border border-gray-200 bg-white px-4 py-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wider text-gray-500">
                      현재 스트릭
                    </div>
                    <div className="text-xl font-bold tabular-nums text-gray-900">
                      {streak ? `${streak.current_streak}일` : '–'}
                    </div>
                  </div>
                </div>
                <div className="flex flex-col items-end text-right">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                    최장
                  </span>
                  <span className="text-sm font-semibold tabular-nums text-gray-700">
                    {streak ? `${streak.longest_streak}일` : '–'}
                  </span>
                  {streak?.last_solved_date && (
                    <span className="mt-0.5 text-[10px] text-gray-500 tabular-nums">
                      최근 풀이 {streak.last_solved_date}
                    </span>
                  )}
                </div>
              </div>

              {streak && (streak.daily_solves?.length ?? 0) > 0 && (
                <StreakGrass days={streak.daily_solves} />
              )}
            </div>
            {streakError && (
              <p className="mb-3 text-[11px] text-red-600">
                스트릭 조회 실패: {streakError}
              </p>
            )}
            <div className="grid grid-cols-4 gap-3">
              <Stat label="누적 제출" value={stats.total} />
              <Stat label="AC" value={stats.ac} valueClass="text-emerald-600" />
              <Stat label="SUS" value={stats.sus} valueClass="text-red-600" />
              <Stat label="해결 문제" value={stats.solved} />
            </div>
          </Card>

          <Card>
            <CardHead
              title="최근 제출"
              icon={<span className="font-mono">‹/›</span>}
              right={
                submissions && submissions.total > submissions.items.length ? (
                  <span className="text-gray-500 text-xs">
                    최근 {submissions.items.length}건 / 전체 {submissions.total}건
                  </span>
                ) : undefined
              }
            />
            {subsLoading && <p className="text-xs text-gray-500">불러오는 중…</p>}
            {subsError && (
              <p className="text-xs text-red-600">제출 이력 조회 실패: {subsError}</p>
            )}
            {!subsLoading && !subsError && submissions && submissions.items.length === 0 && (
              <p className="text-xs text-gray-500">
                아직 제출한 풀이가 없어요.{' '}
                <Link to="/problems" className="underline text-gray-700">
                  문제 풀러 가기 →
                </Link>
              </p>
            )}
            {submissions && submissions.items.length > 0 && (
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-gray-500 text-xs font-semibold">
                    {['문제', '결과', '모드', '시간', '메모리', '점수', '제출 시각', ''].map((h) => (
                      <th
                        key={h}
                        className="text-left px-2 py-2.5 border-b border-gray-100 font-semibold"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {submissions.items.map((s) => (
                    <tr key={s.id} className="border-b border-gray-50 last:border-none">
                      <td className="px-2 py-2.5">
                        <Link
                          to={`/problems/${s.problem_id}`}
                          className="text-gray-900 hover:underline"
                        >
                          #{s.problem_id}
                        </Link>
                      </td>
                      <td
                        className={`px-2 py-2.5 font-bold ${
                          s.final_verdict ? VERDICT_COLOR[s.final_verdict] ?? '' : 'text-gray-400'
                        }`}
                      >
                        {s.final_verdict ?? s.status}
                      </td>
                      <td className="px-2 py-2.5 text-gray-600">{s.mode ?? '-'}</td>
                      <td className="px-2 py-2.5 tabular-nums text-gray-700">
                        {s.max_elapsed_ms != null ? `${s.max_elapsed_ms} ms` : '-'}
                      </td>
                      <td className="px-2 py-2.5 tabular-nums text-gray-700">
                        {s.peak_memory_kb != null
                          ? `${(s.peak_memory_kb / 1024).toFixed(1)} MB`
                          : '-'}
                      </td>
                      <td className="px-2 py-2.5 tabular-nums text-gray-700">
                        {s.points_awarded ?? '-'}
                      </td>
                      <td className="px-2 py-2.5 text-gray-500 tabular-nums">
                        {formatDate(s.created_at)}
                      </td>
                      <td className="px-2 py-2.5 text-right">
                        <Link
                          to={`/submissions/${s.id}`}
                          className="text-xs text-gray-500 hover:text-gray-900"
                        >
                          상세 →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      </div>

      <ProfileSetupModal
        open={profileModalOpen}
        onClose={() => {
          setProfileModalOpen(false)
          void refreshProfile()
        }}
        initial={{
          grade: profile?.grade,
          department: profile?.department,
          nickname: profile?.nickname,
        }}
      />

      <AvatarEditorModal
        open={avatarModalOpen}
        onClose={() => setAvatarModalOpen(false)}
        currentUrl={avatarUrl}
        hasCustom={hasCustomAvatar}
      />
    </main>
  )
}

function Stat({
  label,
  value,
  valueClass = 'text-gray-900',
}: {
  label: string
  value: number
  valueClass?: string
}) {
  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
      <div className="text-[11px] font-semibold text-gray-500">{label}</div>
      <div className={`text-2xl font-bold tabular-nums mt-1 ${valueClass}`}>{value}</div>
    </div>
  )
}

const CELL_PX = 12
const CELL_GAP_PX = 3

type Cell = { date: string; count: number } | null

function StreakGrass({ days }: { days: { date: string; count: number }[] }) {
  if (days.length === 0) return null

  const firstDate = new Date(`${days[0].date}T00:00:00`)
  const startDow = firstDate.getDay() // 0=Sun ... 6=Sat

  const cells: Cell[] = []
  for (let i = 0; i < startDow; i++) cells.push(null)
  for (const d of days) cells.push(d)
  while (cells.length % 7 !== 0) cells.push(null)
  const numWeeks = cells.length / 7

  // 각 주(컬럼)의 대표 월을 잡아 연속 컬럼들로 span 생성.
  const monthSpans: { label: string; startCol: number; endCol: number }[] = []
  let currentMonth = -1
  let currentSpan: { label: string; startCol: number; endCol: number } | null = null
  for (let w = 0; w < numWeeks; w++) {
    let weekMonth: number | null = null
    for (let r = 0; r < 7; r++) {
      const c = cells[w * 7 + r]
      if (c) {
        weekMonth = new Date(`${c.date}T00:00:00`).getMonth()
        break
      }
    }
    if (weekMonth === null) continue
    if (weekMonth !== currentMonth) {
      if (currentSpan) monthSpans.push(currentSpan)
      currentSpan = { label: `${weekMonth + 1}월`, startCol: w, endCol: w }
      currentMonth = weekMonth
    } else if (currentSpan) {
      currentSpan.endCol = w
    }
  }
  if (currentSpan) monthSpans.push(currentSpan)

  const gridWidth = numWeeks * CELL_PX + (numWeeks - 1) * CELL_GAP_PX

  return (
    <div className="mt-3 overflow-x-auto pb-1">
      <div style={{ width: `${gridWidth}px` }}>
        {/* 월 라벨 */}
        <div
          className="text-[10px] text-gray-500 leading-none mb-1 h-3"
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${numWeeks}, ${CELL_PX}px)`,
            columnGap: `${CELL_GAP_PX}px`,
          }}
        >
          {monthSpans.map((s, i) => (
            <div
              key={i}
              className="whitespace-nowrap overflow-visible"
              style={{ gridColumn: `${s.startCol + 1} / ${s.endCol + 2}` }}
            >
              {s.label}
            </div>
          ))}
        </div>

        {/* 잔디 격자 */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${numWeeks}, ${CELL_PX}px)`,
            gridTemplateRows: `repeat(7, ${CELL_PX}px)`,
            gridAutoFlow: 'column',
            gap: `${CELL_GAP_PX}px`,
          }}
        >
          {cells.map((cell, i) =>
            cell ? (
              <div key={i} className="relative group">
                <div
                  className={`h-3 w-3 rounded-[2px] ${GRASS_COLOR(cell.count)}`}
                />
                <div
                  role="tooltip"
                  className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:block whitespace-nowrap rounded-md bg-gray-900 px-2 py-1 text-[10px] font-medium text-white shadow-md z-20"
                >
                  {cell.date} · {cell.count}문제
                  <span className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
                </div>
              </div>
            ) : (
              <div key={i} className="h-3 w-3" />
            ),
          )}
        </div>

        {/* 범례 */}
        <div className="mt-2 flex items-center justify-end gap-1 text-[10px] text-gray-500">
          <span>적음</span>
          {[0, 1, 2, 3, 4].map((n) => (
            <span key={n} className={`h-2.5 w-2.5 rounded-sm ${GRASS_COLOR(n)}`} />
          ))}
          <span>많음</span>
        </div>
      </div>
    </div>
  )
}
