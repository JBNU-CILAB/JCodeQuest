import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'
import { apiGet, ApiError } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import { ProfileSetupModal } from '../components/ProfileSetupModal'
import { ProfileRequiredModal } from '../components/ProfileRequiredModal'
import { formatIsoWeekKo } from '../lib/isoWeek'
import type {
  ProblemLevel,
  ProblemSummary,
  SubmissionListResponse,
} from '../types'

const LEVEL_FILTERS: Array<{ value: ProblemLevel | 'all'; label: string }> = [
  { value: 'all', label: '전체' },
  { value: 'bronze', label: 'Bronze' },
  { value: 'silver', label: 'Silver' },
  { value: 'gold', label: 'Gold' },
]

const LEVEL_LABEL: Record<ProblemLevel, string> = {
  bronze: 'Bronze',
  silver: 'Silver',
  gold: 'Gold',
}

const LEVEL_BADGE_STYLE: Record<ProblemLevel, string> = {
  bronze: 'bg-amber-100 text-amber-800 border border-amber-200',
  silver: 'bg-slate-100 text-slate-700 border border-slate-200',
  gold: 'bg-yellow-100 text-yellow-800 border border-yellow-300',
}

interface ProblemCardProps {
  problem: ProblemSummary
  idx: number
  open: boolean
  solved: boolean
  onClick: () => void
}

function HoverProblemCard({
  problem,
  idx,
  open,
  solved,
  onClick,
}: ProblemCardProps) {
  const [hover, setHover] = useState(false)
  const hoverTimer = useRef<number | null>(null)

  const enter = () => {
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current)
    hoverTimer.current = window.setTimeout(() => setHover(true), 220)
  }
  const leave = () => {
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current)
    setHover(false)
  }

  // Stagger only on initial open so re-renders (filter change) don't replay.
  const animation = open
    ? `card-pop 0.42s ${idx * 60}ms var(--ease-out-cubic) both`
    : undefined

  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={enter}
      onMouseLeave={leave}
      onFocus={enter}
      onBlur={leave}
      className="relative flex flex-col gap-1.5 bg-white border border-line rounded-2xl px-5 py-4 text-left w-full cursor-pointer transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-[3px] hover:shadow-[0_10px_24px_-8px_rgba(31,41,55,0.12)] hover:border-brand/40"
      style={{ animation, zIndex: hover ? 40 : undefined }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span
          className={`px-2 py-0.5 text-[11px] font-bold rounded-full ${LEVEL_BADGE_STYLE[problem.level]}`}
        >
          {LEVEL_LABEL[problem.level]}
        </span>
        <span className="text-[11px] text-gray-500 px-2 py-0.5 rounded-full bg-gray-100">
          {problem.category}
        </span>
        <span className="ml-auto text-[13px] font-bold text-brand tabular-nums">
          {problem.points} pt
        </span>
      </div>

      <h3 className="text-[15px] font-bold text-gray-800 leading-snug">
        {problem.title}
      </h3>
      <p className="text-[12.5px] text-gray-500 leading-relaxed line-clamp-2">
        {problem.one_line_summary}
      </p>

      {solved && (
        <span
          className="absolute top-3.5 right-3.5 w-2.5 h-2.5 rounded-full bg-brand"
          style={{ boxShadow: '0 0 0 3px rgba(49, 130, 246, 0.18)' }}
          aria-label="해결됨"
        />
      )}

      {hover && (
        <div
          className="absolute left-0 right-0 z-30 bg-gray-800 text-gray-100 rounded-2xl px-5 py-4 pointer-events-none"
          style={{
            top: 'calc(100% + 10px)',
            boxShadow: '0 18px 40px -10px rgba(0,0,0,0.4)',
            animation:
              'preview-pop-up 0.22s var(--ease-out-cubic)',
          }}
        >
          <span
            className="absolute w-3 h-3 bg-gray-800 rotate-45"
            style={{ left: 30, top: -6 }}
            aria-hidden
          />
          <h4
            className="text-[12px] font-bold uppercase mb-1.5"
            style={{ color: '#7aa9f7', letterSpacing: '0.08em' }}
          >
            preview
          </h4>
          <div className="text-white font-bold mb-1 leading-snug">
            {problem.title}
          </div>
          <div className="text-gray-300 text-[12.5px] leading-relaxed mb-2 line-clamp-3">
            {problem.one_line_summary}
          </div>
          <dl
            className="grid gap-y-1 mt-1.5 text-gray-300 text-[12px]"
            style={{ gridTemplateColumns: '72px 1fr', columnGap: 12 }}
          >
            <dt className="text-gray-400 text-[11px]">분류</dt>
            <dd>{problem.category}</dd>
            <dt className="text-gray-400 text-[11px]">난이도</dt>
            <dd>{LEVEL_LABEL[problem.level]}</dd>
            <dt className="text-gray-400 text-[11px]">배점</dt>
            <dd className="tabular-nums">{problem.points} pt</dd>
            <dt className="text-gray-400 text-[11px]">상태</dt>
            <dd>{solved ? '✓ 해결' : '— 미해결'}</dd>
          </dl>
        </div>
      )}
    </button>
  )
}

