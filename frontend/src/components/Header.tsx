import { Link } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { useAuth } from '../lib/AuthContext'

const NAV_LINKS: Array<{ label: string; to: string }> = [
  { label: '공지', to: '#' },
  { label: '문제페이지', to: '/problems' },
  { label: '랭킹', to: '#' },
]

const TIER_STYLES: Record<string, string> = {
  bronze: 'bg-amber-700/80 text-amber-50',
  silver: 'bg-slate-400/80 text-slate-50',
  gold: 'bg-yellow-500/90 text-yellow-50',
}

export function Header() {
  const { session, profile } = useAuth()
  const loggedIn = session !== null

  const metadata = (session?.user.user_metadata ?? {}) as {
    avatar_url?: string
    picture?: string
    full_name?: string
  }
  const avatarUrl = metadata.avatar_url ?? metadata.picture
  const displayName = profile?.display_name ?? metadata.full_name ?? session?.user.email ?? ''
  const tier = profile?.tier ?? 'bronze'
  const exp = profile?.exp ?? 0

  return (
    <header className="h-[72px] px-10 flex items-center gap-6 text-white bg-gradient-to-b from-header-1 to-header-2">
      <Link
        to="/"
        className="w-[90px] h-12 bg-white rounded flex items-center justify-center text-3xl italic font-semibold text-gray-800 select-none font-display tracking-tighter"
      >
        cd
      </Link>

      {loggedIn && (
        <>
          <nav className="ml-auto flex gap-10 items-center">
            {NAV_LINKS.map(({ label, to }) => (
              <Link
                key={label}
                to={to}
                className="text-gray-200 text-[15px] font-medium pb-1.5 border-b-2 border-transparent hover:text-white hover:border-white/40 transition"
              >
                {label}
              </Link>
            ))}
          </nav>

          <div className="ml-7 flex items-center gap-3">
            {/* Exp · Tier */}
            <div className="flex flex-col items-end gap-1 text-[11px] leading-none">
              <span className="text-white/90 font-medium tracking-tight">
                {displayName}
              </span>
              <div className="flex items-center gap-1.5">
                <span
                  className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ${TIER_STYLES[tier] ?? TIER_STYLES.bronze}`}
                >
                  {tier}
                </span>
                <span className="text-white/70 text-[10px] tabular-nums">
                  {exp.toLocaleString()} XP
                </span>
              </div>
            </div>

            {/* Avatar */}
            <div className="flex flex-col items-center gap-0.5">
              {avatarUrl ? (
                <img
                  src={avatarUrl}
                  alt={displayName}
                  referrerPolicy="no-referrer"
                  className="w-9 h-9 rounded-full border-2 border-white/40 object-cover"
                />
              ) : (
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-slate-300 to-slate-400 text-white text-lg border-2 border-white/40 flex items-center justify-center">
                  🙂
                </div>
              )}
              <div className="text-[9px] text-white/70 tracking-tight">
                <button
                  onClick={() => supabase.auth.signOut()}
                  className="hover:text-white"
                >
                  로그아웃
                </button>
                <span>/</span>
                <a href="#" className="hover:text-white">마이페이지</a>
              </div>
            </div>
          </div>
        </>
      )}
    </header>
  )
}
