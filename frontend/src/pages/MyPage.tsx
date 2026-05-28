import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { AvatarEditorModal } from '../components/AvatarEditorModal'
import { Card, CardHead } from '../components/Card'
import { ProfileSetupModal } from '../components/ProfileSetupModal'
import { Stat, StreakGrass } from '../components/StreakGrass'
import { useAuth } from '../lib/AuthContext'
import { apiGet, apiPatch, ApiError } from '../lib/api'
import { resolveAvatarUrl } from '../lib/avatar'
import { supabase } from '../lib/supabase'
import { tierLabel } from '../lib/tiers'
import { TierBadge } from '../components/TierBadge'
import type { StreakResponse, SubmissionListResponse } from '../types'

const GRADE_LABEL: Record<number, string> = {
  1: '1학년',
  2: '2학년',
  3: '3학년',
  4: '4학년',
  5: '대학원',
  6: '대학원',
}

const VERDICT_COLOR: Record<string, string> = {
  AC: 'text-blue-600',
  SUS: 'text-red-600',
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
  const tier = profile?.tier ?? 'beginner'
  const exp = profile?.exp ?? 0
  const email = profile?.email ?? session.user.email ?? null
  const tierProgress = profile?.tier_progress ?? null

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
              {/* 본인 프로필 — lg + emphasize 로 가장 화려하게. */}
              <TierBadge tier={tier} size="lg" emphasize />
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

          {tierProgress && (
            <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5">
              <div className="flex items-center justify-between text-[11px] text-gray-600 mb-1.5">
                <span>
                  {tierProgress.next === null ? (
                    <span className="font-semibold text-rose-700">최고 티어 도달</span>
                  ) : (
                    <>
                      다음 티어 <span className="font-semibold">{tierLabel(tierProgress.next)}</span>
                      까지 <span className="tabular-nums">{tierProgress.exp_to_next.toLocaleString()}</span> XP
                    </>
                  )}
                </span>
                <span className="tabular-nums text-gray-500">
                  {Math.round(tierProgress.progress_pct)}%
                </span>
              </div>
              <div className="h-2 rounded-full bg-gray-200 overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    tierProgress.next === null ? 'bg-rose-500' : 'bg-indigo-500'
                  }`}
                  style={{ width: `${Math.min(100, Math.max(0, tierProgress.progress_pct))}%` }}
                />
              </div>
              {tierProgress.max_exp > 0 && (
                <p className="mt-1.5 text-[10px] text-gray-400 tabular-nums">
                  시스템 총 가용 XP {tierProgress.max_exp.toLocaleString()} — 문제가 늘면 임계가
                  올라갑니다.
                </p>
              )}
            </div>
          )}

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
              <Stat label="AC" value={stats.ac} valueClass="text-blue-600" />
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
