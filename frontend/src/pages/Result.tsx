import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { apiGet, apiPost, apiSse, ApiError } from '../lib/api'
import { Button } from '../components/Button'
import type {
  JudgeVote,
  SubmissionStatus,
  SubmissionStatusResponse,
  TestResult,
  TutorHistoryResponse,
  TutorResponse,
  Verdict,
} from '../types'

// ───────────────────────── Status badge ─────────────────────────

const STATUS_STYLE: Record<SubmissionStatus, { bg: string; label: string }> = {
  queued: { bg: 'bg-gray-200 text-gray-700', label: '대기' },
  running: { bg: 'bg-blue-100 text-blue-700', label: '채점 중' },
  done: { bg: 'bg-emerald-100 text-emerald-700', label: '완료' },
  failed: { bg: 'bg-rose-100 text-rose-700', label: '실패' },
}

function StatusBadge({ status }: { status: SubmissionStatus }) {
  const s = STATUS_STYLE[status]
  return (
    <span className={`px-2 py-0.5 text-xs font-bold rounded-full ${s.bg}`}>
      {s.label}
    </span>
  )
}

// ───────────────────────── Verdict banner ─────────────────────────

const VERDICT_STYLE: Record<
  Verdict,
  { wrap: string; chip: string; emoji: string; label: string; sub: string }
> = {
  AC: {
    wrap: 'bg-emerald-50 border-emerald-200',
    chip: 'bg-emerald-500 text-white',
    emoji: '🎉',
    label: 'Accepted',
    sub: '모든 테스트 통과 + 심사위원단 승인',
  },
  SUS: {
    wrap: 'bg-rose-50 border-rose-200',
    chip: 'bg-rose-500 text-white',
    emoji: '🤔',
    label: 'Suspect',
    sub: '테스트 실패 또는 심사위원단이 의도와 다르다고 판단',
  },
}

function VerdictBanner({
  verdict,
  pointsAwarded,
}: {
  verdict: Verdict
  pointsAwarded: number | null
}) {
  const s = VERDICT_STYLE[verdict]
  return (
    <div className={`border-2 rounded-2xl px-8 py-6 flex items-center gap-5 ${s.wrap}`}>
      <span className="text-5xl leading-none">{s.emoji}</span>
      <div className="flex-1">
        <div className="flex items-center gap-3 mb-1">
          <span className={`px-3 py-1 text-sm font-bold rounded-full ${s.chip}`}>
            {verdict}
          </span>
          <span className="text-xl font-extrabold text-gray-800">{s.label}</span>
        </div>
        <p className="text-xs text-gray-600">{s.sub}</p>
        {pointsAwarded != null && pointsAwarded > 0 && (
          <p className="mt-2 text-sm">
            <span className="font-bold text-brand">+{pointsAwarded} pt</span>
            <span className="text-gray-500"> 획득!</span>
          </p>
        )}
      </div>
    </div>
  )
}

// ───────────────────────── Test results ─────────────────────────

