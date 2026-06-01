import { useCallback, useRef, useState, useTransition } from "react";

/**
 * React 19 `use` 패턴을 위한 공통 훅.
 *
 * 호출 측은 `fetcher`와 의존성 배열만 넘기고, 반환된 `promise`를 자식 컴포넌트에 전달해
 * `use(promise)` 로 읽도록 한다(자식은 Suspense 경계 안에 있어야 함).
 *
 * - `refresh()` 는 내부 version 카운터를 올려 동일 deps 라도 새로운 Promise 를 만든다.
 *   `useTransition` 안에서 setState 하므로, 자식이 다시 suspend 해도 이전 UI 가 유지되고
 *   Suspense fallback 이 깜빡이지 않는다(`isPending` 으로 갱신 중 표시 가능).
 * - 의존성(필터·페이지 등)이 바뀌면 자동으로 새 Promise 가 만들어진다.
 *
 * ⚠️ Promise 캐시는 `useRef` 로 저장한다. `useMemo` 는 "성능 힌트"라 React 가 캐시를
 *    임의로 버릴 수 있고, 그 경우 `use(promise)` 에 새 promise 가 들어가 매 렌더 다시
 *    suspend → resolve → 재렌더 → 새 promise 무한 루프가 생긴다(StrictMode 와 Suspense
 *    조합에서 특히 잘 발생). `useRef` 는 unmount 까지 동일 객체를 보장하므로 안전.
 */
export function useResource<T>(
  fetcher: () => Promise<T>,
  deps: ReadonlyArray<unknown>,
): {
  promise: Promise<T>;
  refresh: () => void;
  isPending: boolean;
} {
  const [version, setVersion] = useState(0);
  const [isPending, startTransition] = useTransition();

  // 매 렌더 새로 만들어지는 fetcher 참조를 안정적으로 잡아두기 위함 — 의존성으로 쓰면
  // 새 함수 인스턴스마다 캐시가 무효화돼 의미가 없다. 키는 deps + version 뿐.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // promise / 그것을 만든 키를 ref 에 보관. 키가 element-wise 동일하면 캐시 적중.
  const cacheRef = useRef<{
    promise: Promise<T>;
    key: ReadonlyArray<unknown>;
  } | null>(null);

  const key: ReadonlyArray<unknown> = [...deps, version];
  if (cacheRef.current === null || !sameKey(cacheRef.current.key, key)) {
    cacheRef.current = { promise: fetcherRef.current(), key };
  }

  const refresh = useCallback(() => {
    // transition 으로 묶어야 Suspense fallback 으로 떨어지지 않고 이전 UI 가 유지된다.
    startTransition(() => {
      setVersion((v) => v + 1);
    });
  }, []);

  return { promise: cacheRef.current.promise, refresh, isPending };
}

function sameKey(a: ReadonlyArray<unknown>, b: ReadonlyArray<unknown>): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (!Object.is(a[i], b[i])) return false;
  }
  return true;
}

/**
 * fetch 응답을 받아 JSON 으로 풀고 비-2xx 일 때 에러로 던지는 작은 헬퍼.
 * `useResource` 의 fetcher 안에서 표준 처리로 쓰기 위함.
 */
export async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`[${res.status}] ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}
