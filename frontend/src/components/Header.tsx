import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { resolveAvatarUrl } from '../lib/avatar'
import { supabase } from '../lib/supabase'
import { useAuth } from '../lib/AuthContext'
import { tierLabel, tierStyle } from '../lib/tiers'
import { ProfileSetupModal } from './ProfileSetupModal'

const LOGO_FRAMES = Array.from({ length: 8 }, (_, i) => `/logo/image${i + 1}.png`)
const LOGO_FRAME_MS = 250

const NAV_LINKS: Array<{ label: string; to: string }> = [
  { label: '공지', to: '/notices' },
  { label: '문제페이지', to: '/problems' },
  { label: '랭킹', to: '/ranking' },
]

export function Header() {
  const { session, profile } = useAuth()
  const navigate = useNavigate()
  const loggedIn = session !== null
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    LOGO_FRAMES.forEach((src) => {
      const img = new Image()
      img.src = src
    })
    const id = setInterval(() => {
      setFrame((f) => (f + 1) % LOGO_FRAMES.length)
    }, LOGO_FRAME_MS)
    return () => clearInterval(id)
  }, [])

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
  const avatarUrl = session ? resolveAvatarUrl(metadata, avatarSeed) : null
  const displayName = profile?.display_name ?? metadata.full_name ?? session?.user.email ?? ''
  const tier = profile?.tier ?? 'beginner'
  const exp = profile?.exp ?? 0
  const needsApiKey = loggedIn && profile !== null && !profile?.has_api_key
  const needsProfile =
    loggedIn &&
    profile !== null &&
    (!profile.grade || !profile.department || !profile.nickname)
  const showBadge = needsApiKey || needsProfile

  const [profileModalOpen, setProfileModalOpen] = useState(false)

  const handleAvatarClick = () => {
    if (needsProfile) {
      setProfileModalOpen(true)
    } else {
      navigate('/mypage')
    }
  }

  return (
    <header className="h-[72px] px-10 flex items-center gap-6 text-black bg-white border-b border-black/10">
      <Link
        to="/"
        aria-label="홈"
        className="flex items-center select-none"
      >
       <p
          className="text-3xl font-black tracking-widest"
          style={{
            color: "#000000",
            textShadow: `
              2px 2px 0px rgba(49, 130, 246, 0.6),  /* toss-blue */
              -2px -2px 0px rgba(244, 63, 94, 0.4)  /* 로즈 핑크 */
            `,
          }}
        >
        J-CodeQuest
      </p>
      </Link>

      <nav className="ml-auto flex gap-10 items-center">
        {NAV_LINKS.map(({ label, to }) => (
          <Link
            key={label}
            to={to}
            className="text-black text-[15px] font-medium pb-1.5 border-b-2 border-transparent hover:text-black hover:border-black/40 transition"
          >
            {label}
          </Link>
        ))}
      </nav>

      {!loggedIn && (
        <button
          onClick={() =>
            supabase.auth.signInWithOAuth({
              provider: 'google',
              options: {
                redirectTo: window.location.origin,
                queryParams: { hd: 'jbnu.ac.kr' },
              },
            })
          }
          className="ml-7 text-black text-[15px] font-medium pb-1.5 border-b-2 border-transparent hover:border-black/40 transition"
        >
          로그인
        </button>
      )}

      {loggedIn && (
        <>
          <div className="ml-7 flex items-center gap-3">
            {/* Avatar */}
            <div className="relative flex flex-col items-center gap-0.5 group">
              <button
                type="button"
                onClick={handleAvatarClick}
                aria-label={needsProfile ? '프로필 설정' : '마이페이지'}
                className="rounded-full focus:outline-none focus:ring-2 focus:ring-black/30"
              >
                {avatarUrl && (
                  <img
                    src={avatarUrl}
                    alt={displayName}
                    referrerPolicy="no-referrer"
                    className="w-9 h-9 rounded-full border-2 border-black/20 object-cover bg-gray-50 cursor-pointer"
                  />
                )}
              </button>

              {showBadge && (
                <span
                  aria-label="설정 필요 알림"
                  className="absolute top-0 right-0 w-2.5 h-2.5 rounded-full bg-red-500 ring-2 ring-white animate-pulse pointer-events-none"
                />
              )}

              <div className="absolute top-full right-0 pt-2 z-50 opacity-0 invisible group-hover:opacity-100 group-hover:visible focus-within:opacity-100 focus-within:visible transition-opacity duration-150">
                <div className="min-w-[220px] flex flex-col bg-white border border-black/10 rounded-md shadow-lg text-[12px] text-black/80 overflow-hidden">
                  {/* Exp · Tier */}
                  <div className="flex flex-col items-start gap-1 text-[11px] leading-none px-3 py-2.5 border-b border-black/10 bg-black/[0.02]">
                    <span className="text-black font-medium tracking-tight">
                      {displayName}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${tierStyle(tier)}`}
                      >
                        {tierLabel(tier)}
                      </span>
                      <span className="text-black/70 text-[10px] tabular-nums">
                        {exp.toLocaleString()} XP
                      </span>
                    </div>
                  </div>

                  {needsProfile && (
                    <div className="flex items-start gap-2 px-3 py-2.5 border-b border-amber-200 bg-amber-50 text-amber-900">
                      <span className="text-base leading-none mt-0.5">🪪</span>
                      <div className="flex flex-col gap-1.5 min-w-0">
                        <p className="text-[11px] leading-snug">
                          학년·학과·닉네임을 등록하면<br />
                          <strong className="font-semibold">랭킹에 정확히 표시</strong>됩니다.
                        </p>
                        <button
                          type="button"
                          onClick={() => setProfileModalOpen(true)}
                          className="self-start text-[11px] font-semibold text-amber-700 hover:text-amber-900 underline underline-offset-2"
                        >
                          프로필 설정하기 →
                        </button>
                      </div>
                    </div>
                  )}

                  {needsApiKey && (
                    <div className="flex items-start gap-2 px-3 py-2.5 border-b border-amber-200 bg-amber-50 text-amber-900">
                      <span className="text-base leading-none mt-0.5">⚠️</span>
                      <div className="flex flex-col gap-1.5 min-w-0">
                        <p className="text-[11px] leading-snug">
                          AI 튜터 서비스를 받고 싶다면<br />
                          <strong className="font-semibold">API 키를 등록해주세요!</strong>
                        </p>
                        <Link
                          to="/settings/api-key"
                          className="self-start text-[11px] font-semibold text-amber-700 hover:text-amber-900 underline underline-offset-2"
                        >
                          API 키 등록하기 →
                        </Link>
                      </div>
                    </div>
                  )}

                  <div className="flex flex-col py-1">
                    <Link
                      to="/mypage"
                      className="px-3 py-1.5 text-left hover:bg-black/5 hover:text-black transition"
                    >
                      마이페이지
                    </Link>
                    <button
                      onClick={() => supabase.auth.signOut()}
                      className="px-3 py-1.5 text-left hover:bg-black/5 hover:text-black transition"
                    >
                      로그아웃
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      <ProfileSetupModal
        open={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
        initial={{
          grade: profile?.grade,
          department: profile?.department,
          nickname: profile?.nickname,
        }}
      />
    </header>
  )
}
