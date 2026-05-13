import type { Session } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'

interface HeaderProps {
  session: Session | null
}

export function Header({ session }: HeaderProps) {
  const loggedIn = session !== null

  return (
    <header className="h-[72px] px-10 flex items-center gap-6 text-white bg-gradient-to-b from-header-1 to-header-2">
      <div className="w-[90px] h-12 bg-white rounded flex items-center justify-center text-3xl italic font-semibold text-gray-800 select-none font-display tracking-tighter">
        cd
      </div>

      {loggedIn && (
        <>
          <nav className="ml-auto flex gap-10 items-center">
            {['공지', '문제페이지', '랭킹'].map((label) => (
              <a
                key={label}
                href="#"
                className="text-gray-200 text-[15px] font-medium pb-1.5 border-b-2 border-transparent hover:text-white hover:border-white/40 transition"
              >
                {label}
              </a>
            ))}
          </nav>
          <div className="ml-7 flex flex-col items-center gap-0.5">
            <button className="w-9 h-9 rounded-full bg-gradient-to-br from-slate-300 to-slate-400 text-white text-lg border-2 border-white/40 cursor-pointer">
              🙂
            </button>
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
        </>
      )}
    </header>
  )
}
