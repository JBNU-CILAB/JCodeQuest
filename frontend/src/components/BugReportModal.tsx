import { useEffect, useState } from 'react'
import type { ProblemLevel } from '../types'

export type BugReportCategory =
  | 'judging'
  | 'statement'
  | 'sample'
  | 'system'
  | 'other'

export interface BugReportPayload {
  category: BugReportCategory
  title: string
  body: string
  includeCode: boolean
}

interface ProblemContext {
  id: number
  title: string
  level: ProblemLevel
}

interface BugReportModalProps {
  open: boolean
  onClose: () => void
  onSubmit: (payload: BugReportPayload) => void
  problem?: ProblemContext | null
}

const CATEGORIES: Array<{ v: BugReportCategory; label: string }> = [
  { v: 'judging', label: '채점 오류' },
  { v: 'statement', label: '문제 오타' },
  { v: 'sample', label: '예제 이상' },
  { v: 'system', label: '시스템 / UI' },
  { v: 'other', label: '기타' },
]

export function BugReportModal({
  open,
  onClose,
  onSubmit,
  problem,
}: BugReportModalProps) {
  const [category, setCategory] = useState<BugReportCategory>('judging')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [includeCode, setIncludeCode] = useState(true)

  useEffect(() => {
    if (open) {
      setCategory('judging')
      setTitle('')
      setBody('')
      setIncludeCode(true)
    }
  }, [open])

  if (!open) return null

  const canSubmit = title.trim().length >= 4 && body.trim().length >= 10

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center px-4"
      style={{
        background: 'rgba(15, 23, 42, 0.45)',
        animation: 'modal-fade-in 0.18s ease-out',
      }}
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-label="버그 제보"
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-[18px] p-7 w-full max-w-[560px] shadow-[0_20px_60px_rgba(0,0,0,0.25)]"
        style={{ animation: 'modal-pop-in 0.22s var(--ease-out-cubic)' }}
      >
        <div className="flex items-start gap-3 mb-4">
          <div
            className="flex items-center justify-center text-lg shrink-0"
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: '#fef2f2',
              color: '#b91c1c',
            }}
          >
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-extrabold m-0">버그 제보</h2>
            <p className="text-[13px] text-gray-500 mt-1 leading-relaxed">
              문제 / 채점 / 시스템에서 발견한 이상한 점을 알려주세요. 운영진에게
              바로 전달됩니다.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="닫기"
            type="button"
            className="bg-transparent border-0 text-2xl text-gray-500 leading-none p-1 cursor-pointer hover:text-gray-800 transition"
          >
            ×
          </button>
        </div>

        {problem && (
          <div
            className="flex gap-2 items-center px-3 py-2 rounded-[10px] text-[12px] text-gray-700 mb-3.5"
            style={{
              background: '#f9fafb',
              fontFamily: 'NeoDunggeunmo, monospace',
            }}
          >
            <span className="text-brand-dark">#{problem.id}</span>
            <span>{problem.title}</span>
            <span className="ml-auto text-gray-500 uppercase">
              {problem.level}
            </span>
          </div>
        )}

        <label className="text-[12px] font-bold text-gray-700 block mb-1.5">
          유형
        </label>
        <div className="flex gap-1.5 mb-4 flex-wrap">
          {CATEGORIES.map((c) => {
            const active = category === c.v
            return (
              <button
                key={c.v}
                type="button"
                onClick={() => setCategory(c.v)}
                className={`px-3 py-1.5 rounded-full text-[12px] font-semibold border transition ${
                  active
                    ? 'border-brand bg-brand-soft text-brand-dark'
                    : 'border-line bg-white text-gray-500 hover:text-gray-800'
                }`}
              >
                {c.label}
              </button>
            )
          })}
        </div>

        <label className="text-[12px] font-bold text-gray-700 block mb-1.5">
          제목{' '}
          <span className="text-gray-400 font-normal">(짧게)</span>
        </label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="예: 예제 2번 출력 형식이 설명과 달라요"
          className="w-full px-3.5 py-2.5 border border-line rounded-[10px] text-sm bg-white mb-3.5 focus:outline-none focus:border-brand"
        />

        <label className="text-[12px] font-bold text-gray-700 block mb-1.5">
          상세 내용{' '}
          <span className="text-gray-400 font-normal">
            (어떻게 재현되는지)
          </span>
        </label>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={[
            '1. 어떤 입력을 넣었는지',
            '2. 기대한 출력 / 실제 출력',
            '3. 언제부터 발생했는지',
          ].join('\n')}
          rows={5}
          className="w-full px-3.5 py-2.5 border border-line rounded-[10px] text-[13px] leading-relaxed mb-3 resize-y bg-white focus:outline-none focus:border-brand"
          style={{
            fontFamily: 'NeoDunggeunmo, monospace',
            minHeight: 120,
          }}
        />

        <label className="flex items-center gap-2 text-[13px] text-gray-700 cursor-pointer">
          <input
            type="checkbox"
            checked={includeCode}
            onChange={(e) => setIncludeCode(e.target.checked)}
            style={{ accentColor: 'var(--color-brand)' }}
          />
          현재 작성 중인 코드와 마지막 제출 결과를 첨부
        </label>

        <div className="flex gap-2.5 mt-5 justify-end">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center justify-center gap-1.5 px-5 py-2.5 text-sm font-semibold rounded-full bg-white border border-line text-gray-800 hover:border-gray-400 transition active:translate-y-px"
          >
            취소
          </button>
          <button
            type="button"
            disabled={!canSubmit}
            onClick={() =>
              onSubmit({ category, title, body, includeCode })
            }
            className={`inline-flex items-center justify-center gap-1.5 px-5 py-2.5 text-sm font-semibold rounded-full text-white transition active:translate-y-px ${
              canSubmit
                ? 'bg-brand hover:bg-brand-dark cursor-pointer'
                : 'bg-gray-300 cursor-not-allowed'
            }`}
          >
            제보 보내기
          </button>
        </div>
      </div>
    </div>
  )
}
