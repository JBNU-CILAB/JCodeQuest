import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  open: boolean
  onClose: () => void
  title: string
  slides: ReactNode[]
}

export function SlideModal({ open, onClose, title, slides }: Props) {
  const [index, setIndex] = useState(0)
  const total = slides.length

  const goPrev = useCallback(() => setIndex((i) => Math.max(0, i - 1)), [])
  const goNext = useCallback(
    () => setIndex((i) => Math.min(total - 1, i + 1)),
    [total],
  )

  useEffect(() => {
    if (!open) {
      setIndex(0)
      return
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft') goPrev()
      else if (e.key === 'ArrowRight') goNext()
    }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [open, onClose, goPrev, goNext])

  if (!open) return null

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-[640px] bg-white rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-black/10">
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="w-8 h-8 rounded-full hover:bg-black/5 flex items-center justify-center text-gray-500 hover:text-gray-900 transition"
          >
            ✕
          </button>
        </div>

        <div className="relative">
          <div className="overflow-hidden">
            <div
              className="flex transition-transform duration-300 ease-out"
              style={{ transform: `translateX(-${index * 100}%)` }}
            >
              {slides.map((node, i) => (
                <div key={i} className="w-full shrink-0">
                  {node}
                </div>
              ))}
            </div>
          </div>

          <button
            type="button"
            onClick={goPrev}
            disabled={index === 0}
            aria-label="이전"
            className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-white border border-black/10 shadow-md text-gray-700 flex items-center justify-center text-2xl leading-none hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition"
          >
            ‹
          </button>
          <button
            type="button"
            onClick={goNext}
            disabled={index === total - 1}
            aria-label="다음"
            className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-white border border-black/10 shadow-md text-gray-700 flex items-center justify-center text-2xl leading-none hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed transition"
          >
            ›
          </button>
        </div>

        <div className="flex items-center justify-between px-6 py-4 border-t border-black/10 bg-gray-50/50">
          <div className="flex items-center gap-1.5">
            {slides.map((_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setIndex(i)}
                aria-label={`${i + 1}번째 슬라이드로 이동`}
                className={`h-2 rounded-full transition-all ${
                  i === index
                    ? 'w-5 bg-gray-800'
                    : 'w-2 bg-gray-300 hover:bg-gray-400'
                }`}
              />
            ))}
          </div>
          <div className="text-xs text-gray-400 tabular-nums">
            {index + 1} / {total}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