function TestResultsList({ results }: { results: TestResult[] }) {
  const passed = results.filter((r) => r.passed).length
  return (
    <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
      <div className="flex items-center justify-between px-6 py-3.5 border-b border-gray-100">
        <h2 className="text-sm font-bold text-gray-800">테스트 케이스 결과</h2>
        <span className="text-xs text-gray-500 tabular-nums">
          {passed} / {results.length} 통과
        </span>
      </div>
      <div className="divide-y divide-gray-100">
        {results.map((r) => (
          <div key={r.ordinal} className="px-6 py-3">
            <div className="flex items-center gap-3 text-sm">
              <span className="text-gray-500 font-mono w-8">#{r.ordinal}</span>
              <span
                className={`px-2 py-0.5 text-[11px] font-bold rounded ${
                  r.passed
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-rose-100 text-rose-700'
                }`}
              >
                {r.passed ? 'PASS' : 'FAIL'}
              </span>
              <span className="text-xs text-gray-500 uppercase tracking-wider">
                {r.status}
              </span>
              <span className="ml-auto flex items-center gap-3 text-xs text-gray-500 tabular-nums">
                <span>{r.elapsed_ms} ms</span>
                <span>{(r.peak_memory_kb / 1024).toFixed(1)} MB</span>
              </span>
            </div>
            {!r.passed && r.error && (
              <pre className="mt-2 bg-rose-50 border border-rose-100 rounded-lg p-2.5 text-[11px] font-mono text-rose-700 whitespace-pre-wrap overflow-x-auto">
                {r.error}
              </pre>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ───────────────────────── Ensemble votes ─────────────────────────

const JUDGE_LABEL: Record<string, string> = {
  melchior: 'Melchior',
  balthasar: 'Balthasar',
  casper: 'Casper',
}

function EnsembleVotes({ votes }: { votes: JudgeVote[] }) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl px-6 py-5 shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
      <h2 className="text-sm font-bold text-gray-800 mb-4">AI 심사위원단</h2>
      <div className="grid gap-3 md:grid-cols-3">
        {votes.map((v) => (
          <div
            key={v.judge_id}
            className="border border-gray-200 rounded-xl px-4 py-3 flex flex-col gap-2 bg-gray-50/50"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-gray-700">
                {JUDGE_LABEL[v.judge_id] ?? v.judge_id}
              </span>
              <span
                className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                  v.verdict === 'AC'
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-rose-100 text-rose-700'
                }`}
              >
                {v.verdict}
              </span>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-gray-500">
              <span>의도 {v.intent_match ? '✓' : '✗'}</span>
              <span>·</span>
              <span>확신 {(v.confidence * 100).toFixed(0)}%</span>
            </div>
            <p className="text-[12px] text-gray-600 leading-relaxed">
              {v.rationale}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}

// ───────────────────────── Tutor panel ─────────────────────────

function TutorPanel({ submissionId }: { submissionId: number }) {
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadOnce, setLoadOnce] = useState(false)
  const [usageCount, setUsageCount] = useState<number>(0)
  const [remainingUses, setRemainingUses] = useState<number>(3)

  // 초기 로드: 이력 조회만 (메시지 자동 로드 X)
  useEffect(() => {
    if (loadOnce) return
    setLoadOnce(true)

    apiGet<TutorHistoryResponse>(`/tutor/${submissionId}/history`)
      .then((h) => {
        setUsageCount(h.usage_count)
        setRemainingUses(h.remaining_uses)
        if (h.messages.length > 0) {
          setMessage(h.messages[h.messages.length - 1].message)
        }
        setError(null)
      })
      .catch((err) => {
        const msg = err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'unknown'
        setError(msg)
      })
  }, [submissionId, loadOnce])

  const requestTutor = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiPost<TutorResponse>(`/tutor/${submissionId}`)
      setMessage(res.message)
      setUsageCount((prev) => prev + 1)
      setRemainingUses((prev) => Math.max(0, prev - 1))
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'unknown'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const regenerate = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiPost<TutorResponse>(
        `/tutor/${submissionId}?regenerate=true`,
      )
      setMessage(res.message)
      setUsageCount((prev) => prev + 1)
      setRemainingUses((prev) => Math.max(0, prev - 1))
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'unknown'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const canRequest = remainingUses > 0 && !loading
  const hasReachedLimit = remainingUses === 0 && usageCount > 0

  return (
    <div className="bg-white border border-gray-200 rounded-2xl px-6 py-5 shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-bold text-gray-800 flex items-center gap-2">
          <span>🤖</span>
          <span>AI 튜터</span>
        </h2>
        <div className="text-xs text-gray-500">
          {usageCount > 0 && (
            <span>
              {remainingUses > 0 ? '남은 사용' : '사용'} {remainingUses}/3
            </span>
          )}
        </div>
      </div>

      {/* 에러 상태 */}
      {error && (
        <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-lg">
          <p className="text-sm text-rose-700">
            {error.includes('API 키')
              ? '로그인 후 프로필에서 API 키를 설정해주세요.'
              : error}
          </p>
        </div>
      )}

      {/* 메시지 표시 */}
      {message && (
        <div className="mb-4 prose prose-sm max-w-none text-gray-700 [&_pre]:bg-gray-900 [&_pre]:text-gray-100 [&_pre]:rounded-lg [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[12px] [&_pre_code]:bg-transparent [&_pre_code]:p-0">
          <ReactMarkdown>{message}</ReactMarkdown>
        </div>
      )}

      {/* 한도 도달 메시지 */}
      {hasReachedLimit && (
        <p className="text-xs text-gray-500 mb-3 p-3 bg-gray-50 rounded">
          이 문제에 대한 튜터 사용 한도(3회)에 도달했습니다.
        </p>
      )}

      {/* 로딩 상태 */}
      {loading && (
        <p className="text-sm text-gray-400 py-2">
          {message ? '다시 생성 중...' : '튜터가 코드를 읽고 있습니다...'}
        </p>
      )}

      {/* 버튼 영역 */}
      <div className="flex gap-2">
        {!message && (
          <Button
            disabled={!canRequest}
            onClick={requestTutor}
            className="flex-1"
          >
            {loading ? '생성 중...' : canRequest ? '튜터에게 묻기' : '한도 도달'}
          </Button>
        )}
        {message && (
          <>
            <Button
              variant="ghost"
              size="sm"
              disabled={!canRequest}
              onClick={regenerate}
            >
              {canRequest ? '다시 묻기' : '한도 도달'}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

// ───────────────────────── Page ─────────────────────────

export function Result() {
  const { id } = useParams<{ id: string }>()
  const submissionId = id ? parseInt(id, 10) : NaN

  const [snapshot, setSnapshot] = useState<SubmissionStatusResponse | null>(null)
  const [streamError, setStreamError] = useState<string | null>(null)

  useEffect(() => {
    if (!Number.isFinite(submissionId)) return
    setStreamError(null)
    setSnapshot(null)
    // SSE 가 자체적으로 첫 메시지로 현재 스냅샷을 보내준다 (backend grading.py).
    // 그래서 별도 GET /grade/{id} 없이 구독만 하면 충분.
    let close: () => void = () => {}
    let terminalReached = false
    close = apiSse<SubmissionStatusResponse>(
      `/grade/${submissionId}/events`,
      {
        onMessage: (data) => {
          setSnapshot(data)
          // backend가 done/failed에서 스트림을 닫지만 EventSource는 자동 재연결을
          // 시도한다. 같은 메시지가 반복되지 않도록 클라이언트에서 명시적으로 close.
          if (data.status === 'done' || data.status === 'failed') {
            terminalReached = true
            close()
          }
        },
        onError: () => {
          if (!terminalReached) {
            setStreamError('실시간 연결이 끊겼습니다. 새로고침해 보세요.')
          }
        },
      },
    )
    return close
  }, [submissionId])

  if (!Number.isFinite(submissionId)) {
    return (
      <main className="max-w-[900px] mx-auto px-8 py-16 text-center text-red-500 text-sm">
        잘못된 제출 ID입니다.
      </main>
    )
  }

  const isProgress =
    !snapshot || snapshot.status === 'queued' || snapshot.status === 'running'

  return (
    <main className="max-w-[900px] mx-auto w-full px-6 pt-6 pb-12 flex flex-col gap-4">
      {/* 헤더 */}
      <div className="flex items-center gap-3 text-sm">
        <Link to="/problems" className="text-gray-500 hover:text-brand">
          ← 문제 목록
        </Link>
        <span className="text-gray-300">/</span>
        <span className="font-bold text-gray-700">제출 #{submissionId}</span>
        {snapshot && <StatusBadge status={snapshot.status} />}
      </div>

      {/* 진행 중 */}
      {isProgress && (
        <div className="bg-white border border-gray-200 rounded-2xl px-8 py-10 text-center shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
          <div
            className="inline-block w-8 h-8 border-[3px] border-brand border-t-transparent rounded-full animate-spin mb-3"
            aria-hidden="true"
          />
          <p className="text-sm text-gray-700 font-semibold">
            {snapshot?.status === 'running' ? '채점 중...' : '채점 대기 중...'}
          </p>
          <p className="text-xs text-gray-400 mt-1">
            실시간으로 진행 상태를 받고 있습니다
          </p>
        </div>
      )}

      {/* 실패 */}
      {snapshot?.status === 'failed' && (
        <div className="bg-rose-50 border-2 border-rose-200 rounded-2xl px-6 py-4">
          <p className="text-sm font-bold text-rose-800">채점 작업이 실패했습니다.</p>
          <p className="text-xs text-rose-600 mt-1">
            잠시 후 다시 제출해보거나, 관리자에게 문의하세요.
          </p>
        </div>
      )}

      {streamError && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded-lg px-4 py-2">
          {streamError}
        </div>
      )}

      {/* 채점 완료 */}
      {snapshot?.status === 'done' && snapshot.final_verdict && (
        <VerdictBanner
          verdict={snapshot.final_verdict}
          pointsAwarded={snapshot.points_awarded}
        />
      )}

      {snapshot?.test_results && snapshot.test_results.length > 0 && (
        <TestResultsList results={snapshot.test_results} />
      )}

      {snapshot?.ensemble && <EnsembleVotes votes={snapshot.ensemble.votes} />}

      {snapshot?.status === 'done' && (
        <TutorPanel submissionId={submissionId} />
      )}
    </main>
  )
}
