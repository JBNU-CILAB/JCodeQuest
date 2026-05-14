import { useEffect, useState } from 'react'
import { CatGroup } from './CatLogo'

const STORAGE_KEY = 'jcq-splash-shown'
const HOLD_MS = 1800
const FADE_MS = 500

const GRASS_TUFTS = [22, 62, 102, 142, 182, 222, 262, 300]

export function Splash() {
  const [phase, setPhase] = useState<'hidden' | 'visible' | 'fading'>(() => {
    if (typeof window === 'undefined') return 'hidden'
    return sessionStorage.getItem(STORAGE_KEY) ? 'hidden' : 'visible'
  })

  useEffect(() => {
    if (phase !== 'visible') return
    sessionStorage.setItem(STORAGE_KEY, '1')
    const fadeTimer = window.setTimeout(() => setPhase('fading'), HOLD_MS)
    const doneTimer = window.setTimeout(() => setPhase('hidden'), HOLD_MS + FADE_MS)
    return () => {
      window.clearTimeout(fadeTimer)
      window.clearTimeout(doneTimer)
    }
  }, [phase])

  if (phase === 'hidden') return null

  return (
    <div
      aria-hidden
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-white"
      style={{
        opacity: phase === 'fading' ? 0 : 1,
        transition: `opacity ${FADE_MS}ms ease-out`,
        pointerEvents: phase === 'fading' ? 'none' : 'auto',
      }}
    >
      <svg
        viewBox="0 0 320 320"
        className="w-[min(88vw,640px)] h-auto text-slate-800"
        role="img"
        aria-label="JCodeQuest"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Cat — scaled up so it dominates the composition */}
        <g transform="translate(4, 5) scale(1.42)">
          <CatGroup />
        </g>

        {/* Grass — green dotted tufts */}
        <g
          stroke="#6fa55a"
          strokeWidth={2}
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="0 5"
        >
          {GRASS_TUFTS.map((cx) => (
            <g key={cx}>
              {/* center blade */}
              <path d={`M ${cx},220 L ${cx},190`} />
              {/* upper side blades */}
              <path d={`M ${cx},220 L ${cx - 8},198`} />
              <path d={`M ${cx},220 L ${cx + 8},198`} />
              {/* lower side blades */}
              <path d={`M ${cx},220 L ${cx - 14},206`} />
              <path d={`M ${cx},220 L ${cx + 14},206`} />
            </g>
          ))}
          {/* Ground line of dots */}
          <path d="M 0,226 L 320,226" stroke="#7a9c63" />
        </g>

        {/* JCodeQuest — letter outlines rendered as dots */}
        <text
          x="160"
          y="290"
          textAnchor="middle"
          fontSize="50"
          fontFamily="ui-sans-serif, -apple-system, 'Helvetica Neue', sans-serif"
          fontWeight={300}
          letterSpacing="1.5"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="0 4.5"
        >
          JCodeQuest
        </text>
      </svg>
    </div>
  )
}
