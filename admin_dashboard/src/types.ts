export interface ConnSettings {
  baseUrl: string;
  baseToken: string;
  judgeUrl: string;
  judgeToken: string;
}

export type ConnStatus = "idle" | "ok" | "error" | "loading";

export type Route = "problems" | "submissions" | "notices" | "reports" | "stats" | "users";

export interface ProblemRow {
  id: number;
  title: string;
  category: string;
  level: string;
  points: number;
  time_limit_ms: number;
  parent_id: number | null;
  created_at: string;
}

export interface TestCase {
  stdin: string;
  expected_stdout: string;
  is_sample?: boolean;
}

export interface SubmissionRow {
  id: number;
  user_id: number;
  user_display_name?: string;
  problem_id: number;
  problem_title?: string;
  final_verdict?: string;
  status: string;
  mode?: string;
  max_elapsed_ms?: number;
  peak_memory_kb?: number;
  points_awarded?: number;
  created_at: string;
}

export interface SubmissionDetail extends SubmissionRow {
  code: string;
  test_results?: unknown[];
  votes?: unknown;
}

export interface NoticeRow {
  id: number;
  title: string;
  body: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
}

export type BugReportCategory = "judging" | "statement" | "sample" | "system" | "other";
export type BugReportStatus = "open" | "in_progress" | "resolved" | "rejected";

export interface BugReportRow {
  id: number;
  user_id: number;
  user_display_name?: string | null;
  problem_id?: number | null;
  problem_title?: string | null;
  category: BugReportCategory;
  title: string;
  body: string;
  code_snapshot?: string | null;
  status: BugReportStatus;
  admin_notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface VerdictBucket {
  bucket: string;
  ac: number;
  sus: number;
  failed: number;
  pending: number;
  total: number;
}

export interface VerdictsResponse {
  series: VerdictBucket[];
  since: string;
  until: string;
}

export interface JudgeBucket {
  bucket: string;
  total_with_votes: number;
  unanimous: number;
  split: number;
  judges: Record<string, { agree_with_final: number; ac: number; sus: number }>;
}

export interface JudgesResponse {
  series: JudgeBucket[];
  judge_ids: string[];
}

export interface UserRow {
  id: number;
  display_name: string;
  nickname?: string;
  email?: string;
  provider: string;
  exp: number;
  submission_count: number;
  has_api_key: boolean;
  created_at: string;
}

export interface ComparisonVariant {
  problem_id: number;
  title?: string;
  level?: string;
  hallucination_score?: number;
  intent_similarity?: number;
  difficulty_similarity?: number;
  judge_score?: number;
  rationale?: string;
  error?: string;
}

export interface ComparisonResponse {
  original_id: number;
  original_title?: string;
  variant_count: number;
  scored_count: number;
  hallucination?: { mean?: number; min?: number; max?: number; count: number };
  intent_similarity?: { mean?: number; min?: number; max?: number; count: number };
  difficulty_similarity?: { mean?: number; min?: number; max?: number; count: number };
  variants: ComparisonVariant[];
}
