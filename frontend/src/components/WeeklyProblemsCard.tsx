import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardHead } from './Card'
import { Button } from './Button'
import { apiGet, ApiError } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import { formatIsoWeekKo } from '../lib/isoWeek'
import type {
  ProblemSummary,
  SubmissionListResponse,
  WeeklyProblemBucketsResponse,
} from '../types'

type WeekRow = {
  week: string
  label: string
  total: number
  solved: number
}

const SHOW_WEEKS = 4 // 카드에 노출할 최대 주차 수

export function WeeklyProblemsCard() {
  const { session } = useAuth()
  const [rows, setRows] = useState<WeekRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    const problemsP = apiGet<ProblemSummary[]>('/problems')
    const bucketsP = apiGet<WeeklyProblemBucketsResponse>('/problems/weeks')
    const mineP: Promise<SubmissionListResponse | null> = session
      ? apiGet<SubmissionListResponse>('/me/submissions?limit=100')
      : Promise.resolve(null)

    Promise.all([problemsP, bucketsP, mineP])
      .then(([problems, buckets, mine]) => {
        if (cancelled) return

        const acProblemIds = new Set<number>(
          (mine?.items ?? [])
            .filter((s) => s.final_verdict === 'AC')
            .map((s) => s.problem_id),
        )

        // iso_week → solved 개수 (해당 주차의 problem 중 AC된 개수)
        const solvedByWeek = new Map<string, number>()
        for (const p of problems) {
          if (!acProblemIds.has(p.id)) continue
          solvedByWeek.set(p.iso_week, (solvedByWeek.get(p.iso_week) ?? 0) + 1)
        }

        const merged: WeekRow[] = buckets.buckets
          .slice(0, SHOW_WEEKS)
          .map((b) => ({
            week: b.week,
            label: formatIsoWeekKo(b.week),
            total: b.count,
            solved: solvedByWeek.get(b.week) ?? 0,
          }))

        setRows(merged)
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [session?.access_token])

  return (
    <Card>
      <CardHead
        title="주차별 문제"
        right={
          <Link
            to="/problems"
            className="text-gray-500 text-xs font-medium hover:text-brand"
          >
            전체 보기 ›
          </Link>
        }
      />

      {loading && (
        <p className="text-xs text-gray-500 py-2">불러오는 중…</p>
      )}
      {error && (
        <p className="text-xs text-red-600 py-2">주차 목록 조회 실패: {error}</p>
      )}
      {!loading && !error && rows && rows.length === 0 && (
        <p className="text-xs text-gray-500 py-2">아직 등록된 주차가 없어요.</p>
      )}

      {!loading && !error && rows && rows.length > 0 && (
        <div className="flex flex-col gap-[18px]">
          {rows.map((w) => {
            const pct = w.total === 0 ? 0 : Math.round((w.solved / w.total) * 100)
            const done = w.total > 0 && w.solved >= w.total
            return (
              <div
                key={w.week}
                className="grid items-center gap-4"
                style={{ gridTemplateColumns: '100px 1fr auto' }}
              >
                <div className="text-[13px] font-bold text-gray-800">
                  {w.label}
                  <span className="block text-[11.5px] text-gray-500 font-medium mt-0.5">
                    {w.solved} / {w.total} 문제 해결
                  </span>
                </div>
                <div className="relative h-2.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="absolute inset-y-0 left-0 rounded-full"
                    style={{
                      width: `${pct}%`,
                      background: done
                        ? 'linear-gradient(90deg, #4ea36b, #3f8856)'
                        : 'linear-gradient(90deg, #6ec48e, #4ea36b)',
                    }}
                  />
                </div>
                {done ? (
                  <Button variant="disabled" size="sm" disabled>
                    완료
                  </Button>
                ) : (
                  <Link to="/problems">
                    <Button variant="outline" size="sm">
                      문제 풀기
                    </Button>
                  </Link>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
