// 화려한 티어 배지. 그라데이션 + 티어별 아이콘 + 링/글로우.
// 랭킹·프로필 같이 "보이는 곳"용 — 헤더 드롭다운 같은 텍스트 위주 자리는 lib/tiers의 단순 배지 그대로.
//
// 디자인 메모:
// - 그라데이션은 다이아곤이 더 입체적으로 보여서 `bg-gradient-to-br` 통일.
// - master 만 외곽에 색 글로우 + 옅은 펄스 — '최상위' 시각적 위계.
// - 알 수 없는 tier 값(레거시 'bronze' 등)은 beginner 스타일로 폴백.

import type { Tier } from '../types'
import { tierLabel } from '../lib/tiers'

const TIER_GRADIENT: Record<Tier, string> = {
  beginner: 'from-slate-400 via-slate-500 to-slate-700',
  amateur: 'from-emerald-400 via-teal-500 to-cyan-600',
  professional: 'from-indigo-500 via-violet-500 to-fuchsia-500',
  master: 'from-amber-400 via-rose-500 to-purple-600',
}

const TIER_RING: Record<Tier, string> = {
  beginner: 'ring-white/20',
  amateur: 'ring-emerald-200/60',
  professional: 'ring-violet-200/70',
  master: 'ring-amber-200/80',
}

const TIER_GLOW: Record<Tier, string> = {
  beginner: 'shadow-slate-500/30',
  amateur: 'shadow-emerald-500/40',
  professional: 'shadow-violet-500/50',
  // 마스터만 컬러 글로우 강도 ↑ — 위계 확보. shadow-2xl로 끌어올림.
  master: 'shadow-rose-500/60',
}

const TIER_ICON: Record<Tier, string> = {
  beginner: '🌱',
  amateur: '⭐',
  professional: '💎',
  master: '👑',
}

const SIZE: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'text-[10px] px-2 py-0.5 gap-1',
  md: 'text-[11px] px-2.5 py-1 gap-1.5',
  lg: 'text-[13px] px-3 py-1.5 gap-2',
}

function resolve(tier: string | undefined | null): Tier {
  if (tier && tier in TIER_GRADIENT) return tier as Tier
  return 'beginner'
}

interface TierBadgeProps {
  tier: string | undefined | null
  size?: 'sm' | 'md' | 'lg'
  // 마스터에서 한정해서 글로우를 더 강하게 + 펄스를 살짝. 리더보드 1위 등 강조용.
  emphasize?: boolean
  className?: string
}

export function TierBadge({ tier, size = 'sm', emphasize = false, className = '' }: TierBadgeProps) {
  const t = resolve(tier)
  const isMaster = t === 'master'
  const showPulse = isMaster && emphasize

  return (
    <span
      className={[
        'relative inline-flex items-center font-bold text-white whitespace-nowrap',
        'rounded-full bg-gradient-to-br',
        TIER_GRADIENT[t],
        SIZE[size],
        // 안쪽 라이트 라인 — 금속·보석 느낌. ring-inset이 핵심.
        'ring-1 ring-inset',
        TIER_RING[t],
        // 외곽 글로우. master는 한 단계 더 진하게.
        'shadow-md',
        TIER_GLOW[t],
        isMaster ? 'shadow-lg' : '',
        // 텍스트 살짝 떠 있는 느낌으로 가독성 보정.
        'drop-shadow-[0_1px_0_rgba(0,0,0,0.25)]',
        className,
      ].join(' ')}
    >
      {showPulse && (
        // 외곽에 깜빡이는 후광. pointer-events 차단 + 살짝만 보이도록 opacity-40.
        <span
          aria-hidden
          className="absolute inset-0 rounded-full bg-gradient-to-br from-amber-300 to-rose-500 opacity-40 blur-md animate-pulse pointer-events-none"
        />
      )}
      <span className="relative leading-none">{TIER_ICON[t]}</span>
      <span className="relative tracking-wide">{tierLabel(t)}</span>
    </span>
  )
}
