// ───────────────── 백엔드 API 응답 타입 ─────────────────
// backend/src/schemas.py 의 Pydantic 모델과 1:1 대응

export interface UserMe {
  id: number
  display_name: string
  email: string | null
  provider: string
  exp: number
  tier: string
  has_api_key?: boolean
  nickname?: string | null
  grade?: number | null
  department?: string | null
  is_anonymous?: boolean
  avatar_url?: string | null
}

export interface SubmissionListItem {
  id: number
  problem_id: number
  status: SubmissionStatus
  final_verdict: Verdict | null
  mode: 'unanimous' | 'majority' | null
  points_awarded: number | null
  max_elapsed_ms: number | null
  peak_memory_kb: number | null
  created_at: string
}

export interface SubmissionListResponse {
  items: SubmissionListItem[]
  total: number
  limit: number
  offset: number
}

export interface RecentSubmissionItem {
  id: number
  user_id: number
  user_display_name: string | null
  problem_id: number
  problem_title: string | null
  status: SubmissionStatus
  final_verdict: Verdict | null
  mode: 'unanimous' | 'majority' | null
  points_awarded: number | null
  max_elapsed_ms: number | null
  peak_memory_kb: number | null
  created_at: string
}

export interface RecentSubmissionsResponse {
  items: RecentSubmissionItem[]
  limit: number
}

export interface DailySolve {
  date: string
  count: number
}

export interface StreakResponse {
  current_streak: number
  longest_streak: number
  last_solved_date: string | null
  daily_solves: DailySolve[]
}

export type ProblemLevel = 'bronze' | 'silver' | 'gold'

export interface ProblemSummary {
  id: number
  title: string
  category: string
  level: ProblemLevel
  points: number
  one_line_summary: string
  iso_week: string
}

export interface WeeklyProblemBucket {
  week: string
  count: number
}

export interface WeeklyProblemBucketsResponse {
  buckets: WeeklyProblemBucket[]
}

export interface PublicTestCase {
  ordinal: number
  stdin: string
  expected_stdout: string
}

export interface ProblemDetail extends ProblemSummary {
  statement: string
  time_limit_ms: number
  memory_limit_mb: number
  sample_test_cases: PublicTestCase[]
}

export type SubmissionStatus = 'queued' | 'running' | 'done' | 'failed'
export type Verdict = 'AC' | 'SUS'

export interface TestResult {
  ordinal: number
  passed: boolean
  status: string
  actual_stdout: string
  error: string | null
  elapsed_ms: number
  peak_memory_kb: number
}

export interface JudgeVote {
  judge_id: string
  verdict: Verdict
  intent_match: boolean
  rationale: string
  confidence: number
}

export interface EnsembleResult {
  final_verdict: Verdict
  mode: 'unanimous' | 'majority'
  votes: JudgeVote[]
}

export interface GradeAcceptedResponse {
  submission_id: number
  status: SubmissionStatus
}

export interface SubmissionStatusResponse {
  submission_id: number
  status: SubmissionStatus
  final_verdict: Verdict | null
  test_results: TestResult[] | null
  ensemble: EnsembleResult | null
  points_awarded: number | null
}

export interface TutorResponse {
  submission_id: number
  message: string
}

export interface TutorHistoryItem {
  id: number
  message: string
  created_at: string
}

export interface TutorHistoryResponse {
  submission_id: number
  messages: TutorHistoryItem[]
  usage_count: number
  remaining_uses: number
}

export interface Notice {
  id: number
  title: string
  body: string
  pinned: boolean
  created_at: string
  updated_at: string
}

export type LeaderboardPeriod = 'all' | 'week'

export interface LeaderboardEntry {
  rank: number
  user_id: number
  display_name: string
  tier: string
  points: number
}

export interface LeaderboardResponse {
  period: LeaderboardPeriod
  week: string | null
  entries: LeaderboardEntry[]
}

export interface PublicProfileStats {
  solved: number
  total_submissions: number
  current_streak: number
  longest_streak: number
  daily_solves: DailySolve[]
}

// GET /users/:id — 타인 공개 프로필. is_anonymous=true면 서버가 닉네임/티어/EXP만
// 채우고 나머지는 null로 내려준다.
export interface PublicProfile {
  user_id: number
  display_name: string
  tier: string
  exp: number
  is_anonymous: boolean
  avatar_url?: string | null
  grade?: number | null
  department?: string | null
  rank?: number | null
  stats?: PublicProfileStats | null
}

// ───────────────── Mock 카드 타입 (Phase 6에서 일부 교체) ─────────────────

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