interface WeekSectionProps {
  week: string
  items: ProblemSummary[]
  defaultOpen: boolean
  solvedIds: Set<number>
  onOpenProblem: (id: number) => void
}

function WeekSection({
  week,
  items,
  defaultOpen,
  solvedIds,
  onOpenProblem,
}: WeekSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  const bodyRef = useRef<HTMLDivElement | null>(null)
  // 'auto' once we've finished opening — keeps hover popovers from being clipped.
  const [bodyHeight, setBodyHeight] = useState<number | 'auto'>(
    defaultOpen ? 'auto' : 0,
  )

  useEffect(() => {
    if (!bodyRef.current) return
    if (open) {
      const h = bodyRef.current.scrollHeight
      setBodyHeight(h)
      const t = window.setTimeout(() => setBodyHeight('auto'), 420)
      return () => window.clearTimeout(t)
    } else {
      const h = bodyRef.current.scrollHeight
      setBodyHeight(h)
      requestAnimationFrame(() => setBodyHeight(0))
    }
  }, [open, items.length])

  const solvedCount = items.filter((p) => solvedIds.has(p.id)).length
  const pct = items.length ? Math.round((solvedCount / items.length) * 100) : 0

  if (items.length === 0) return null

  return (
    <section className="mb-7">
      <div
        className="flex items-center gap-4 px-1 py-3.5 cursor-pointer select-none border-b border-dashed border-transparent hover:border-black/10 transition-colors"
        onClick={() => setOpen((o) => !o)}
        role="button"
        aria-expanded={open}
      >
        <span
          className="inline-flex items-center justify-center w-6 h-6 text-brand"
          style={{
            transition: 'transform 0.32s var(--ease-overshoot)',
            transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path
              d="M5 3l4 4-4 4"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <h2
          className="text-[20px] font-extrabold text-gray-800"
          style={{ letterSpacing: '0.02em' }}
        >
          {week ? formatIsoWeekKo(week) : '주차 미지정'}
        </h2>
        {week && (
          <span className="text-[13px] text-gray-500 font-mono tabular-nums">
            {week}
          </span>
        )}
        <div
          className="flex-1 max-w-[240px] h-1 bg-line rounded-full overflow-hidden"
          title={`${solvedCount}/${items.length} 해결`}
        >
          <span
            className="block h-full rounded-full"
            style={{
              width: `${pct}%`,
              background:
                'linear-gradient(90deg, var(--color-brand), #7aa9f7)',
              transition: 'width 0.6s var(--ease-out-cubic)',
            }}
          />
        </div>
        <span className="ml-auto text-[13px] text-gray-500 tabular-nums">
          {solvedCount}/{items.length}개
        </span>
      </div>

      <div
        ref={bodyRef}
        style={{
          height: bodyHeight,
          overflow: bodyHeight === 'auto' ? 'visible' : 'hidden',
          transition: 'height 0.4s var(--ease-out-cubic)',
        }}
      >
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 pt-3">
          {items.map((p, i) => (
            <HoverProblemCard
              key={p.id}
              problem={p}
              idx={i}
              open={open}
              solved={solvedIds.has(p.id)}
              onClick={() => onOpenProblem(p.id)}
            />
          ))}
        </div>
      </div>
    </section>
  )
}

export function Problems() {
  const { session, profile } = useAuth()
  const navigate = useNavigate()
  const [problems, setProblems] = useState<ProblemSummary[] | null>(null)
  const [allCategories, setAllCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [solvedIds, setSolvedIds] = useState<Set<number>>(new Set())

  const [category, setCategory] = useState<string>('all')
  const [level, setLevel] = useState<ProblemLevel | 'all'>('all')
  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [profileRequiredOpen, setProfileRequiredOpen] = useState(false)
  const [pendingProblemId, setPendingProblemId] = useState<number | null>(null)

  const handleOpenProfileModal = useCallback(() => {
    setProfileModalOpen(true)
  }, [])

  const metadata = (session?.user.user_metadata ?? {}) as {
    grade?: number
    department?: string
    nickname?: string
    anonymous?: boolean
  }
  const hasCompleteProfile =
    session !== null &&
    Boolean(metadata.grade) &&
    Boolean(metadata.department) &&
    Boolean(metadata.nickname) &&
    typeof metadata.anonymous === 'boolean'

  const handleOpenProblem = useCallback(
    (id: number) => {
      if (!session) {
        navigate(`/problems/${id}`)
        return
      }
      if (!hasCompleteProfile) {
        setPendingProblemId(id)
        setProfileRequiredOpen(true)
        return
      }
      navigate(`/problems/${id}`)
    },
    [session, hasCompleteProfile, navigate],
  )

  const groupedByWeek = useMemo(() => {
    if (!problems) return [] as Array<{ week: string; items: ProblemSummary[] }>
    const map = new Map<string, ProblemSummary[]>()
    for (const p of problems) {
      const key = p.iso_week || ''
      const bucket = map.get(key)
      if (bucket) bucket.push(p)
      else map.set(key, [p])
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0))
      .map(([week, items]) => ({ week, items }))
  }, [problems])

  useEffect(() => {
    setLoading(true)
    setError(null)

    const params = new URLSearchParams()
    if (category !== 'all') params.set('category', category)
    if (level !== 'all') params.set('level', level)
    const qs = params.toString()
    const path = qs ? `/problems?${qs}` : '/problems'

    apiGet<ProblemSummary[]>(path)
      .then((data) => {
        setProblems(data)
        if (category === 'all' && level === 'all') {
          const cats = Array.from(new Set(data.map((p) => p.category))).sort()
          setAllCategories(cats)
        }
      })
      .catch((err) => {
        const msg =
          err instanceof ApiError
            ? `${err.status} ${err.message}`
            : err instanceof Error
              ? err.message
              : 'unknown error'
        setError(msg)
        setProblems(null)
      })
      .finally(() => setLoading(false))
  }, [category, level])

  // 로그인 사용자의 AC된 problem_id 모음 — 카드 dot + 주차 진행률용.
  useEffect(() => {
    if (!session) {
      setSolvedIds(new Set())
      return
    }
    let cancelled = false
    apiGet<SubmissionListResponse>('/me/submissions?limit=200')
      .then((res) => {
        if (cancelled) return
        const ids = new Set<number>()
        for (const s of res.items) {
          if (s.final_verdict === 'AC') ids.add(s.problem_id)
        }
        setSolvedIds(ids)
      })
      .catch(() => {
        if (!cancelled) setSolvedIds(new Set())
      })
    return () => {
      cancelled = true
    }
  }, [session?.access_token])

  return (
    <main
      className="max-w-[1180px] mx-auto w-full px-8 pt-8 pb-20"
      style={{ animation: 'view-fade 0.32s ease-out' }}
    >
      <div className="flex items-end justify-between mb-6">
        <h1 className="text-[28px] font-extrabold text-gray-800 tracking-tight">
          문제 목록
        </h1>
        {problems && (
          <span className="text-sm text-gray-500 tabular-nums">
            {problems.length}개
          </span>
        )}
      </div>

      {/* 필터 */}
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <label className="flex items-center gap-2 text-[13px] text-gray-500">
          <span>카테고리</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="border border-line rounded-full pl-3.5 pr-8 py-1.5 text-[13px] bg-white focus:outline-none focus:border-brand appearance-none"
            style={{
              backgroundImage:
                "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6' fill='none'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%23374151' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E\")",
              backgroundRepeat: 'no-repeat',
              backgroundPosition: 'right 12px center',
            }}
          >
            <option value="all">전체</option>
            {allCategories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>

        <div className="ml-auto inline-flex items-center gap-1 bg-white border border-line rounded-full p-1">
          {LEVEL_FILTERS.map((f) => {
            const active = level === f.value
            return (
              <button
                key={f.value}
                onClick={() => setLevel(f.value)}
                className={`px-3.5 py-1.5 text-[12px] font-semibold rounded-full transition ${
                  active
                    ? 'bg-brand text-white'
                    : 'text-gray-500 hover:text-gray-800'
                }`}
              >
                {f.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* 결과 */}
      {loading && (
        <div className="text-center py-16 text-gray-400 text-sm">
          불러오는 중...
        </div>
      )}
      {error && (
        <div className="text-center py-16 text-red-500 text-sm">
          문제 목록을 불러오지 못했습니다 — {error}
        </div>
      )}
      {!loading && !error && problems && problems.length === 0 && (
        <div className="text-center py-16 text-gray-400 text-sm">
          조건에 맞는 문제가 없습니다.
        </div>
      )}
      {!loading && !error && problems && problems.length > 0 && (
        <div className="flex flex-col">
          {groupedByWeek.map(({ week, items }, i) => (
            <WeekSection
              key={week || 'unknown'}
              week={week}
              items={items}
              defaultOpen={i === 0}
              solvedIds={solvedIds}
              onOpenProblem={handleOpenProblem}
            />
          ))}
        </div>
      )}

      <ProfileRequiredModal
        open={profileRequiredOpen}
        onClose={() => {
          setProfileRequiredOpen(false)
          setPendingProblemId(null)
        }}
        onSetupProfile={() => {
          setProfileRequiredOpen(false)
          handleOpenProfileModal()
        }}
      />

      <ProfileSetupModal
        open={profileModalOpen}
        onClose={() => {
          setProfileModalOpen(false)
          // 프로필 설정이 끝났다고 가정하고 보류 중이던 문제로 진입.
          if (pendingProblemId !== null) {
            const id = pendingProblemId
            setPendingProblemId(null)
            navigate(`/problems/${id}`)
          }
        }}
        initial={{
          grade: profile?.grade,
          department: profile?.department,
          nickname: profile?.nickname,
        }}
      />
    </main>
  )
}
