import { useCallback, useEffect, useState } from 'react'
import { SlideModal } from './SlideModal'

interface Slide {
  title: string
  description: string
  image: string
}

const SLIDES: Slide[] = [
  {
    title: '1. 교내 AI 서비스 이용하기!',
    description: 'https://gpt.jbnu.ai/에 접속하여 로그인 해주세요!',
    image: '/guide/api-key/step1.png',
  },
  {
    title: '2. API GateWay 클릭!',
    description: '화면 좌측 하단에 API GateWay를 클릭해주세요!',
    image: '/guide/api-key/step2.png',
  },
  {
    title: '3. 새 API 키 생성!',
    description: '"API 키 생성"을 클릭하면 본인의 API 키를 생성해주세요!',
    image: '/guide/api-key/step3.png',
  },
  {
    title: '4. 생성된 API 키 복사',
    description:
      '복사한 키는 "복사 완료" 버튼을 누른 이후 재확인이 불가하니 반드시 "복사"버튼을 눌러 복사해주시길 바랍니다.',
    image: '/guide/api-key/step4.png',
  },
  {
    title: '5. J-CodeQueset 튜터에 등록',
    description: '복사한 API키를 J-CodeQuest 튜터에 등록합니다.',
    image: '/guide/api-key/step4.png',
  },
]

// 백엔드 schemas._API_KEY_PATTERN과 동일 — 공백/개행 없는 인쇄 가능 ASCII 20–512자.
const API_KEY_PATTERN = /^[!-~]{20,512}$/

function validateApiKey(raw: string): string | null {
  if (!raw) return null
  if (raw.length < 20) return '20자 이상 입력해주세요.'
  if (raw.length > 512) return '512자를 넘을 수 없습니다.'
  if (!API_KEY_PATTERN.test(raw))
    return '공백·개행 없이 영문/숫자/기호로만 입력해주세요.'
  return null
}

interface Props {
  open: boolean
  onClose: () => void
  onSubmit?: (apiKey: string) => Promise<void> | void
}

export function ApiKeyGuideModal({ open, onClose, onSubmit }: Props) {
  const [apiKey, setApiKey] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) {
      setApiKey('')
      setSubmitting(false)
    }
  }, [open])

  const handleSubmit = useCallback(async () => {
    const trimmed = apiKey.trim()
    if (!trimmed || submitting) return
    if (validateApiKey(trimmed) !== null) return
    try {
      setSubmitting(true)
      await onSubmit?.(trimmed)
      setApiKey('')
      onClose()
    } finally {
      setSubmitting(false)
    }
  }, [apiKey, submitting, onSubmit, onClose])

  const slides = SLIDES.map((slide, i) => (
    <SlidePanel
      key={i}
      slide={slide}
      isApiKeyStep={i === SLIDES.length - 1}
      apiKey={apiKey}
      onApiKeyChange={setApiKey}
      onSubmit={handleSubmit}
      submitting={submitting}
    />
  ))

  return (
    <SlideModal
      open={open}
      onClose={onClose}
      title="API 키 등록 가이드"
      slides={slides}
    />
  )
}

interface SlidePanelProps {
  slide: Slide
  isApiKeyStep: boolean
  apiKey: string
  onApiKeyChange: (value: string) => void
  onSubmit: () => void
  submitting: boolean
}

function SlidePanel({
  slide,
  isApiKeyStep,
  apiKey,
  onApiKeyChange,
  onSubmit,
  submitting,
}: SlidePanelProps) {
  const [errored, setErrored] = useState(false)
  return (
    <div className="px-12 py-6">
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
      {isApiKeyStep && (
        <>
          <form
            className="mt-4 flex items-stretch gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              onSubmit()
            }}
          >
            <input
              type="password"
              value={apiKey}
              onChange={(e) => onApiKeyChange(e.target.value)}
              placeholder="API 키를 붙여넣어 주세요"
              autoComplete="off"
              spellCheck={false}
              aria-invalid={validateApiKey(apiKey.trim()) !== null}
              className="flex-1 min-w-0 rounded-md border border-black/10 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-800/30 focus:border-gray-800/40"
            />
            <button
              type="submit"
              disabled={
                !apiKey.trim() ||
                submitting ||
                validateApiKey(apiKey.trim()) !== null
              }
              className="shrink-0 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              {submitting ? '저장 중…' : '저장'}
            </button>
          </form>
          {validateApiKey(apiKey.trim()) && (
            <p className="mt-1 text-xs text-red-600">
              {validateApiKey(apiKey.trim())}
            </p>
          )}
        </>
      )}
    </div>
  )
}
