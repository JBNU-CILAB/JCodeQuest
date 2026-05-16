import { createPortal } from 'react-dom'

interface Props {
  open: boolean
  onClose: () => void
  onSetupProfile: () => void
}

export function ProfileRequiredModal({ open, onClose, onSetupProfile }: Props) {
  if (!open) return null

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-[420px] bg-white rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-black/10">
          <h2 className="text-base font-semibold text-gray-900">프로필 설정 필요</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="w-8 h-8 rounded-full hover:bg-black/5 flex items-center justify-center text-gray-500 hover:text-gray-900 transition"
          >
            ✕
          </button>
        </div>

        <div className="px-6 py-6">
          <p className="text-sm text-gray-700 leading-relaxed mb-2">
            프로필 설정 이후 이용해주세요!
          </p>
          <p className="text-[13px] text-gray-600 leading-relaxed mb-6">
            학년, 학과, 닉네임 정보를 완성하면 문제를 풀 수 있습니다.
          </p>

          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-md bg-gray-100 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-200 transition"
            >
              닫기
            </button>
            <button
              type="button"
              onClick={onSetupProfile}
              className="flex-1 rounded-md bg-gray-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-gray-800 transition"
            >
              프로필 등록하기
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
