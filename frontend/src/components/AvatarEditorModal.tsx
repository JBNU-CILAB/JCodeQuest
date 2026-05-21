import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { uploadAvatar, resetAvatar } from '../lib/avatar'

interface Props {
  open: boolean
  onClose: () => void
  currentUrl: string
  hasCustom: boolean
}

const MAX_BYTES = 2 * 1024 * 1024
const ALLOWED = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']

export function AvatarEditorModal({ open, onClose, currentUrl, hasCustom }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [busyKind, setBusyKind] = useState<'upload' | 'reset' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) return
    setFile(null)
    setError(null)
    setBusy(false)
    setBusyKind(null)
  }, [open])

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  if (!open) return null

  const handleFile = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    if (!ALLOWED.includes(f.type)) {
      setError('PNG/JPEG/WebP/GIF만 업로드할 수 있습니다.')
      return
    }
    if (f.size > MAX_BYTES) {
      setError('파일 크기는 2MB 이하여야 합니다.')
      return
    }
    setError(null)
    setFile(f)
  }

  const handleUpload = async () => {
    if (!file) return
    setBusy(true)
    setBusyKind('upload')
    setError(null)
    try {
      await uploadAvatar(file)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : '업로드 실패')
    } finally {
      setBusy(false)
      setBusyKind(null)
    }
  }

  const handleReset = async () => {
    setBusy(true)
    setBusyKind('reset')
    setError(null)
    try {
      await resetAvatar()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : '삭제 실패')
    } finally {
      setBusy(false)
      setBusyKind(null)
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose()
      }}
    >
      <div className="w-full max-w-md rounded-2xl bg-white shadow-xl">
        <div className="px-6 py-5 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-base font-bold text-gray-900">프로필 이미지 변경</h3>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="text-gray-400 hover:text-gray-700 text-xl leading-none disabled:opacity-40"
            aria-label="닫기"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-6">
          <div className="flex flex-col items-center gap-3">
            <img
              src={previewUrl ?? currentUrl}
              alt="프로필 미리보기"
              referrerPolicy="no-referrer"
              className="w-28 h-28 rounded-full border-2 border-black/10 object-cover bg-gray-50"
            />
            <p className="text-[11px] text-gray-500 text-center">
              PNG/JPEG/WebP/GIF · 최대 2MB
            </p>
          </div>

          <input
            ref={inputRef}
            type="file"
            accept={ALLOWED.join(',')}
            onChange={handleFile}
            className="hidden"
          />

          {error && (
            <p className="mt-4 text-xs text-red-600 text-center">{error}</p>
          )}

          <div className="mt-6 flex flex-col gap-2">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={busy}
              className="w-full rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
            >
              {file ? `다시 선택 · ${file.name}` : '이미지 선택'}
            </button>
            <button
              type="button"
              onClick={handleUpload}
              disabled={busy || !file}
              className="w-full rounded-md bg-gray-900 px-4 py-2 text-sm font-semibold text-white hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {busyKind === 'upload' ? '업로드 중…' : '업로드'}
            </button>
            {hasCustom && (
              <button
                type="button"
                onClick={handleReset}
                disabled={busy}
                className="w-full rounded-md bg-red-50 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-100 disabled:opacity-40"
              >
                {busyKind === 'reset' ? '삭제 중…' : '기본 이미지로 되돌리기'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
