import { useState } from 'react'
import { Card, CardHead } from './Card'
import { RANKINGS } from '../data'

type Scope = 'all' | 'friends'

const MEDAL_BG: Record<number, string> = {
  1: 'bg-yellow-100',
  2: 'bg-gray-200',
  3: 'bg-orange-200',
}
const MEDAL_EMOJI: Record<number, string> = {
  1: '🥇',
  2: '🥈',
  3: '🥉',
}

export function RankingCard() {
  const [scope, setScope] = useState<Scope>('all')

  const toggle = (
    <div className="inline-flex bg-gray-100 rounded-full p-0.5">
      {(['all', 'friends'] as Scope[]).map((s) => (
        <button
          key={s}
          onClick={() => setScope(s)}
          className={`px-3.5 py-1 rounded-full text-xs font-semibold transition ${
            scope === s ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'
          }`}
        >
          {s === 'all' ? '전체' : '친구'}
        </button>
      ))}
    </div>
  )

  return (
    <Card>
      <CardHead icon="🏆" title="이번주 랭킹" right={toggle} />
      <div>
        {RANKINGS.map((u) => (
          <div
            key={u.rank}
            className="flex items-center gap-3.5 py-2.5 border-b border-gray-100 last:border-none"
          >
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-base shrink-0 ${
                MEDAL_BG[u.rank] ?? 'bg-gray-100 text-gray-500 text-sm font-bold'
              }`}
            >
              {MEDAL_EMOJI[u.rank] ?? u.rank}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-gray-800">{u.name}</div>
              <div className="text-xs text-gray-500 mt-0.5">
                {u.solved} Solved · {u.streak} Day streak
              </div>
            </div>
            <div className="inline-flex items-center gap-1 bg-violet-50 text-violet-600 font-bold text-[13px] px-3 py-1 rounded-full">
              💎 {u.score}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
