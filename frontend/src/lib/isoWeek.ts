/**
 * "YYYY-Www" ISO week 라벨을 "n월 n주차" 한국어 표기로 변환.
 * 기준일은 ISO week의 목요일(ISO 8601이 정의한 대표일) — 월/주차 계산이 안정적이다.
 *
 * 예) 2026-W21 → 5월 3주차 (Thursday May 21, 2026)
 *
 * 매칭 실패 시 원문을 그대로 돌려줘서 호출자가 안전하게 사용할 수 있다.
 */
export function formatIsoWeekKo(isoWeek: string | null | undefined): string {
  if (!isoWeek) return ''
  const m = /^(\d{4})-W(\d{2})$/.exec(isoWeek)
  if (!m) return isoWeek
  const year = Number(m[1])
  const week = Number(m[2])

  // ISO 8601: Week 1은 1월 4일을 포함한다. 1월 4일이 속한 주의 월요일이 W01의 시작.
  const jan4 = new Date(Date.UTC(year, 0, 4))
  const jan4Dow = jan4.getUTCDay() || 7 // Sun(0) → 7로 보정
  const week1MondayMs = jan4.getTime() - (jan4Dow - 1) * 86_400_000
  const targetMondayMs = week1MondayMs + (week - 1) * 7 * 86_400_000
  const thursdayMs = targetMondayMs + 3 * 86_400_000
  const thu = new Date(thursdayMs)

  const month = thu.getUTCMonth() + 1
  const weekOfMonth = Math.floor((thu.getUTCDate() - 1) / 7) + 1
  return `${month}월 ${weekOfMonth}주차`
}
