import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../lib/AuthContext'
import { apiGet } from '../lib/api'

type LeaderboardEntry = {
  rank: number
  user_id: number
  display_name: string
  tier: string
  points: number
}

type LeaderboardResponse = {
  period: 'all' | 'week'
  week: string | null
  entries: LeaderboardEntry[]
}

const RANK_COLOR: Record<number, string> = {
  1: 'text-yellow-300',
  2: 'text-zinc-300',
  3: 'text-amber-400',
}

const MAX_SCORE = 1500

export function Hero() {
  const { session, profile } = useAuth()
  const loggedIn = session !== null

  const [period, setPeriod] = useState<'all' | 'week'>('all')

  const [allTop, setAllTop] = useState<LeaderboardEntry[]>([])
  const [allLoading, setAllLoading] = useState(true)
  const [allError, setAllError] = useState<string | null>(null)

  const [weekTop, setWeekTop] = useState<LeaderboardEntry[]>([])
  const [weekLabel, setWeekLabel] = useState<string | null>(null)
  const [weekLoading, setWeekLoading] = useState(true)
  const [weekError, setWeekError] = useState<string | null>(null)

  useEffect(() => {
    apiGet<LeaderboardResponse>('/leaderboard?period=all&limit=3')
      .then((res) => setAllTop(res.entries))
      .catch((err) => setAllError(err instanceof Error ? err.message : 'fetch failed'))
      .finally(() => setAllLoading(false))

    apiGet<LeaderboardResponse>('/leaderboard?period=week&limit=3')
      .then((res) => {
        setWeekTop(res.entries)
        setWeekLabel(res.week)
      })
      .catch((err) => setWeekError(err instanceof Error ? err.message : 'fetch failed'))
      .finally(() => setWeekLoading(false))
  }, [])

  useEffect(() => {
    const id = setTimeout(() => {
      setPeriod((p) => (p === 'all' ? 'week' : 'all'))
    }, 5000)
    return () => clearTimeout(id)
  }, [period])

  const renderBoard = (
    rows: LeaderboardEntry[],
    loading: boolean,
    error: string | null,
  ) => {
    const nameLen = rows.length ? Math.max(...rows.map((u) => u.display_name.length)) : 12
    return (
      <div className="flex flex-col gap-2.5">
        {loading && (
          <div className="text-emerald-500/60 text-xs">$ loading leaderboard...</div>
        )}
        {!loading && error && (
          <div className="text-red-400/80 text-xs">$ error: {error}</div>
        )}
        {!loading && !error && rows.length === 0 && (
          <div className="text-emerald-500/60 text-xs">
            $ no users yet — be the first AC.
          </div>
        )}
        {rows.map((u) => {
          const pct = Math.min(100, Math.round((u.points / MAX_SCORE) * 100))
          return (
            <div key={u.user_id} className="flex items-center gap-3">
              <span
                className={`shrink-0 font-bold ${RANK_COLOR[u.rank] ?? 'text-emerald-300'}`}
              >
                [{u.rank}]
              </span>
              <span
                className="shrink-0 text-zinc-100 whitespace-nowrap"
                style={{ minWidth: `${nameLen}ch` }}
              >
                {u.display_name}
              </span>
              <div
                className="flex-1 h-4 bg-emerald-900/40 border border-emerald-500/20 relative overflow-hidden"
                role="progressbar"
                aria-valuenow={u.points}
                aria-valuemin={0}
                aria-valuemax={MAX_SCORE}
              >
                <div
                  className="h-full bg-emerald-400/80 shadow-[0_0_8px_rgba(52,211,153,0.4)] transition-[width] duration-700"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="shrink-0 w-24 text-right text-emerald-200 tabular-nums">
                {u.points.toLocaleString()}{' '}
                <span className="text-emerald-500/70">XP</span>
              </span>
            </div>
          )
        })}
      </div>
    )
  }

  const handleLogin = () =>
    supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    })

  const handleLogout = () => supabase.auth.signOut()

  return (
    <section className="bg-[#0a0e14] font-mono text-emerald-300 h-[380px] overflow-hidden px-6 py-6 flex flex-col">
      {/* Window chrome */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900/70 border border-emerald-500/20 rounded-t-md">
        <span className="w-2.5 h-2.5 rounded-full bg-red-400/70" />
        <span className="w-2.5 h-2.5 rounded-full bg-yellow-400/70" />
        <span className="w-2.5 h-2.5 rounded-full bg-green-400/70" />
        <span className="ml-3 text-xs text-zinc-400">~/J-CodeQuest/leaderboard — zsh</span>
        <div className="ml-auto flex items-center gap-1 text-[11px] tracking-wider">
          <button
            onClick={() => setPeriod('all')}
            className={`px-2 py-0.5 rounded transition ${
              period === 'all'
                ? 'text-emerald-300 bg-emerald-500/15'
                : 'text-zinc-500 hover:text-emerald-300'
            }`}
          >
            GLOBAL
          </button>
          <span className="text-zinc-600">·</span>
          <button
            onClick={() => setPeriod('week')}
            className={`px-2 py-0.5 rounded transition ${
              period === 'week'
                ? 'text-emerald-300 bg-emerald-500/15'
                : 'text-zinc-500 hover:text-emerald-300'
            }`}
          >
            WEEK
            {weekLabel && (
              <span className="ml-1 text-emerald-500/70">{weekLabel}</span>
            )}
          </button>
        </div>
      </div>

      {/* Terminal body */}
      <div className="flex-1 border border-t-0 border-emerald-500/20 bg-black/95 rounded-b-md px-6 py-5 flex flex-col gap-4 text-[13px] leading-relaxed">
        {/* Prompt */}
        <div className="flex items-center flex-wrap gap-x-1">
          <span className="text-pink-400">user@jcq</span>
          <span className="text-zinc-500">:</span>
          <span className="text-sky-400">~</span>
          <span className="text-zinc-500">$</span>
          <span className="ml-1 text-zinc-100">
            {period === 'all'
              ? 'jcq leaderboard --global --top 3'
              : `jcq leaderboard --week ${weekLabel ?? 'current'} --top 3`}
          </span>
        </div>

        {/* Slide window: ALL / WEEK */}
        <div className="mt-1 overflow-hidden">
          <div
            className="flex transition-transform duration-300 ease-out"
            style={{
              transform: period === 'all' ? 'translateX(0)' : 'translateX(-100%)',
            }}
          >
            <div className="w-full shrink-0" aria-hidden={period !== 'all'}>
              {renderBoard(allTop, allLoading, allError)}
            </div>
            <div className="w-full shrink-0" aria-hidden={period !== 'week'}>
              {renderBoard(weekTop, weekLoading, weekError)}
            </div>
          </div>
        </div>

        {/* Status line */}
        <div className="mt-auto pt-3 border-t border-emerald-500/15 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-500">
          <span>[ESC] menu</span>
          <span>[↑↓] nav</span>
          <span>[ENTER] view profile</span>
          {loggedIn ? (
            <span className="ml-auto flex items-center gap-3">
              <span className="text-emerald-400">
                ● {profile?.display_name ?? session?.user.email ?? 'guest'}
              </span>
              <span className="text-zinc-400 tabular-nums">
                {(profile?.exp ?? 0).toLocaleString()} XP
              </span>
              <button
                onClick={handleLogout}
                className="text-zinc-400 hover:text-emerald-300 transition"
              >
                $ logout
              </button>
            </span>
          ) : (
            <button
              onClick={handleLogin}
              className="ml-auto flex items-center gap-1 text-zinc-200 hover:text-emerald-300 transition"
            >
              <span>$ login --provider google</span>
              <span className="inline-block w-2 h-3.5 bg-emerald-300 align-middle animate-pulse" />
            </button>
          )}
        </div>
      </div>
    </section>
  )
}
