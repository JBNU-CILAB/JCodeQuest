import { RankingCard } from './RankingCard'
import { WeeklyProblemsCard } from './WeeklyProblemsCard'
import { RecentSubmissionsCard } from './RecentSubmissionsCard'

export function Dashboard() {
  return (
    <main className="max-w-[1180px] mx-auto w-full px-8 pt-8 pb-20 flex flex-col gap-6">
      <div className="grid gap-6 grid-cols-1 md:grid-cols-2">
        <RankingCard />
        <WeeklyProblemsCard />
      </div>
      <RecentSubmissionsCard />
    </main>
  )
}
