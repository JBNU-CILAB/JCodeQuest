import { useCallback, useEffect, useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import { apiGet, apiPost, apiSse, ApiError } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import { Button } from '../components/Button'
import { supabase } from '../lib/supabase'
import type {
  BattleStatusResponse,
  BattleSubmitResponse,
  ScoreboardEntry,
  SubmissionStatusResponse,
} from '../types'

const DEFAULT_CODE = `# 표준 입력에서 읽어 표준 출력으로 결과를 출력하세요
# 예) n = int(input())
`
const MAX_CODE_LENGTH = 64 * 1024

function fmtCountdown(ms: number | null): string {
  if (ms == null) return '--:--'
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

const MEDAL = ['🥇', '🥈', '🥉']

function getErrorDetail(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.body && typeof err.body === 'object' && 'detail' in err.body) {
      return String((err.body as { detail: unknown }).detail)
    }
    return err.message
  }
  return err instanceof Error ? err.message : 'unknown error'
}

function Avatar({ entry, highlight }: { entry: ScoreboardEntry; highlight: boolean }) {
  const ring = highlight ? 'ring-2 ring-brand' : 'ring-1 ring-gray-200'
  if (entry.avatar_url) {
    return (
      <img
        src={entry.avatar_url}
        alt={entry.display_name}
        referrerPolicy="no-referrer"
        className={`w-8 h-8 rounded-full object-cover bg-gray-50 ${ring}`}
      />
    )
  }
  return (
    <div
      className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white bg-gradient-to-br from-brand to-brand-dark ${ring}`}
    >
      {entry.display_name.slice(0, 1)}
    </div>
  )
}

// 세로 정렬 실시간 순위 — lobby/active/finished 본문에서 공통으로 쓰는 스코어보드.
// finished면 1~3위에 메달, 본인 행은 brand-soft 배경 + (나) 라벨로 강조.
function Scoreboard({
  entries,
  myUserId,
  finished,
}: {
  entries: ScoreboardEntry[]
  myUserId: number | undefined
  finished: boolean
}) {
  return (
    <div className="flex flex-col gap-1.5">
      {entries.map((e) => {
        const isMe = e.user_id === myUserId
        const medal = finished && e.rank <= 3 ? MEDAL[e.rank - 1] : null
        return (
          <div
            key={e.user_id}
            className={`flex items-center gap-3 px-3 py-2 rounded-xl border transition ${
              isMe
                ? 'bg-brand-soft border-brand/40'
                : 'bg-white border-gray-100'
            }`}
          >
            <span className="w-7 text-center text-sm font-bold tabular-nums text-gray-500">
              {medal ?? e.rank}
            </span>
            <Avatar entry={e} highlight={isMe} />
            <div className="flex flex-col min-w-0 flex-1">
              <span className="text-[13px] font-semibold text-gray-800 truncate">
                {e.display_name}
                {isMe && <span className="ml-1 text-[10px] text-brand">(나)</span>}
              </span>
              <span className="text-[10px] text-gray-400 tabular-nums">
                {e.attempts > 0 ? `${e.attempts}회 제출` : '미제출'}
                {e.solved_seconds != null &&
                  ` · ${Math.floor(e.solved_seconds / 60)}분 ${Math.floor(
                    e.solved_seconds % 60,
                  )}초`}
              </span>
            </div>
            {e.is_ac ? (
              <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-green-100 text-green-700 border border-green-200">
                AC
              </span>
            ) : (
              <span className="text-[12px] font-semibold tabular-nums text-gray-500">
                {e.tests_passed}/{e.total_tests || '?'}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function Battle() {
  const { session, profile } = useAuth()
  const [snap, setSnap] = useState<BattleStatusResponse | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const serverOffsetRef = useRef(0)

  const [code, setCode] = useState(DEFAULT_CODE)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [mySubId, setMySubId] = useState<number | null>(null)
  const [myGrading, setMyGrading] = useState(false)

  const [toasts, setToasts] = useState<{ id: number; msg: string }[]>([])
  const prevBoardRef = useRef<Map<number, boolean>>(new Map())

  const pushToast = useCallback((msg: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, msg }])
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200)
  }, [])

  // 스냅샷 적용 + 서버시각 오프셋 보정 + 상대 AC 이벤트 토스트(스코어보드 delta).
  const applySnapshot = useCallback(
    (data: BattleStatusResponse) => {
      serverOffsetRef.current = Date.parse(data.server_time) - Date.now()
      const prev = prevBoardRef.current
      for (const e of data.scoreboard) {
        if (e.user_id !== profile?.id && e.is_ac && !prev.get(e.user_id)) {
          pushToast(`${e.display_name} 님 AC! 🎉`)
        }
      }
      prevBoardRef.current = new Map(data.scoreboard.map((e) => [e.user_id, e.is_ac]))
      setSnap(data)
      setLoadError(null)
    },
    [profile?.id, pushToast],
  )

  // 초기 로드 + /current 폴링(배틀 없음/예정/종료 구간에서 다음 배틀 감지용 폴백).
  useEffect(() => {
    if (!session) return
    let active = true
    const fetchCurrent = async () => {
      try {
        const d = await apiGet<BattleStatusResponse>('/battles/current')
        if (active) applySnapshot(d)
      } catch (err) {
        if (active) setLoadError(getErrorDetail(err))
      }
    }
    void fetchCurrent()
    const id = window.setInterval(fetchCurrent, 10_000)
    return () => {
      active = false
      window.clearInterval(id)
    }
  }, [session, applySnapshot])

  // 배틀이 잡히면 SSE 구독 — 단계 전이/채점 완료마다 스코어보드를 즉시 갱신.
  const battleId = snap?.battle_id ?? null
  useEffect(() => {
    if (battleId == null) return
    const close = apiSse<BattleStatusResponse>(`/battles/${battleId}/events`, {
      onMessage: applySnapshot,
    })
    return close
  }, [battleId, applySnapshot])

  // 카운트다운용 1초 틱.
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [])

  // 내 제출 채점 결과 토스트.
  useEffect(() => {
    if (mySubId == null) return
    setMyGrading(true)
    let close: () => void = () => {}
    close = apiSse<SubmissionStatusResponse>(`/grade/${mySubId}/events`, {
      onMessage: (d) => {
        if (d.status === 'done' || d.status === 'failed') {
          setMyGrading(false)
          close()
          if (d.status === 'failed') {
            pushToast('내 제출 채점에 실패했어요')
          } else {
            const results = d.test_results ?? []
            const passed = results.filter((t) => t.passed).length
            pushToast(
              d.final_verdict === 'AC'
                ? `정답! ${passed}/${results.length} 통과 ✅`
                : `${passed}/${results.length} 통과 — 다시 도전!`,
            )
          }
        }
      },
    })
    return close
  }, [mySubId, pushToast])

  if (!session) {
    return (
      <main className="max-w-[760px] mx-auto px-6 py-24 text-center">
        <div className="text-5xl mb-4"></div>
        <h1 className="text-2xl font-black text-gray-800 mb-2">Code Battle</h1>
        <p className="text-sm text-gray-500 mb-8">
          매일 저녁 8시, 모두 같은 문제로 20분간 겨루는 실시간 대전.
          <br />
          로그인하고 참가하세요.
        </p>
        <Button
          onClick={() =>
            supabase.auth.signInWithOAuth({
              provider: 'google',
              options: {
                redirectTo: window.location.origin,
                queryParams: { hd: 'jbnu.ac.kr' },
              },
            })
          }
        >
          로그인하고 참가하기
        </Button>
      </main>
    )
  }

  const serverNow = now + serverOffsetRef.current
  const status = snap?.status ?? null
  const me = profile?.id
  const board = snap?.scoreboard ?? []
  const joined = me != null && board.some((e) => e.user_id === me)

  const msUntil = (iso?: string | null) => (iso ? Date.parse(iso) - serverNow : null)
  const codeBytes = new TextEncoder().encode(code).length
  const overLimit = codeBytes > MAX_CODE_LENGTH

  const handleJoin = async () => {
    if (!snap?.battle_id) return
    try {
      await apiPost(`/battles/${snap.battle_id}/join`)
      pushToast('참가 완료! 행운을 빌어요 🍀')
      const d = await apiGet<BattleStatusResponse>('/battles/current')
      applySnapshot(d)
    } catch (err) {
      pushToast(getErrorDetail(err))
    }
  }

  const handleSubmit = async () => {
    if (!snap?.battle_id || overLimit) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const r = await apiPost<BattleSubmitResponse>(
        `/battles/${snap.battle_id}/submit`,
        { code },
      )
      setMySubId(r.submission_id)
      pushToast('제출 완료 — 채점 중...')
    } catch (err) {
      setSubmitError(getErrorDetail(err))
    } finally {
      setSubmitting(false)
    }
  }

  // ── 헤더(타이머) 라벨/타깃 ──────────────────────────────────────────
  let bannerLabel = '다음 코드 배틀까지'
  let bannerTarget: number | null = msUntil(snap?.next_start_at)
  if (status === 'lobby') {
    bannerLabel = '풀이 시작까지'
    bannerTarget = msUntil(snap?.start_at)
  } else if (status === 'active') {
    bannerLabel = '남은 시간'
    bannerTarget = msUntil(snap?.end_at)
  } else if (status === 'finished') {
    bannerLabel = '다음 배틀까지'
    bannerTarget = msUntil(snap?.next_start_at)
  }

  return (
    <main className="max-w-[1280px] mx-auto w-full px-6 pt-6 pb-16">
      {/* 배너 */}
      <div className="rounded-3xl bg-gradient-to-br from-brand to-brand-dark text-white px-8 py-6 mb-6 flex items-center justify-between flex-wrap gap-4 shadow-lg">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold opacity-90">
            <span className="text-lg"></span> Code Battle
            {status && (
              <span className="px-2 py-0.5 rounded-full bg-white/20 text-[11px] uppercase tracking-wider">
                {status}
              </span>
            )}
          </div>
          <h1 className="text-3xl font-black mt-1">매일 저녁 8시, 실시간 코드 대전</h1>
          <p className="text-sm opacity-80 mt-1">
            {snap?.participant_count ?? 0}명 참가 중
            {snap?.battle_date && ` · ${snap.battle_date}`}
          </p>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase tracking-widest opacity-70">{bannerLabel}</div>
          <div className="text-4xl font-black tabular-nums mt-1">
            {fmtCountdown(bannerTarget)}
          </div>
        </div>
      </div>

      {loadError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3 mb-4">
          {loadError}
        </div>
      )}

      {/* ── 단계별 본문 ── */}
      {(status === null || status === 'scheduled') && (
        <div className="bg-white border border-gray-200 rounded-2xl px-8 py-16 text-center shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
          <div className="text-5xl mb-4"></div>
          <h2 className="text-xl font-bold text-gray-800 mb-2">
            아직 진행 중인 배틀이 없어요
          </h2>
          <p className="text-sm text-gray-500">
            다음 배틀이 시작되면 자동으로 이 화면이 열립니다. 잠시만 기다려 주세요.
          </p>
        </div>
      )}

      {status === 'lobby' && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 items-start">
          <div className="bg-white border border-gray-200 rounded-2xl px-8 py-12 text-center shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
            <div className="text-5xl mb-4">🎮</div>
            <h2 className="text-xl font-bold text-gray-800 mb-2">대기실</h2>
            <p className="text-sm text-gray-500 mb-6">
              곧 문제가 공개됩니다. 참가 버튼을 눌러 입장하세요.
              <br />
              모두 같은 문제를 풀고, 빨리·정확히 푼 순으로 순위가 매겨집니다.
            </p>
            {joined ? (
              <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-green-50 text-green-700 border border-green-200 text-sm font-semibold">
                ✓ 참가 완료 — 시작을 기다리는 중
              </div>
            ) : (
              <Button onClick={handleJoin}>참가하기</Button>
            )}
          </div>
          <div className="bg-white border border-gray-200 rounded-2xl px-5 py-5 shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
            <h3 className="text-sm font-bold text-gray-800 mb-3">
              참가자 {board.length}명
            </h3>
            <Scoreboard entries={board} myUserId={me} finished={false} />
          </div>
        </div>
      )}

      {status === 'active' && snap?.problem && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-5 items-start">
          {/* 문제 + 에디터 — 세로 스택 */}
          <div className="flex flex-col gap-5 min-w-0">
          {/* 문제 */}
          <aside className="bg-white border border-gray-200 rounded-2xl px-6 py-5 shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
            <div className="flex items-center gap-2 mb-2">
              <span className="px-2 py-0.5 text-[11px] font-bold rounded-full bg-amber-100 text-amber-800 border border-amber-200">
                {snap.problem.level.toUpperCase()}
              </span>
              <span className="ml-auto text-xs font-bold text-brand tabular-nums">
                {snap.problem.points} pt
              </span>
            </div>
            <h2 className="text-lg font-bold text-gray-800 mb-1">{snap.problem.title}</h2>
            <p className="text-[12px] text-gray-500 mb-3">{snap.problem.one_line_summary}</p>
            <p className="text-[13px] text-gray-700 whitespace-pre-wrap leading-relaxed mb-4">
              {snap.problem.statement}
            </p>
            {snap.problem.sample_test_cases.length > 0 && (
              <div className="flex flex-col gap-2 border-t border-gray-100 pt-3">
                {snap.problem.sample_test_cases.map((tc) => (
                  <div key={tc.ordinal} className="grid grid-cols-2 gap-2">
                    <pre className="bg-gray-50 border border-gray-200 rounded-lg px-2 py-1.5 text-[11px] font-mono whitespace-pre overflow-x-auto">
                      {tc.stdin}
                    </pre>
                    <pre className="bg-gray-50 border border-gray-200 rounded-lg px-2 py-1.5 text-[11px] font-mono whitespace-pre overflow-x-auto">
                      {tc.expected_stdout}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </aside>

          {/* 에디터 */}
          <section className="flex flex-col gap-2">
            <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
              <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100 bg-gray-50">
                <span className="text-xs font-bold text-gray-600">Python 3</span>
                <span
                  className={`text-[10px] tabular-nums ${overLimit ? 'text-red-500 font-semibold' : 'text-gray-400'}`}
                >
                  {codeBytes.toLocaleString()} / {MAX_CODE_LENGTH.toLocaleString()} bytes
                </span>
              </div>
              <Editor
                height="56vh"
                defaultLanguage="python"
                value={code}
                onChange={(v) => setCode(v ?? '')}
                theme="vs"
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  tabSize: 4,
                  insertSpaces: true,
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                  renderLineHighlight: 'line',
                }}
              />
            </div>
            {submitError && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-[13px] rounded-xl px-4 py-2.5">
                {submitError}
              </div>
            )}
            <div className="flex items-center justify-end gap-2">
              {myGrading && (
                <span className="text-xs text-gray-500">내 제출 채점 중...</span>
              )}
              <Button
                variant={!submitting && !overLimit ? 'primary' : 'disabled'}
                disabled={submitting || overLimit}
                onClick={handleSubmit}
              >
                {submitting ? '제출 중...' : '제출하기'}
              </Button>
            </div>
          </section>
          </div>

          {/* 실시간 스코어보드 — lg 미만에선 문제·에디터 아래로 내려간다 */}
          <div className="bg-white border border-gray-200 rounded-2xl px-5 py-5 shadow-[0_1px_2px_rgba(31,41,55,0.03)] lg:sticky lg:top-4">
            <h3 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              실시간 순위
            </h3>
            <Scoreboard entries={board} myUserId={me} finished={false} />
          </div>
        </div>
      )}

      {status === 'finished' && (
        <div className="max-w-[640px] mx-auto">
          <div className="bg-white border border-gray-200 rounded-2xl px-6 py-6 shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
            <h2 className="text-lg font-bold text-gray-800 mb-1 text-center">
              🏁 최종 순위
            </h2>
            <p className="text-xs text-gray-400 text-center mb-5">
              {snap?.problem?.title}
            </p>
            <Scoreboard entries={board} myUserId={me} finished />
          </div>
        </div>
      )}

      {/* 이벤트 토스트 */}
      <div className="fixed right-5 bottom-6 z-[2000] flex flex-col gap-2 items-end">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="bg-gray-800 text-white px-4 py-2.5 rounded-xl text-[13px] shadow-[0_12px_30px_rgba(0,0,0,0.25)]"
            style={{ animation: 'toast-pop-in 0.18s ease-out' }}
            role="status"
          >
            {t.msg}
          </div>
        ))}
      </div>
    </main>
  )
}
