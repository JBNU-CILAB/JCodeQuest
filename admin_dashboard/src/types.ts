export interface ConnSettings {
  baseUrl: string;
  baseToken: string;
  judgeUrl: string;
  judgeToken: string;
}

export type ConnStatus = "idle" | "ok" | "error" | "loading";

export type Route = "runs" | "problems" | "submissions" | "notices" | "reports" | "stats" | "users";

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

/* ── 출제 파이프라인 메타 (authoring_meta) ─────────────────────────────
   backend가 ProblemRow.authoring_meta(opaque JSON)에 그대로 들고 있는 값.
   향후 생성분에만 rag 섹션이 채워진다(기존 변형은 rag 미존재 → null 처리). */
export interface RagExemplar {
  id: number | null;
  title: string | null;
}

export interface AuthoringMeta {
  candidate_index?: number | null;
  // LLM-as-a-Judge 품질 심사
  judge_score?: number | null;          // 판사 점수 중앙값
  judge_scores?: number[];              // per-judge 점수
  judge_passed?: boolean | null;
  judge_rationale?: string | null;
  judge_issues?: string[];
  // 솔버(LLM이 직접 풀이)
  solver_results?: { judge_id?: string; verdict?: string; rationale?: string; code?: string }[];
  solver_passed?: boolean | null;
  // verify(reference_code 실행)
  verify_passed?: boolean | null;
  verify_error?: string | null;
  verify_attempts?: number | null;
  // 테스트 변별력(결함 풀이 공격)
  discrimination?: {
    score?: number | null;
    passed?: boolean | null;
    attacks?: { strategy?: string; verdict?: string; rejected?: boolean; rationale?: string; code?: string }[];
  };
  // 원본-변형 비교 3축
  comparison?: {
    hallucination_score?: number | null;
    intent_similarity?: number | null;
    difficulty_similarity?: number | null;
    rationale?: string;
    error?: string;
    passed?: boolean | null;
  };
  // 신규성(임베딩 cosine) — RAG 임베딩의 "밀어내기" 방향
  novelty?: {
    max_similarity?: number | null;
    closest_id?: number | null;
    attempts?: number | null;
    threshold?: number | null;          // 게이트 기준선 (>= 이면 재draft) — 옛 변형엔 없음
  };
  // RAG exemplar 검색 — "끌어오기" 방향. enabled=true & exemplars=[]면 빈 코퍼스/폴백.
  rag?: {
    enabled?: boolean;
    top_k?: number;
    mmr_lambda?: number;
    level_window?: number;
    min_judge_score?: number;
    exemplars?: RagExemplar[];
  };
  issued_iso_week?: string;
  source?: string;                      // "manual" (수기 등록 원본)
}

export interface ProblemTestCase {
  ordinal: number;
  stdin: string;
  expected_stdout: string;
  is_sample: boolean;
}

/* /api/problems/{id} (ProblemDetailOut) — authoring_meta 포함 관리자 시야 */
export interface ProblemDetail {
  id: number;
  title: string;
  category: string;
  level: string;
  status: string;
  parent_id: number | null;
  langsmith_trace_id?: string | null;
  created_at?: string | null;
  child_count?: number;
  avg_judge_score?: number | null;
  statement: string;
  reference_code: string;
  intent_rubric?: Record<string, unknown> | null;
  authoring_meta?: AuthoringMeta | null;
  points: number;
  time_limit_ms: number;
  memory_limit_mb: number;
  test_cases: ProblemTestCase[];
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

/* ── 파이프라인 run (RunsView · forensics) ─────────────────────────────── */
export interface RunCandidateResult {
  idx: number;
  status: "pass" | "fail" | "warn" | string;
  note?: string;
}

export interface RunNodeStateT {
  status: "queued" | "running" | "done" | "failed" | "skipped" | string;
  duration_ms?: number | null;
  retries?: number;
  tokens?: { prompt?: number; completion?: number; total?: number };
  error?: string | null;
  candidates_in?: number | null;
  candidates_out?: number | null;
  candidate_results?: RunCandidateResult[];
  outputs_preview?: Record<string, unknown> | null;
}

export interface RunSummaryT {
  id: string;
  trace_id?: string | null;
  problem_id?: number | null;
  problem_title?: string | null;
  target_count: number;
  by_user?: string | null;
  status: "running" | "done" | "failed" | string;
  failed_at_node?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  total_duration_ms?: number | null;
  saved_count: number;
}

export interface RunDetailT extends RunSummaryT {
  node_states: Record<string, RunNodeStateT>;
  saved_problem_ids: number[];
  errors: string[];
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
