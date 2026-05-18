import { useCallback, useEffect, useRef, useState } from 'react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../lib/AuthContext'
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

type SlideId = 'all' | 'week' | 'grade'

const SLIDES: { id: SlideId; label: string }[] = [
  { id: 'all', label: 'GLOBAL' },
  { id: 'week', label: 'WEEK' },
  { id: 'grade', label: 'GRADE' },
]

const GRADES = [1, 2, 3, 4] as const
type Grade = (typeof GRADES)[number]

const AUTO_ROTATE_MS = 6000

const githubIdenticon = (seed: number | string) =>
  `https://github.com/identicons/${encodeURIComponent(String(seed))}.png`

function Avatar({
  entry,
  size,
}: {
  entry: LeaderboardEntry
  size: number
}) {
  const fallback = githubIdenticon(entry.user_id)
  const initial = entry.avatar_url || fallback
  const [src, setSrc] = useState(initial)

  useEffect(() => {
    setSrc(entry.avatar_url || fallback)
  }, [entry.avatar_url, fallback])

  return (
    <img
      src={src}
      onError={() => {
        if (src !== fallback) setSrc(fallback)
      }}
      width={size}
      height={size}
      alt=""
      aria-hidden
      style={{ imageRendering: 'pixelated' }}
      className="rounded-md border border-zinc-200 bg-zinc-50 object-cover"
    />
  )
}

type PodiumGeom = {
  height: number
  width: number
  liftPx: number
  highlighted: boolean
  shape: { x1: number; y1: number; x2: number; y2: number }
}

const PODIUM: Record<number, PodiumGeom> = {
  1: {
    height: 130,
    width: 200,
    liftPx: 0,
    highlighted: true,
    shape: { x1: 8, y1: 2, x2: 192, y2: 6 },
  },
  2: {
    height: 96,
    width: 200,
    liftPx: 70,
    highlighted: false,
    shape: { x1: 4, y1: 6, x2: 196, y2: 0 },
  },
  3: {
    height: 78,
    width: 200,
    liftPx: 90,
    highlighted: false,
    shape: { x1: 10, y1: 0, x2: 188, y2: 8 },
  },
}

function PodiumBlock({ rank, geom }: { rank: number; geom: PodiumGeom }) {
  const { width: w, height: h, highlighted, shape } = geom
  const stroke = highlighted ? '#10b981' : '#d4d4d8'
  const strokeWidth = highlighted ? 2 : 1
  return (
    <svg width={w} height={h} className="block">
      <polygon
        points={`${shape.x1},${shape.y1} ${shape.x2},${shape.y2} ${w - 1},${h - 1} 1,${h - 1}`}
        fill="#fafaf7"
        stroke={stroke}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
      />
      <text
        x={w / 2}
        y={h / 2 + 10}
        textAnchor="middle"
        fontSize="26"
        fontWeight="700"
        fill="#52525b"
        fontFamily="ui-monospace, SFMono-Regular, monospace"
      >
        {rank}
      </text>
    </svg>
  )
}

function PodiumColumn({ entry }: { entry: LeaderboardEntry | null | undefined }) {
  if (!entry) {
    return <div style={{ width: 200 }} aria-hidden />
  }
  const geom = PODIUM[entry.rank] ?? PODIUM[3]
  const isFirst = entry.rank === 1
  return (
    <div
      className="flex flex-col items-center"
      style={{ width: geom.width }}
    >
      <div
        className="flex flex-col items-center"
        style={{ marginTop: `${geom.liftPx}px` }}
      >
        <Avatar entry={entry} size={isFirst ? 104 : 84} />
        <div className="mt-2 flex items-center gap-1.5 font-mono text-[13px]">
          <span
            className={
              isFirst ? 'text-emerald-700 font-semibold' : 'text-zinc-500'
            }
          >
            [{entry.rank}]
          </span>
          <span className="text-zinc-900 font-medium">{entry.display_name}</span>
        </div>
        {entry.tier && (
          <div className="text-[11px] text-zinc-400 mt-0.5 lowercase">
            {entry.tier}
          </div>
        )}
        <div className="mt-1.5 flex items-baseline gap-1.5">
          <span className="text-amber-600 text-sm">◆</span>
          <span className="text-[15px] font-semibold text-zinc-900 tabular-nums">
            {entry.points.toLocaleString()}
          </span>
        </div>
        <div className="text-[10px] tracking-[0.25em] text-zinc-400 mt-0.5">
          SCORE
        </div>
      </div>
      <div className="mt-4">
        <PodiumBlock rank={entry.rank} geom={geom} />
      </div>
    </div>
  )
}

