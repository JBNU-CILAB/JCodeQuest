import { useLocation, useNavigate } from 'react-router-dom'
import { Hero } from '../components/Hero'
import { Dashboard } from '../components/Dashboard'
import { ApiKeyGuideModal } from '../components/ApiKeyGuideModal'
import { useAuth } from '../lib/AuthContext'
import { apiPut, ApiError } from '../lib/api'

export function Landing() {
  const { session, refreshProfile } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const apiKeyModalOpen = location.pathname === '/settings/api-key'

  const handleApiKeySubmit = async (apiKey: string) => {
    if (!session) {
      alert('로그인 후 다시 시도해주세요.')
      return
    }
    try {
      await apiPut('/me/api-key', { api_key: apiKey })
      await refreshProfile()
    } catch (err) {
      const detail = err instanceof ApiError ? err.message : String(err)
      alert(`API 키 저장 실패: ${detail}`)
      throw err
    }
  }

  return (
    <>
      <Hero />
      {session && <Dashboard />}
      <ApiKeyGuideModal
        open={apiKeyModalOpen}
        onClose={() => navigate('/', { replace: false })}
        onSubmit={handleApiKeySubmit}
      />
    </>
  )
}
