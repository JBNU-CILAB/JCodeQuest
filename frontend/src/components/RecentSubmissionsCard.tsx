import { Card, CardHead } from './Card'
import { SUBMISSIONS } from '../data'

const VERDICT_COLOR: Record<string, string> = {
  AC: 'text-brand',
  WA: 'text-red-600',
  TLE: 'text-amber-600',
}

export function RecentSubmissionsCard() {
  return (
    <Card>
      <CardHead
        icon={<span className="font-mono">‹/›</span>}
        title="최근 제출"
        right={<a href="#" className="text-gray-500 text-xs font-medium hover:text-brand">전체 보기 ›</a>}
      />
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-gray-500 text-xs font-semibold">
            {['문제', '결과', '메모리', '시간', '언어', '제출 시간'].map((h) => (
              <th key={h} className="text-left px-2 py-3 border-b border-gray-100 font-semibold">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {SUBMISSIONS.map((s, i) => (
            <tr key={i} className="border-b border-gray-50 last:border-none">
              <td className="px-2 py-3">{s.problem}</td>
              <td className={`px-2 py-3 font-bold ${VERDICT_COLOR[s.verdict] ?? ''}`}>{s.verdictLabel}</td>
              <td className="px-2 py-3">{s.memory}</td>
              <td className="px-2 py-3">{s.time}</td>
              <td className="px-2 py-3">{s.language}</td>
              <td className="px-2 py-3">{s.submittedAt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
