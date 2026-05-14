import { useEffect, useState } from 'react'
import { SlideModal } from './SlideModal'
import { supabase } from '../lib/supabase'

export interface ProfileMeta {
  grade?: number
  department?: string
  nickname?: string
  anonymous?: boolean
}

interface Props {
  open: boolean
  onClose: () => void
  initial?: ProfileMeta
}

type GradeValue = 1 | 2 | 3 | 4 | 5

const GRADE_LABEL: Record<GradeValue, string> = {
  1: '1학년',
  2: '2학년',
  3: '3학년',
  4: '4학년',
  5: '대학원',
}

export function ProfileSetupModal({ open, onClose, initial }: Props) {
  const [grade, setGrade] = useState<GradeValue | null>(null)
  const [department, setDepartment] = useState('')
  const [nickname, setNickname] = useState('')
  const [anonymous, setAnonymous] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setGrade((initial?.grade as GradeValue | undefined) ?? null)
    setDepartment(initial?.department ?? '')
    setNickname(initial?.nickname ?? '')
    setAnonymous(initial?.anonymous ?? true)
    setError(null)
    setSubmitting(false)
  }, [open, initial])

  const handleSubmit = async () => {
    if (!grade || !department.trim() || !nickname.trim()) {
      setError('모든 항목을 입력해주세요')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const { error: err } = await supabase.auth.updateUser({
        data: {
          grade,
          department: department.trim(),
          nickname: nickname.trim(),
          anonymous,
        },
      })
      if (err) throw err
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : '저장 실패')
    } finally {
      setSubmitting(false)
    }
  }

  const slides = [
    <div className="px-12 py-8" key="grade">
      <h3 className="text-lg font-bold text-gray-900 text-center">학년</h3>
      <p className="mt-2 text-sm text-gray-600 text-center">
        현재 재학 중인 학년을 선택해주세요
      </p>
      <div className="mt-6 grid grid-cols-2 gap-2">
        {(Object.keys(GRADE_LABEL) as unknown as string[])
          .map((k) => Number(k) as GradeValue)
          .map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGrade(g)}
              className={`px-4 py-2.5 rounded-md border text-sm font-medium transition ${
                grade === g
                  ? 'bg-gray-900 text-white border-gray-900'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
              }`}
            >
              {GRADE_LABEL[g]}
            </button>
          ))}
      </div>
    </div>,

    <div className="px-12 py-8" key="dept">
      <h3 className="text-lg font-bold text-gray-900 text-center">학과</h3>
      <p className="mt-2 text-sm text-gray-600 text-center">
        소속 학과를 입력해주세요
      </p>
      <input
        type="text"
        value={department}
        onChange={(e) => setDepartment(e.target.value)}
        placeholder="예: 컴퓨터공학부"
        className="mt-6 w-full rounded-md border border-black/10 bg-white px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-800/30 focus:border-gray-800/40"
      />
    </div>,

    <div className="px-12 py-8" key="nick">
      <h3 className="text-lg font-bold text-gray-900 text-center">닉네임</h3>
      <p className="mt-2 text-sm text-gray-600 text-center">
        랭킹 및 프로필에 표시될 이름을 정해주세요
      </p>
      <input
        type="text"
        value={nickname}
        onChange={(e) => setNickname(e.target.value)}
        placeholder="닉네임"
        className="mt-6 w-full rounded-md border border-black/10 bg-white px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-800/30 focus:border-gray-800/40"
      />
      <label className="mt-4 flex items-start gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={anonymous}
          onChange={(e) => setAnonymous(e.target.checked)}
          className="mt-0.5 w-4 h-4 rounded border-gray-300 text-gray-900 focus:ring-gray-800/30"
        />
        <span className="text-sm text-gray-700 leading-snug">
          닉네임으로 표시{' '}
          <span className="text-gray-400">(해제 시 실명이 노출됩니다)</span>
        </span>
      </label>
    </div>,

    <div className="px-12 py-8" key="confirm">
      <h3 className="text-lg font-bold text-gray-900 text-center">확인</h3>
      <p className="mt-2 text-sm text-gray-600 text-center">
        입력한 내용을 확인하고 저장해주세요
      </p>
      <div className="mt-6 grid grid-cols-[80px_1fr] gap-x-4 gap-y-3 text-sm">
        <span className="text-gray-500">학년</span>
        <span className="text-gray-900">
          {grade ? GRADE_LABEL[grade] : '-'}
        </span>
        <span className="text-gray-500">학과</span>
        <span className="text-gray-900">{department || '-'}</span>
        <span className="text-gray-500">닉네임</span>
        <span className="text-gray-900">{nickname || '-'}</span>
        <span className="text-gray-500">표시</span>
        <span className="text-gray-900">
          {anonymous ? '닉네임' : '실명'}
        </span>
      </div>
      {error && (
        <p className="mt-4 text-sm text-red-600 text-center">{error}</p>
      )}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={submitting}
        className="mt-6 w-full rounded-md bg-gray-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition"
      >
        {submitting ? '저장 중…' : '저장하기'}
      </button>
    </div>,
  ]

  return (
    <SlideModal
      open={open}
      onClose={onClose}
      title="프로필 설정"
      slides={slides}
    />
  )
}
