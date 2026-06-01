import { useEffect, useState } from "react";
import type { ConnSettings, ProblemRow } from "../types";
import { adminFetch } from "../api";

/**
 * 문제 선택 드롭다운 — 기존 `<input type=number>`(문제 ID)을 대체.
 *
 * - /api/problems?originals_only=... 로 1회 fetch 후 (baseUrl, originalsOnly) 키로 모듈 캐시.
 *   같은 세션에서 여러 뷰가 동시에 열려도 네트워크 호출은 1회.
 * - value/onChange 는 기존 input과의 호환을 위해 문자열(문제 id 또는 "") 로 다룬다.
 *   서버 쿼리 파라미터를 그대로 쓰는 호출부(SubmissionsView, PlagiarismView 등)를
 *   바꾸지 않고 드롭다운으로 교체할 수 있다.
 * - 옵션 라벨은 `#id · title`. 비어있을 때는 placeholder를 노출하고,
 *   로딩/실패 상태도 동일 select 안에 한 옵션으로 표현해 외부 레이아웃에 영향이 없다.
 */

type CacheKey = string;
type CacheState = {
  promise?: Promise<ProblemRow[]>;
  list?: ProblemRow[];
  error?: string;
};
const cache = new Map<CacheKey, CacheState>();

function keyOf(settings: ConnSettings, originalsOnly: boolean): CacheKey {
  return `${settings.baseUrl}::${originalsOnly ? "orig" : "all"}`;
}

async function loadProblems(
  settings: ConnSettings,
  originalsOnly: boolean,
): Promise<ProblemRow[]> {
  const key = keyOf(settings, originalsOnly);
  const cached = cache.get(key);
  if (cached?.list) return cached.list;
  if (cached?.promise) return cached.promise;

  const promise = (async () => {
    const r = await adminFetch(
      `/api/problems?originals_only=${originalsOnly ? "true" : "false"}`,
      settings,
    );
    if (!r.ok) {
      const t = await r.text();
      throw new Error(`[${r.status}] ${t.slice(0, 200)}`);
    }
    const list: ProblemRow[] = await r.json();
    list.sort((a, b) => b.id - a.id); // 최신순
    cache.set(key, { list });
    return list;
  })();
  cache.set(key, { promise });
  try {
    return await promise;
  } catch (e) {
    cache.set(key, { error: (e as Error).message });
    throw e;
  }
}

/** 외부에서 새로 출제하거나 삭제한 뒤 다시 받아오고 싶을 때 호출. */
export function invalidateProblemPickerCache(): void {
  cache.clear();
}

/**
 * 모듈 캐시를 공유한 채로 문제 목록을 가져오고 싶은 호출부(예: "모든 문제" 일괄 처리)를
 * 위해 노출. UI 컴포넌트와 동일한 (baseUrl, originalsOnly) 키를 쓴다.
 */
export function loadProblemsList(
  settings: ConnSettings,
  originalsOnly = false,
): Promise<ProblemRow[]> {
  return loadProblems(settings, originalsOnly);
}

interface Props {
  settings: ConnSettings;
  value: string; // "" = 미선택
  onChange: (v: string) => void;
  /** true 면 원본만, false 면 변형 포함. 기본 false. */
  originalsOnly?: boolean;
  /** "" 값일 때 표시할 placeholder. 기본 "전체". */
  placeholder?: string;
  /** placeholder 바로 아래 추가할 옵션들(예: "모든 문제" 일괄 실행 sentinel). */
  extraOptions?: { value: string; label: string }[];
  disabled?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

export default function ProblemPicker({
  settings,
  value,
  onChange,
  originalsOnly = false,
  placeholder = "전체",
  extraOptions,
  disabled,
  className,
  style,
}: Props) {
  const [problems, setProblems] = useState<ProblemRow[] | null>(() => {
    const c = cache.get(keyOf(settings, originalsOnly));
    return c?.list ?? null;
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    const cached = cache.get(keyOf(settings, originalsOnly));
    if (cached?.list) {
      setProblems(cached.list);
      return;
    }
    setProblems(null);
    loadProblems(settings, originalsOnly)
      .then((list) => {
        if (!cancelled) setProblems(list);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setError(e.message);
          setProblems([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [settings, originalsOnly]);

  const loading = problems === null;
  const empty = !loading && (problems?.length ?? 0) === 0;

  // 선택된 id 가 현재 목록에 없으면(외부에서 미리 주입된 값) 옵션을 임시로 한 줄 추가해
  // 컨트롤드 select의 경고/리셋을 막는다. extraOptions(sentinel 값)도 "목록에 있는" 것으로
  // 간주해 동일 처리가 두 번 들어가지 않게 한다.
  const numericValue = value && /^\d+$/.test(value) ? Number(value) : null;
  const isExtraValue = (extraOptions ?? []).some((o) => o.value === value);
  const hasInList =
    (numericValue != null && (problems ?? []).some((p) => p.id === numericValue)) ||
    isExtraValue;

  return (
    <select
      className={className}
      style={style}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled || loading}
      title={error ?? undefined}
    >
      <option value="">
        {loading
          ? "문제 목록 불러오는 중…"
          : error
            ? `오류: ${error}`
            : empty
              ? "문제 없음"
              : placeholder}
      </option>
      {extraOptions?.map((o) => (
        <option key={`extra:${o.value}`} value={o.value}>
          {o.label}
        </option>
      ))}
      {value !== "" && !hasInList && (
        <option value={value}>
          {numericValue != null ? `#${value} · (목록에 없음)` : value}
        </option>
      )}
      {problems?.map((p) => (
        <option key={p.id} value={String(p.id)}>
          #{p.id} · {p.title}
        </option>
      ))}
    </select>
  );
}
