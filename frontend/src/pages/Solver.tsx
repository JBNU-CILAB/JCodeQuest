import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Editor from '@monaco-editor/react'
import { apiGet, apiPost, ApiError } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import { Button } from '../components/Button'
import type {
  GradeAcceptedResponse,
  ProblemDetail,
  ProblemLevel,
} from '../types'

const DEFAULT_CODE = `# 표준 입력에서 읽어 표준 출력으로 결과를 출력하세요
# 예) n = int(input())
`

// schemas.py: GradeRequest.code 가 64 KB 캡
const MAX_CODE_LENGTH = 64 * 1024

const LEVEL_BADGE_STYLE: Record<ProblemLevel, string> = {
  bronze: 'bg-amber-100 text-amber-800 border border-amber-200',
  silver: 'bg-slate-100 text-slate-700 border border-slate-200',
  gold: 'bg-yellow-100 text-yellow-800 border border-yellow-300',
}

function getErrorDetail(err: ApiError): string {
  if (err.body && typeof err.body === 'object' && 'detail' in err.body) {
    return String((err.body as { detail: unknown }).detail)
  }
  return err.message
}

export function Solver() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { session } = useAuth()

  const [problem, setProblem] = useState<ProblemDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [code, setCode] = useState(DEFAULT_CODE)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    setLoadError(null)
    apiGet<ProblemDetail>(`/problems/${id}`)
      .then(setProblem)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setLoadError('문제를 찾을 수 없습니다.')
        } else {
          setLoadError(
            err instanceof Error ? err.message : 'unknown error',
          )
        }
      })
      .finally(() => setLoading(false))
  }, [id])

  const codeBytes = new TextEncoder().encode(code).length
  const overLimit = codeBytes > MAX_CODE_LENGTH

  const handleSubmit = async () => {
    if (!problem) return
    if (overLimit) {
      setSubmitError(
        `코드 크기가 너무 큽니다 (${codeBytes.toLocaleString()} > ${MAX_CODE_LENGTH.toLocaleString()} bytes)`,
      )
      return
    }
    setSubmitting(true)
    setSubmitError(null)
    try {
      const res = await apiPost<GradeAcceptedResponse>('/grade', {
        problem_id: problem.id,
        code,
      })
      navigate(`/submissions/${res.submission_id}`)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setSubmitError('로그인이 필요합니다. 다시 로그인 후 시도해주세요.')
        } else if (err.status === 409 || err.status === 429) {
          setSubmitError(getErrorDetail(err))
        } else if (err.status === 422) {
          setSubmitError(`입력 검증 실패 — ${getErrorDetail(err)}`)
        } else {
          setSubmitError(`${err.status} — ${getErrorDetail(err)}`)
        }
      } else {
        setSubmitError(err instanceof Error ? err.message : 'unknown error')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <main className="max-w-[1180px] mx-auto px-8 py-16 text-center text-gray-400 text-sm">
        문제를 불러오는 중...
      </main>
    )
  }
  if (loadError || !problem) {
    return (
      <main className="max-w-[1180px] mx-auto px-8 py-16 text-center text-red-500 text-sm">
        {loadError ?? '문제 로드 실패'}
      </main>
    )
  }

  return (
    <main className="max-w-[1380px] mx-auto w-full px-6 pt-6 pb-12 flex flex-col lg:flex-row gap-6 items-start">
      {/* 좌측: 문제 설명 */}
      <aside className="w-full lg:w-1/2 flex flex-col gap-4">
        <div className="bg-white border border-gray-200 rounded-2xl px-6 py-5 shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
          <div className="flex items-center gap-2 mb-3">
            <span
              className={`px-2 py-0.5 text-[11px] font-bold rounded-full ${LEVEL_BADGE_STYLE[problem.level]}`}
            >
              {problem.level.toUpperCase()}
            </span>
            <span className="text-xs text-gray-500 px-2 py-0.5 rounded-full bg-gray-100">
              {problem.category}
            </span>
            <span className="ml-auto text-xs font-bold text-brand tabular-nums">
              {problem.points} pt
            </span>
          </div>
          <h1 className="text-xl font-bold text-gray-800 leading-snug mb-1">
            {problem.title}
          </h1>
          <p className="text-[13px] text-gray-500 mb-4">
            {problem.one_line_summary}
          </p>
          <div className="flex gap-4 text-[11px] text-gray-500 border-t border-gray-100 pt-3 tabular-nums">
            <span>시간 제한 {problem.time_limit_ms} ms</span>
            <span>메모리 제한 {problem.memory_limit_mb} MB</span>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-2xl px-6 py-5 shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
          <h2 className="text-sm font-bold text-gray-800 mb-3">문제 설명</h2>
          <p className="text-[13.5px] text-gray-700 whitespace-pre-wrap leading-relaxed">
            {problem.statement}
          </p>
        </div>

        {problem.sample_test_cases.length > 0 && (
          <div className="bg-white border border-gray-200 rounded-2xl px-6 py-5 shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
            <h2 className="text-sm font-bold text-gray-800 mb-3">샘플 입출력</h2>
            <div className="flex flex-col gap-3">
              {problem.sample_test_cases.map((tc) => (
                <div key={tc.ordinal} className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="text-[10px] font-semibold text-gray-500 mb-1 tracking-wider">
                      INPUT #{tc.ordinal}
                    </div>
                    <pre className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-xs font-mono whitespace-pre overflow-x-auto">
                      {tc.stdin}
                    </pre>
                  </div>
                  <div>
                    <div className="text-[10px] font-semibold text-gray-500 mb-1 tracking-wider">
                      OUTPUT #{tc.ordinal}
                    </div>
                    <pre className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-xs font-mono whitespace-pre overflow-x-auto">
                      {tc.expected_stdout}
                    </pre>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </aside>

      {/* 우측: 에디터 */}
      <section className="w-full lg:w-1/2 flex flex-col gap-3 lg:sticky lg:top-4">
        <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-[0_1px_2px_rgba(31,41,55,0.03)]">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 bg-gray-50">
            <span className="text-xs font-bold text-gray-600">Python 3</span>
            <span
              className={`text-[10px] tabular-nums ${overLimit ? 'text-red-500 font-semibold' : 'text-gray-400'}`}
            >
              {codeBytes.toLocaleString()} / {MAX_CODE_LENGTH.toLocaleString()} bytes
            </span>
          </div>
          <Editor
            height="64vh"
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
          <div className="bg-red-50 border border-red-200 text-red-700 text-[13px] rounded-xl px-4 py-3">
            {submitError}
          </div>
        )}

        <div className="flex items-center justify-end gap-3">
          {!session && (
            <span className="text-xs text-gray-500">제출하려면 로그인이 필요합니다</span>
          )}
          <Button
            variant={session && !submitting && !overLimit ? 'primary' : 'disabled'}
            disabled={!session || submitting || overLimit}
            onClick={handleSubmit}
          >
            {submitting ? '제출 중...' : '제출하기'}
          </Button>
        </div>
      </section>
    </main>
  )
}
