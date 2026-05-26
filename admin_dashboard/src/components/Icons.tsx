/* 공용 인라인 SVG 아이콘 — rail 네비 + runs 그래프/드로어. currentColor 상속. */
type P = React.SVGProps<SVGSVGElement>;

export const RailIcons = {
  runs: (p: P) => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" {...p}>
      <rect x="3" y="6" width="6" height="4" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <rect x="15" y="6" width="6" height="4" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <rect x="3" y="14" width="6" height="4" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <rect x="15" y="14" width="6" height="4" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <path d="M9 8h6M9 16h6M12 10v4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  stats: (p: P) => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  problems: (p: P) => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" {...p}>
      <rect x="4" y="3" width="16" height="18" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  submissions: (p: P) => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" stroke="currentColor" strokeWidth="1.6" />
      <rect x="9" y="3" width="6" height="4" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  notices: (p: P) => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M6 8a6 6 0 1 1 12 0v5l2 3H4l2-3V8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M10 19a2 2 0 0 0 4 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  reports: (p: P) => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" {...p}>
      <path d="M12 3l9 16H3l9-16z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M12 10v4M12 16.5v.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  users: (p: P) => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" {...p}>
      <circle cx="12" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5 20c1-3.6 4-5.5 7-5.5s6 1.9 7 5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
};

export const Icon = {
  Search: (p: P) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M11 11l3 3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  ZoomIn: (p: P) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M8 4v8M4 8h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  ZoomOut: (p: P) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M4 8h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  Reset: (p: P) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M3 8a5 5 0 1 0 1.46-3.54M3 4v3h3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  Close: (p: P) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  ),
  Rerun: (p: P) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M13.5 6A6 6 0 1 0 14 9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 5h3.5V1.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  Copy: (p: P) => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" {...p}>
      <rect x="5" y="5" width="9" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
      <path d="M3 11V3a1 1 0 0 1 1-1h8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
  Box: (p: P) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <rect x="2.5" y="2.5" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 6h4M6 9h4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
  LLM: (p: P) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.4" />
      <path d="M5 8c1 1.5 5 1.5 6 0" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="6" cy="6.5" r="0.7" fill="currentColor" />
      <circle cx="10" cy="6.5" r="0.7" fill="currentColor" />
    </svg>
  ),
  DB: (p: P) => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" {...p}>
      <ellipse cx="8" cy="4" rx="5" ry="1.8" stroke="currentColor" strokeWidth="1.4" />
      <path d="M3 4v8c0 1 2.2 1.8 5 1.8s5-.8 5-1.8V4M3 8c0 1 2.2 1.8 5 1.8s5-.8 5-1.8" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  ),
  External: (p: P) => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" {...p}>
      <path d="M6 3H3.5A1.5 1.5 0 0 0 2 4.5v8A1.5 1.5 0 0 0 3.5 14h8a1.5 1.5 0 0 0 1.5-1.5V10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <path d="M9.5 2.5H13.5V6.5M13 3l-6 6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
};

export function NodeKindIcon({ kind }: { kind: string }) {
  if (kind === "llm") return <Icon.LLM />;
  if (kind === "db") return <Icon.DB />;
  return <Icon.Box />;
}
