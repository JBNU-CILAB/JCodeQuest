// 4단계 티어 표시 헬퍼.
// 백엔드 `src/tier.py:TIER_ORDER` 와 동일 순서. 임계값(%) 산식 자체는 서버 단일 소스 —
// 프론트는 라벨/색만 들고 있고, 진행도/다음 티어는 서버가 내려준 `tier_progress`를 그대로 쓴다.

import type { Tier } from '../types'

export const TIER_ORDER: Tier[] = ['beginner', 'amateur', 'professional', 'master']

// 화면 표시명. 영문 키 그대로 캐피털라이즈해서 노출.
export const TIER_LABELS: Record<Tier, string> = {
  beginner: 'Beginner',
  amateur: 'Amateur',
  professional: 'Professional',
  master: 'Master',
}

// 배지 색상. Tailwind 클래스만 — 컴포넌트마다 같은 모양을 유지하기 위한 단일 소스.
// 키가 모르는 값이면 호출 측에서 TIER_STYLES.beginner 로 폴백.
export const TIER_STYLES: Record<Tier, string> = {
  beginner: 'bg-slate-500/80 text-slate-50',
  amateur: 'bg-emerald-600/80 text-emerald-50',
  professional: 'bg-indigo-600/80 text-indigo-50',
  master: 'bg-rose-600/90 text-rose-50',
}

export function tierStyle(tier: string | undefined | null): string {
  if (tier && tier in TIER_STYLES) {
    return TIER_STYLES[tier as Tier]
  }
  return TIER_STYLES.beginner
}

export function tierLabel(tier: string | undefined | null): string {
  if (tier && tier in TIER_LABELS) {
    return TIER_LABELS[tier as Tier]
  }
  // 알 수 없는 값(레거시 'bronze' 등)은 그대로 노출 — 백필 전엔 일시적으로 섞일 수 있음.
  return tier ?? 'Beginner'
}