function Podium({
  rows,
  loading,
  error,
  emptyHint = 'no users yet — be the first AC.',
}: {
  rows: LeaderboardEntry[]
  loading: boolean
  error: string | null
  emptyHint?: string
}) {
  if (loading) {
    return (
      <div className="text-zinc-400 text-sm font-mono py-12 text-center">
        loading leaderboard...
      </div>
    )
  }
  if (error) {
    return (
      <div className="text-red-500 text-sm font-mono py-12 text-center">
        error: {error}
      </div>
    )
  }
  if (rows.length === 0) {
    return (
      <div className="text-zinc-400 text-sm font-mono py-12 text-center">
        {emptyHint}
      </div>
    )
  }
  const byRank = new Map(rows.map((r) => [r.rank, r]))
  return (
    <div className="flex items-end justify-center gap-4">
      <PodiumColumn entry={byRank.get(2)} />
      <PodiumColumn entry={byRank.get(1)} />
      <PodiumColumn entry={byRank.get(3)} />
    </div>
  )
}

type FetchState = {
  rows: LeaderboardEntry[]
  loading: boolean
  error: string | null
}

const EMPTY_STATE: FetchState = { rows: [], loading: true, error: null }

function useLeaderboardOnce(path: string): FetchState & { week: string | null } {
  const [state, setState] = useState<FetchState>(EMPTY_STATE)
  const [week, setWeek] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    apiGet<LeaderboardResponse>(path)
      .then((res) => {
        if (cancelled) return
        setState({ rows: res.entries, loading: false, error: null })
        setWeek(res.week)
      })
      .catch((err) => {
        if (cancelled) return
        setState({
          rows: [],
          loading: false,
          error: err instanceof Error ? err.message : 'fetch failed',
        })
      })
    return () => {
      cancelled = true
    }
  }, [path])
  return { ...state, week }
}

function GradeSlide({ active }: { active: boolean }) {
  const [grade, setGrade] = useState<Grade>(1)
  const [cache, setCache] = useState<Record<number, FetchState>>({})

  useEffect(() => {
    if (cache[grade] && !cache[grade].loading && !cache[grade].error) return
    let cancelled = false
    setCache((prev) => ({
      ...prev,
      [grade]: prev[grade] ?? { rows: [], loading: true, error: null },
    }))
    apiGet<LeaderboardResponse>(`/leaderboard/by-grade?grade=${grade}&limit=3`)
      .then((res) => {
        if (cancelled) return
        setCache((prev) => ({
          ...prev,
          [grade]: { rows: res.entries, loading: false, error: null },
        }))
      })
      .catch((err) => {
        if (cancelled) return
        setCache((prev) => ({
          ...prev,
          [grade]: {
            rows: [],
            loading: false,
            error: err instanceof Error ? err.message : 'fetch failed',
          },
        }))
      })
    return () => {
      cancelled = true
    }
  }, [grade])

  const state = cache[grade] ?? EMPTY_STATE
  return (
    <div
      className="w-full shrink-0"
      aria-hidden={!active}
      role="tabpanel"
    >
      <div className="flex justify-center gap-1.5 mb-3 text-[11px] tracking-wider">
        {GRADES.map((g) => (
          <button
            key={g}
            onClick={() => setGrade(g)}
            className={`px-2.5 py-0.5 rounded transition ${
              grade === g
                ? 'text-emerald-700 bg-emerald-100 font-semibold'
                : 'text-zinc-400 hover:text-emerald-700'
            }`}
          >
            {g}학년
          </button>
        ))}
      </div>
      <Podium
        rows={state.rows}
        loading={state.loading}
        error={state.error}
        emptyHint={`no ${grade}학년 users yet.`}
      />
    </div>
  )
}

function SimpleSlide({
  state,
  active,
  emptyHint,
}: {
  state: FetchState
  active: boolean
  emptyHint?: string
}) {
  return (
    <div className="w-full shrink-0" aria-hidden={!active} role="tabpanel">
      <div className="h-[26px] mb-3" aria-hidden />
      <Podium
        rows={state.rows}
        loading={state.loading}
        error={state.error}
        emptyHint={emptyHint}
      />
    </div>
  )
}

