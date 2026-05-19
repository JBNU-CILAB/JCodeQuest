import { useEffect, useRef } from 'react'

// Intro.tsx 의 배경 입자 애니메이션(아래로 떨어지는 코드 비 + 위로 떠오르는 초록 스트림)을
// 분리해 재사용한 컴포넌트. Intro 의 타이틀 형성 입자는 인트로 전용이라 여기엔 포함하지 않는다.
// 사용처는 부모가 `position: relative`(+ 필요 시 `overflow-hidden`) 여야 한다.

type Drop = {
  x: number
  y: number
  v: number
  char: string
  morphTimer: number
  morphInterval: number
  alpha: number
  size: number
}

const CHAR_POOL =
  '01<>[]{}/\\$#@*+-=~|;:.,?!ABCDEFGHIJKLMNOPQRSTUVWXYZ※'.split('')

// Intro 와 동일한 색상 체계: 낙하 입자는 어두운 블루그레이, 상승 입자는 toss-blue.
const RAIN_COLOR = '#2b3a4a'
const RISE_COLOR = '#1b64da'

function pickChar(): string {
  return CHAR_POOL[Math.floor(Math.random() * CHAR_POOL.length)]
}

interface Props {
  className?: string
  rainCount?: number
  riseCount?: number
}

export function MatrixBackdrop({
  className = '',
  rainCount = 70,
  riseCount = 40,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let raf = 0
    let W = 0
    let H = 0

    function resize() {
      if (!canvas || !ctx) return
      W = canvas.clientWidth
      H = canvas.clientHeight
      canvas.width = W * dpr
      canvas.height = H * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)

    const rainDrops: Drop[] = Array.from({ length: rainCount }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      v: 40 + Math.random() * 120,
      char: pickChar(),
      morphTimer: 0,
      morphInterval: 80 + Math.random() * 240,
      alpha: 0.05 + Math.random() * 0.12,
      size: 11 + Math.random() * 4,
    }))

    const riseDrops: Drop[] = Array.from({ length: riseCount }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      v: 30 + Math.random() * 70,
      char: pickChar(),
      morphTimer: 0,
      morphInterval: 100 + Math.random() * 260,
      alpha: 0.05 + Math.random() * 0.12,
      size: 11 + Math.random() * 4,
    }))

    let lastDraw = performance.now()

    function frame(now: number) {
      if (!ctx) return
      const dt = Math.min(64, now - lastDraw)
      lastDraw = now

      ctx.clearRect(0, 0, W, H)
      ctx.textBaseline = 'top'

      // Falling rain
      ctx.fillStyle = RAIN_COLOR
      for (const d of rainDrops) {
        d.y += d.v * (dt / 1000)
        if (d.y > H + 20) {
          d.y = -20
          d.x = Math.random() * W
        }
        d.morphTimer += dt
        if (d.morphTimer > d.morphInterval) {
          d.char = pickChar()
          d.morphTimer = 0
        }
        ctx.globalAlpha = d.alpha
        ctx.font = `${d.size}px NeoDunggeunmo, monospace`
        ctx.fillText(d.char, d.x, d.y)
      }

      // Rising stream
      ctx.fillStyle = RISE_COLOR
      for (const d of riseDrops) {
        d.y -= d.v * (dt / 1000)
        if (d.y < -20) {
          d.y = H + 20
          d.x = Math.random() * W
        }
        d.morphTimer += dt
        if (d.morphTimer > d.morphInterval) {
          d.char = pickChar()
          d.morphTimer = 0
        }
        ctx.globalAlpha = d.alpha
        ctx.font = `${d.size}px NeoDunggeunmo, monospace`
        ctx.fillText(d.char, d.x, d.y)
      }
      ctx.globalAlpha = 1

      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [rainCount, riseCount])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className={`absolute inset-0 w-full h-full block pointer-events-none ${className}`}
    />
  )
}
