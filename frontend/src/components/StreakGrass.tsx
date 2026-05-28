// 마이페이지와 타인 공개 프로필이 공유하는 활동 요약 위젯.
// (원래 MyPage.tsx에 있던 것을 재사용 위해 분리)

export const GRASS_COLOR = (count: number): string => {
  if (count <= 0) return 'bg-gray-200'
  if (count === 1) return 'bg-blue-200'
  if (count === 2) return 'bg-blue-400'
  if (count === 3) return 'bg-blue-600'
  return 'bg-blue-800'
}

export function Stat({
  label,
  value,
  valueClass = 'text-gray-900',
}: {
  label: string
  value: number
  valueClass?: string
}) {
  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3">
      <div className="text-[11px] font-semibold text-gray-500">{label}</div>
      <div className={`text-2xl font-bold tabular-nums mt-1 ${valueClass}`}>{value}</div>
    </div>
  )
}

const CELL_PX = 12
const CELL_GAP_PX = 3

type Cell = { date: string; count: number } | null

export function StreakGrass({ days }: { days: { date: string; count: number }[] }) {
  if (days.length === 0) return null

  const firstDate = new Date(`${days[0].date}T00:00:00`)
  const startDow = firstDate.getDay() // 0=Sun ... 6=Sat

  const cells: Cell[] = []
  for (let i = 0; i < startDow; i++) cells.push(null)
  for (const d of days) cells.push(d)
  while (cells.length % 7 !== 0) cells.push(null)
  const numWeeks = cells.length / 7

  // 각 주(컬럼)의 대표 월을 잡아 연속 컬럼들로 span 생성.
  const monthSpans: { label: string; startCol: number; endCol: number }[] = []
  let currentMonth = -1
  let currentSpan: { label: string; startCol: number; endCol: number } | null = null
  for (let w = 0; w < numWeeks; w++) {
    let weekMonth: number | null = null
    for (let r = 0; r < 7; r++) {
      const c = cells[w * 7 + r]
      if (c) {
        weekMonth = new Date(`${c.date}T00:00:00`).getMonth()
        break
      }
    }
    if (weekMonth === null) continue
    if (weekMonth !== currentMonth) {
      if (currentSpan) monthSpans.push(currentSpan)
      currentSpan = { label: `${weekMonth + 1}월`, startCol: w, endCol: w }
      currentMonth = weekMonth
    } else if (currentSpan) {
      currentSpan.endCol = w
    }
  }
  if (currentSpan) monthSpans.push(currentSpan)

  const gridWidth = numWeeks * CELL_PX + (numWeeks - 1) * CELL_GAP_PX

  return (
    <div className="mt-3 overflow-x-auto pb-1">
      <div style={{ width: `${gridWidth}px` }}>
        {/* 월 라벨 */}
        <div
          className="text-[10px] text-gray-500 leading-none mb-1 h-3"
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${numWeeks}, ${CELL_PX}px)`,
            columnGap: `${CELL_GAP_PX}px`,
          }}
        >
          {monthSpans.map((s, i) => (
            <div
              key={i}
              className="whitespace-nowrap overflow-visible"
              style={{ gridColumn: `${s.startCol + 1} / ${s.endCol + 2}` }}
            >
              {s.label}
            </div>
          ))}
        </div>

        {/* 잔디 격자 */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${numWeeks}, ${CELL_PX}px)`,
            gridTemplateRows: `repeat(7, ${CELL_PX}px)`,
            gridAutoFlow: 'column',
            gap: `${CELL_GAP_PX}px`,
          }}
        >
          {cells.map((cell, i) =>
            cell ? (
              <div key={i} className="relative group">
                <div
                  className={`h-3 w-3 rounded-[2px] ${GRASS_COLOR(cell.count)}`}
                />
                <div
                  role="tooltip"
                  className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:block whitespace-nowrap rounded-md bg-gray-900 px-2 py-1 text-[10px] font-medium text-white shadow-md z-20"
                >
                  {cell.date} · {cell.count}문제
                  <span className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
                </div>
              </div>
            ) : (
              <div key={i} className="h-3 w-3" />
            ),
          )}
        </div>

        {/* 범례 */}
        <div className="mt-2 flex items-center justify-end gap-1 text-[10px] text-gray-500">
          <span>적음</span>
          {[0, 1, 2, 3, 4].map((n) => (
            <span key={n} className={`h-2.5 w-2.5 rounded-sm ${GRASS_COLOR(n)}`} />
          ))}
          <span>많음</span>
        </div>
      </div>
    </div>
  )
}