export function Hero() {
  const { session, profile } = useAuth()
  const loggedIn = session !== null

  const [slideIdx, setSlideIdx] = useState(0)
  const [paused, setPaused] = useState(false)
  const interactionRef = useRef(0)

  const all = useLeaderboardOnce('/leaderboard?period=all&limit=3')
  const week = useLeaderboardOnce('/leaderboard?period=week&limit=3')

  const goto = useCallback((idx: number) => {
    const wrapped = ((idx % SLIDES.length) + SLIDES.length) % SLIDES.length
    setSlideIdx(wrapped)
    interactionRef.current = Date.now()
  }, [])

  useEffect(() => {
    if (paused) return
    const t = setInterval(() => {
      // 사용자가 직전에 조작했다면 한 사이클 더 기다림
      if (Date.now() - interactionRef.current < AUTO_ROTATE_MS) return
      setSlideIdx((i) => (i + 1) % SLIDES.length)
    }, AUTO_ROTATE_MS)
    return () => clearInterval(t)
  }, [paused])

  const handleLogin = () =>
    supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: window.location.origin,
        queryParams: { hd: 'jbnu.ac.kr' },
      },
    })

  const handleLogout = () => supabase.auth.signOut()

  const weekLabel = week.week

  return (
    <section className="bg-[#faf7f2] text-zinc-900 px-6 pt-10 pb-12 font-mono">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1" />
          <div className="flex-1 text-center">
            <h1 className="text-emerald-600 text-3xl md:text-4xl font-extrabold tracking-[0.25em]">
              LEADERBOARD
            </h1>
          </div>
          <div className="flex-1 flex justify-end items-center gap-2 text-[11px] tracking-wider">
            {SLIDES.map((s, i) => (
              <button
                key={s.id}
                onClick={() => goto(i)}
                className={`px-2 py-0.5 rounded transition ${
                  slideIdx === i
                    ? 'text-emerald-700 bg-emerald-100'
                    : 'text-zinc-400 hover:text-emerald-700'
                }`}
              >
                {s.label}
                {s.id === 'week' && weekLabel && (
                  <span className="ml-1 text-emerald-600/70">{weekLabel}</span>
                )}
              </button>
            ))}
          </div>
        </div>

        <div
          className="mt-6 relative"
        >
          <div className="overflow-hidden mx-8">
            <div
              className="flex transition-transform duration-500 ease-out"
              style={{ transform: `translateX(-${slideIdx * 100}%)` }}
            >
              <SimpleSlide state={all} active={slideIdx === 0} />
              <SimpleSlide
                state={week}
                active={slideIdx === 1}
                emptyHint="no points awarded this week yet."
              />
              <GradeSlide active={slideIdx === 2} />
            </div>
          </div>

          <div className="mt-4 flex justify-center gap-1.5">
            {SLIDES.map((s, i) => (
              <button
                key={s.id}
                aria-label={`go to ${s.label}`}
                onClick={() => goto(i)}
                className={`w-2 h-2 rounded-full transition ${
                  slideIdx === i ? 'bg-emerald-600' : 'bg-zinc-300'
                }`}
              />
            ))}
          </div>
        </div>

        <div className="mt-8 pt-4 border-t border-zinc-200 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-500">
          <span>[ESC] menu</span>
          <span>[←→] slide</span>
          <span>[ENTER] view profile</span>
          {loggedIn ? (
            <span className="ml-auto flex items-center gap-3">
              <span className="text-emerald-700">
                ● {profile?.display_name ?? session?.user.email ?? 'guest'}
              </span>
              <span className="text-zinc-600 tabular-nums">
                {(profile?.exp ?? 0).toLocaleString()} XP
              </span>
              <button
                onClick={handleLogout}
                className="text-zinc-500 hover:text-emerald-700 transition"
              >
                $ logout
              </button>
            </span>
          ) : (
            <button
              onClick={handleLogin}
              className="ml-auto flex items-center gap-1 text-zinc-700 hover:text-emerald-700 transition"
            >
              <span>$ login --provider google</span>
              <span className="inline-block w-2 h-3.5 bg-emerald-500 align-middle animate-pulse" />
            </button>
          )}
        </div>
      </div>
    </section>
  )
}
