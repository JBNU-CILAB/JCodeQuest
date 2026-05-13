import { useEffect, useState } from 'react'
import { apiGet, ApiError } from '../lib/api'
import { ProblemCard } from '../components/ProblemCard'
import type { ProblemLevel, ProblemSummary } from '../types'

const LEVEL_FILTERS: Array<{ value: ProblemLevel | 'all'; label: string }> = [
  { value: 'all', label: '전체' },
  { value: 'bronze', label: 'Bronze' },
  { value: 'silver', label: 'Silver' },
  { value: 'gold', label: 'Gold' },
]

export function Problems() {
  const [problems, setProblems] = useState<ProblemSummary[] | null>(null)
  const [allCategories, setAllCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [category, setCategory] = useState<string>('all')
  const [level, setLevel] = useState<ProblemLevel | 'all'>('all')

  useEffect(() => {
    setLoading(true)
    setError(null)

    const params = new URLSearchParams()
    if (category !== 'all') params.set('category', category)
    if (level !== 'all') params.set('level', level)
    const qs = params.toString()
    const path = qs ? `/problems?${qs}` : '/problems'

    apiGet<ProblemSummary[]>(path)
      .then((data) => {
        setProblems(data)
        // 첫 로드(필터 없음)에서만 distinct 카테고리 갱신 — 이후엔 select 옵션 유지
        if (category === 'all' && level === 'all') {
          const cats = Array.from(new Set(data.map((p) => p.category))).sort()
          setAllCategories(cats)
        }
      })
      .catch((err) => {
        const msg = err instanceof ApiError
          ? `${err.status} ${err.message}`
          : err instanceof Error ? err.message : 'unknown error'
        setError(msg)
        setProblems(null)
      })
      .finally(() => setLoading(false))
  }, [category, level])

  return (
    <main className="max-w-[1180px] mx-auto w-full px-8 pt-8 pb-20">
      <div className="flex items-end justify-between mb-6">
        <h1 className="text-[26px] font-extrabold text-gray-800 tracking-tight">문제 목록</h1>
        {problems && (
          <span className="text-sm text-gray-500 tabular-nums">
            {problems.length}개
          </span>
        )}
      </div>

      {/* 필터 */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <span>카테고리</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="border border-gray-200 rounded-full px-3 py-1.5 text-sm bg-white focus:outline-none focus:border-brand"
          >
            <option value="all">전체</option>
            {allCategories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>

        <div className="ml-auto flex items-center gap-1 bg-white border border-gray-200 rounded-full p-1">
          {LEVEL_FILTERS.map((f) => {
            const active = level === f.value
            return (
              <button
                key={f.value}
                onClick={() => setLevel(f.value)}
                className={`px-3 py-1 text-xs font-semibold rounded-full transition ${
                  active
                    ? 'bg-brand text-white'
                    : 'text-gray-500 hover:text-gray-800'
                }`}
              >
                {f.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* 결과 */}
      {loading && (
        <div className="text-center py-16 text-gray-400 text-sm">불러오는 중...</div>
      )}
      {error && (
        <div className="text-center py-16 text-red-500 text-sm">
          문제 목록을 불러오지 못했습니다 — {error}
        </div>
      )}
      {!loading && !error && problems && problems.length === 0 && (
        <div className="text-center py-16 text-gray-400 text-sm">
          조건에 맞는 문제가 없습니다.
        </div>
      )}
      {!loading && !error && problems && problems.length > 0 && (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {problems.map((p) => (
            <ProblemCard key={p.id} problem={p} />
          ))}
        </div>
      )}
    </main>
  )
}
