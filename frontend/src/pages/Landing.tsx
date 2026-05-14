import { Hero } from '../components/Hero'
import { Dashboard } from '../components/Dashboard'
import { useAuth } from '../lib/AuthContext'

export function Landing() {
  const { session } = useAuth()
  return (
    <>
      <Hero />
      {session && <Dashboard />}
    </>
  )
}
