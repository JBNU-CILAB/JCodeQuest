import { useLocation, useNavigate } from 'react-router-dom'
import { Hero } from '../components/Hero'
import { Dashboard } from '../components/Dashboard'
import { ApiKeyGuideModal } from '../components/ApiKeyGuideModal'
import { useAuth } from '../lib/AuthContext'

export function Landing() {
  const { session } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const apiKeyModalOpen = location.pathname === '/settings/api-key'

  return (
    <>
      <Hero />
      {session && <Dashboard />}
      <ApiKeyGuideModal
        open={apiKeyModalOpen}
        onClose={() => navigate('/', { replace: false })}
      />
    </>
  )
}
