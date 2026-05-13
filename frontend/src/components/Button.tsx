import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'outline' | 'ghost' | 'disabled'
type Size = 'md' | 'sm'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  children: ReactNode
}

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-brand text-white border border-transparent hover:bg-brand-dark',
  outline: 'bg-white text-brand border border-brand hover:bg-brand-soft',
  ghost: 'bg-transparent text-gray-500 border border-gray-200 hover:bg-gray-100',
  disabled: 'bg-gray-200 text-gray-400 border border-transparent cursor-default',
}
const SIZES: Record<Size, string> = {
  md: 'px-5 py-2.5 text-sm',
  sm: 'px-3.5 py-1.5 text-xs',
}

export function Button({ variant = 'primary', size = 'md', className = '', children, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      className={`inline-flex items-center justify-center gap-1.5 rounded-full font-semibold transition active:translate-y-px ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    >
      {children}
    </button>
  )
}
