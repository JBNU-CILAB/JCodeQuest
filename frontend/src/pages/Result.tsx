import { useParams } from 'react-router-dom'

export function Result() {
  const { id } = useParams<{ id: string }>()
  return (
    <main className="max-w-[1180px] mx-auto w-full px-8 pt-8 pb-20">
      <h1 className="text-2xl font-bold text-gray-800">제출 #{id}</h1>
      <p className="mt-2 text-sm text-gray-500">Phase 5에서 구현 예정 — SSE /grade/{'{id}'}/events + GET /grade/{'{id}'} + 튜터 패널</p>
    </main>
  )
}
