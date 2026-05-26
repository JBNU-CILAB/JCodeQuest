/* RunsView 노드 정의 + 포맷 헬퍼.
 * NODE_DEFS는 authoring graph.py의 9개 노드(= node_stats.NODE_ORDER)와 1:1.
 * kind: llm(LLM 호출) · sandbox(코드 실행) · db(DB·임베딩 I/O). side: 게이트성 부가 단계. */

export interface EnsembleMember {
  id: string;     // 판사 식별자 (trace span: judge_quality/{id}#n)
  model: string;  // 기본 모델명 (env로 override 가능 — 표시용 기본값)
}

export interface NodeDef {
  key: string;
  label: string;
  kind: "llm" | "sandbox" | "db";
  side?: boolean;
  note: string;
  ensemble?: EnsembleMember[];   // 3-LLM 앙상블 노드면 멤버 목록 — 그래프에서 서브노드로 펼침
}

export const NODE_DEFS: NodeDef[] = [
  { key: "fetch_problem", label: "fetch_problem", kind: "db", note: "원본 문제·시드·형제 임베딩을 DB에서 가져옵니다." },
  { key: "retrieve_exemplars", label: "retrieve_exemplars", kind: "db", note: "같은 카테고리 모범 사례를 MMR로 골라 RAG grounding으로 넘깁니다." },
  { key: "generate_variants", label: "generate_variants", kind: "llm", note: "draft→신규성 검사→author_solution. 변형 후보를 생성합니다." },
  { key: "verify_candidates", label: "verify_candidates", kind: "sandbox", note: "reference_code를 샌드박스로 실행해 expected_stdout을 채우고 검증합니다." },
  {
    key: "judge_candidates", label: "judge_candidates", kind: "llm",
    note: "3-judge 앙상블 품질 심사. 점수 중앙값으로 통과/탈락. 가장 무거운 노드.",
    ensemble: [
      { id: "Melchior", model: "qwen2.5-coder:14b" },
      { id: "Balthasar", model: "deepseek-coder-v2:lite" },
      { id: "Casper", model: "llama3.1:8b" },
    ],
  },
  { key: "solve_candidates", label: "solve_candidates", kind: "llm", note: "LLM이 후보 문제를 직접 풀어 풀이 가능성(solvable)을 확인합니다." },
  { key: "attack_candidates", label: "attack_candidates", kind: "llm", side: true, note: "결함을 심은 공격 풀이가 테스트에 걸리는지(변별력) 검사하는 게이트." },
  { key: "compare_to_original", label: "compare_to_original", kind: "llm", side: true, note: "원본과 변형을 비교해 환각/의도/난이도 3축을 기록·게이트합니다." },
  { key: "persist_approved", label: "persist_approved", kind: "db", note: "3-게이트(solver·변별력·compare)를 통과한 변형을 DB에 저장합니다." },
];

export function fmtDuration(ms?: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(2)} s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s % 60)}s`;
}

export function fmtTokens(n?: number | null): string {
  if (!n) return "0";
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(1)}k`;
}

export function fmtRelTime(iso?: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "방금 전";
  if (m < 60) return `${m}분 전`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}시간 전`;
  const d = Math.floor(h / 24);
  return `${d}일 전`;
}
