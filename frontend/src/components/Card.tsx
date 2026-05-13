import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
}

export function Card({ children, className = '' }: CardProps) {
  return (
    <div className={`bg-white border border-gray-200 rounded-2xl px-6 py-5 shadow-[0_1px_2px_rgba(31,41,55,0.03)] ${className}`}>
      {children}
    </div>
  )
}

interface CardHeadProps {
  icon?: ReactNode
  title: string
  right?: ReactNode
}

export function CardHead({ icon, title, right }: CardHeadProps) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-2 text-[15px] font-bold text-gray-800">
        {icon && <span className="text-gray-400 text-base">{icon}</span>}
        <span>{title}</span>
      </div>
      {right}
    </div>
  )
}
