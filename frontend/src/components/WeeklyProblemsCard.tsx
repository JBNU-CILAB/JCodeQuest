import { Card, CardHead } from './Card'
import { Button } from './Button'
import { WEEKLY_PROBLEMS } from '../data'

export function WeeklyProblemsCard() {
  return (
    <Card>
      <CardHead
        icon="📅"
        title="주차별 문제"
        right={<a href="#" className="text-gray-500 text-xs font-medium hover:text-brand">전체 보기 ›</a>}
      />
      <div className="flex flex-col gap-[18px]">
        {WEEKLY_PROBLEMS.map((w) => {
          const pct = Math.round((w.solved / w.total) * 100)
          const done = w.solved >= w.total
          return (
            <div
              key={w.label}
              className="grid items-center gap-4"
              style={{ gridTemplateColumns: '90px 1fr auto' }}
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
                <Button variant="disabled" size="sm" disabled>완료</Button>
              ) : (
                <Button variant="outline" size="sm">문제 풀기</Button>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}
