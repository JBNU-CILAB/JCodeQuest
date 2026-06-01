import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardHead } from './Card'
import { Button } from './Button'
import { apiGet } from '../lib/api'
import type { BattleStatusResponse } from '../types'

function fmtCountdown(ms: number | null): string {
  if (ms == null) return '--:--'
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

export function BattleCard() {
  const navigate = useNavigate()
  const [snap, setSnap] = useState<BattleStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const offsetRef = useRef(0)

  useEffect(() => {
    let cancelled = false
    const fetchCurrent = () => {
      apiGet<BattleStatusResponse>('/battles/current')
        .then((d) => {
          if (cancelled) return
          offsetRef.current = Date.parse(d.server_time) - Date.now()
          setSnap(d)
          setError(null)
        })
        .catch((err) => {
          if (!cancelled) setError(err instanceof Error ? err.message : 'fetch failed')
        })
    }
    fetchCurrent()
    const poll = window.setInterval(fetchCurrent, 15_000)
    return () => {
      cancelled = true
      window.clearInterval(poll)
    }
  }, [])

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const serverNow = now + offsetRef.current
  const status = snap?.status ?? null
  const alwaysOpen = snap?.always_open ?? false
  const live = alwaysOpen || status === 'active' || status === 'lobby'
  const msUntil = (iso?: string | null) => (iso ? Date.parse(iso) - serverNow : null)

  let label = '다음 배틀까지'
  let value = fmtCountdown(msUntil(snap?.next_start_at))
  let cta = '배틀 보기'
  if (alwaysOpen) {
    label = '상시 개방 중'
    value = '∞'
    cta = '지금 입장하기'
  } else if (status === 'active') {
    label = '진행 중 · 남은 시간'
    value = fmtCountdown(msUntil(snap?.end_at))
    cta = '지금 입장하기'
  } else if (status === 'lobby') {
    label = '대기실 열림 · 시작까지'
    value = fmtCountdown(msUntil(snap?.start_at))
    cta = '대기실 입장'
  }

  return (
    <Card className="bg-gradient-to-br from-brand to-brand-dark border-transparent text-white">
      <CardHead
        title="오늘의 Code Battle"
        right={
          live ? (
            <span className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider">
              <span className="w-2 h-2 rounded-full bg-green-300 animate-pulse" />
              LIVE
            </span>
          ) : undefined
        }
      />
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-widest text-white/70">{label}</div>
          <div className="text-3xl font-black tabular-nums mt-0.5">{value}</div>
          <p className="text-xs text-white/80 mt-2">
            {error
              ? '상태를 불러오지 못했어요'
              : `${snap?.participant_count ?? 0}명 참가 · 같은 문제로 20분 대전`}
          </p>
        </div>
        <Button
          variant="outline"
          className="!bg-white !text-brand !border-transparent shrink-0"
          onClick={() => navigate('/battle')}
        >
          {cta}
        </Button>
      </div>
    </Card>
  )
}
