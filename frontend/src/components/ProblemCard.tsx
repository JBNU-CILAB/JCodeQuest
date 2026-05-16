import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext'
import { ProfileRequiredModal } from './ProfileRequiredModal'
import type { ProblemSummary, ProblemLevel } from '../types'

const LEVEL_BADGE_STYLE: Record<ProblemLevel, string> = {
  bronze: 'bg-amber-100 text-amber-800 border border-amber-200',
  silver: 'bg-slate-100 text-slate-700 border border-slate-200',
  gold: 'bg-yellow-100 text-yellow-800 border border-yellow-300',
}

const LEVEL_LABEL: Record<ProblemLevel, string> = {
  bronze: 'Bronze',
  silver: 'Silver',
  gold: 'Gold',
}

interface ProblemCardProps {
  problem: ProblemSummary
  onProfileRequired?: () => void
}

export function ProblemCard({ problem, onProfileRequired }: ProblemCardProps) {
  const navigate = useNavigate()
  const { session } = useAuth()
  const [showProfileRequired, setShowProfileRequired] = useState(false)

  const metadata = (session?.user.user_metadata ?? {}) as {
    grade?: number
    department?: string
    nickname?: string
    anonymous?: boolean
  }

  const hasCompleteProfile =
    session &&
    metadata.grade &&
    metadata.department &&
    metadata.nickname &&
    typeof metadata.anonymous === 'boolean'

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault()

    if (!session) {
      navigate(`/problems/${problem.id}`)
      return
    }

    if (!hasCompleteProfile) {
      setShowProfileRequired(true)
      return
    }

    navigate(`/problems/${problem.id}`)
  }

  return (
    <>
      <button
        onClick={handleClick}
        className="group flex flex-col bg-white border border-gray-200 rounded-2xl px-5 py-4 shadow-[0_1px_2px_rgba(31,41,55,0.03)] hover:shadow-md hover:border-brand/40 transition text-left w-full"
      >
      <div className="flex items-center gap-2 mb-3">
        <span
          className={`px-2 py-0.5 text-[11px] font-bold rounded-full ${LEVEL_BADGE_STYLE[problem.level]}`}
        >
          {LEVEL_LABEL[problem.level]}
        </span>
        <span className="text-[11px] text-gray-500 px-2 py-0.5 rounded-full bg-gray-100">
          {problem.category}
        </span>
        <span className="ml-auto text-xs font-bold text-brand tabular-nums">
          {problem.points} pt
        </span>
      </div>

      <h3 className="text-[15px] font-bold text-gray-800 leading-snug mb-1.5 group-hover:text-brand-dark transition">
        {problem.title}
      </h3>
      <p className="text-[12.5px] text-gray-500 leading-relaxed line-clamp-2">
        {problem.one_line_summary}
      </p>
      </button>

      <ProfileRequiredModal
        open={showProfileRequired}
        onClose={() => setShowProfileRequired(false)}
        onSetupProfile={() => {
          setShowProfileRequired(false)
          onProfileRequired?.()
        }}
      />
    </>
  )
}
