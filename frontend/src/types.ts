export type AuthState = 'logged-out' | 'logged-in'

export interface RankUser {
  rank: number
  name: string
  solved: number
  streak: number
  score: number
}

export interface WeeklyProblem {
  label: string
  solved: number
  total: number
}

export interface Submission {
  problem: string
  verdict: 'AC' | 'WA' | 'TLE'
  verdictLabel: string
  memory: string
  time: string
  language: string
  submittedAt: string
}
