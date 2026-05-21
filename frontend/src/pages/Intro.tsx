import { useNavigate } from 'react-router-dom'
import { MatrixBackdrop } from '../components/MatrixBackdrop'

const INTRO_SEEN_KEY = 'intro_seen'

export function Intro() {
  const navigate = useNavigate()

  const handleStart = () => {
    try {
      localStorage.setItem(INTRO_SEEN_KEY, '1')
    } catch {
      // localStorage 사용 불가 환경(시크릿 모드 등)에서는 그냥 이동만 한다.
    }
    navigate('/', { replace: true })
  }

  return (
    <div className="relative flex-1 overflow-hidden bg-white">
      <MatrixBackdrop className="absolute inset-0" />
      <div className="relative z-10 flex min-h-[70vh] flex-col items-center justify-center px-6 text-center">
        <h1 className="text-5xl md:text-7xl font-bold text-[#1b64da] tracking-tight">
          JCodeQuest
        </h1>
        <p className="mt-4 text-lg md:text-xl text-gray-700 max-w-xl">
          알고리즘 문제 풀이를 게임처럼. AI가 출제하고, AI 3인 합의로 채점합니다.
        </p>
        <button
          type="button"
          onClick={handleStart}
          className="mt-10 px-8 py-3 rounded-full bg-[#1b64da] text-white text-base font-semibold shadow-lg hover:bg-[#1857c2] transition"
        >
          시작하기
        </button>
      </div>
    </div>
  )
}
