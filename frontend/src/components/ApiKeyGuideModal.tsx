import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

interface Slide {
  title: string
  description: string
  image: string
}

const SLIDES: Slide[] = [
  {
    title: '1. OpenAI 콘솔 접속',
    description: 'platform.openai.com에 로그인하고 우측 상단 프로필 메뉴를 엽니다.',
    image: '/guide/api-key/step1.png',
  },
  {
    title: '2. API Keys 메뉴 이동',
    description: '"View API keys" 항목을 선택해 키 관리 페이지로 이동합니다.',
    image: '/guide/api-key/step2.png',
  },
  {
    title: '3. 새 시크릿 키 생성',
    description: '"Create new secret key" 버튼을 눌러 키를 발급받고 복사합니다.',
    image: '/guide/api-key/step3.png',
  },
  {
    title: '4. JCodeQuest에 등록',
    description: '복사한 키를 입력란에 붙여넣고 저장하면 AI 튜터가 활성화됩니다.',
    image: '/guide/api-key/step4.png',
  },
]

interface Props {
  open: boolean
  onClose: () => void
}

export function ApiKeyGuideModal({ open, onClose }: Props) {
  const [index, setIndex] = useState(0)
  const total = SLIDES.length

  const goPrev = useCallback(
    () => setIndex((i) => Math.max(0, i - 1)),
    [],
  )
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
      aria-labelledby="api-key-guide-title"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-[640px] bg-white rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-black/10">
          <h2
            id="api-key-guide-title"
            className="text-base font-semibold text-gray-900"
          >
            API 키 등록 가이드
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="w-8 h-8 rounded-full hover:bg-black/5 flex items-center justify-center text-gray-500 hover:text-gray-900 transition"
          >
            ✕
          </button>
        </div>

        {/* Slide track */}
        <div className="relative">
          <div className="overflow-hidden">
            <div
              className="flex transition-transform duration-300 ease-out"
              style={{ transform: `translateX(-${index * 100}%)` }}
            >
              {SLIDES.map((slide, i) => (
                <SlidePanel key={i} slide={slide} />
              ))}
            </div>
          </div>

          {/* Prev / Next */}
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

        {/* Footer (dots + counter) */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-black/10 bg-gray-50/50">
          <div className="flex items-center gap-1.5">
            {SLIDES.map((_, i) => (
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

function SlidePanel({ slide }: { slide: Slide }) {
  const [errored, setErrored] = useState(false)
  return (
    <div className="w-full shrink-0 px-12 py-6">
      <div className="aspect-[16/9] w-full bg-gray-50 border border-black/5 rounded-lg overflow-hidden flex items-center justify-center">
        {errored ? (
          <div className="flex flex-col items-center gap-1 text-gray-400 text-sm">
            <span className="text-2xl">🖼️</span>
            이미지 준비 중
          </div>
        ) : (
          <img
            src={slide.image}
            alt={slide.title}
            className="w-full h-full object-contain"
            onError={() => setErrored(true)}
          />
        )}
      </div>
      <div className="mt-5 text-center">
        <h3 className="text-lg font-bold text-gray-900">{slide.title}</h3>
        <p className="mt-2 text-sm text-gray-600 leading-relaxed">
          {slide.description}
        </p>
      </div>
    </div>
  )
}
