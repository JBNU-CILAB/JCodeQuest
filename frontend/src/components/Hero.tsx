import type { Session } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'
import { Button } from './Button'

interface HeroProps {
  session: Session | null
}

export function Hero({ session }: HeroProps) {
  const loggedIn = session !== null

  const handleLogin = () =>
    supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    })

  const handleLogout = () => supabase.auth.signOut()

  return (
    <section
      className="relative h-[380px] overflow-hidden"
      style={{
        background:
          'linear-gradient(180deg, #b6e0f7 0%, #d6eef9 55%, #e8f4d8 70%, #a7d893 100%)',
      }}
    >
      {/* Decorative leaves */}
      <span className="absolute top-[-8px] left-[-8px] text-[56px] leading-none rotate-[-25deg] drop-shadow-md">🌿</span>
      <span className="absolute top-[-8px] right-[-8px] text-[56px] leading-none rotate-[25deg] -scale-x-100 drop-shadow-md">🌿</span>

      {/* Clouds */}
      <div className="absolute top-[60px] left-[15%] w-[110px] h-9 bg-white rounded-full opacity-85"
           style={{ boxShadow: '30px -10px 0 -2px #fff, 60px 4px 0 -4px #fff' }} />
      <div className="absolute top-[100px] right-[22%] w-[90px] h-7 bg-white rounded-full opacity-85"
           style={{ boxShadow: '25px -8px 0 -2px #fff, 50px 2px 0 -4px #fff' }} />
      <div className="absolute top-[40px] right-[12%] w-[70px] h-[22px] bg-white rounded-full opacity-85" />

      {/* Sparkles */}
      <span className="absolute text-base opacity-80 top-[12%] left-[28%]">✨</span>
      <span className="absolute text-base opacity-80 top-[70%] left-[30%]">✨</span>
      <span className="absolute text-base opacity-80 top-[18%] right-[26%]">✨</span>
      <span className="absolute text-base opacity-80 top-[62%] right-[30%]">✨</span>

      {/* Grass + flowers */}
      <div className="absolute left-0 right-0 bottom-0 h-[90px]"
           style={{ background: 'linear-gradient(180deg, transparent 0%, #a7d893 30%, #7ec46f 100%)' }}>
        <span className="absolute bottom-[18px] text-xl leading-none" style={{ left: '8%' }}>🌼</span>
        <span className="absolute bottom-[18px] text-xl leading-none" style={{ left: '22%' }}>🌷</span>
        <span className="absolute bottom-[18px] text-xl leading-none" style={{ left: '78%' }}>🌸</span>
        <span className="absolute bottom-[18px] text-xl leading-none" style={{ right: '8%' }}>🌻</span>
      </div>

      {/* Speech bubble */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[460px] max-w-[90%]">
        {/* Cat mascot */}
        <div className="absolute -top-[88px] left-1/2 -translate-x-1/2 w-[130px] h-[110px] flex items-end justify-center text-[96px] leading-none z-10 drop-shadow-md">
          {loggedIn ? '😸' : '🐱'}
        </div>

        <div
          className="relative bg-white rounded-[28px] px-10 pt-14 pb-9 text-center shadow-[0_12px_40px_rgba(31,41,55,0.12)]
                     after:content-[''] after:absolute after:bottom-[-14px] after:left-1/2 after:-translate-x-1/2 after:rotate-45
                     after:w-7 after:h-7 after:bg-white after:shadow-[4px_4px_8px_rgba(31,41,55,0.04)]"
        >
          {loggedIn ? (
            <>
              <h1 className="text-[26px] font-extrabold leading-snug -tracking-[0.5px] text-gray-800">
                환영합니다!<br />로그인 되었습니다 <span className="text-pink-500">♥</span>
              </h1>
              <p className="mt-3.5 text-sm text-gray-500 leading-relaxed">
                즐거운 코딩 라이프를 시작해보세요!<br />오늘도 좋은 하루 되세요 😊
              </p>
              <div className="mt-5 flex justify-center gap-2.5">
                <Button>문제 풀러가기</Button>
                <Button variant="outline" onClick={handleLogout}>로그아웃</Button>
              </div>
            </>
          ) : (
            <>
              <h1 className="text-[26px] font-extrabold leading-snug -tracking-[0.5px] text-gray-800">
                로그인하고<br />문제를 풀어보세요!
              </h1>
              <p className="mt-3.5 text-sm text-gray-500 leading-relaxed">
                AI 튜터와 함께 실력을 키우고,<br />랭킹에 도전해보세요.
              </p>
              <div className="mt-5 flex justify-center gap-2.5">
                <Button onClick={handleLogin}>Google로 로그인</Button>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
