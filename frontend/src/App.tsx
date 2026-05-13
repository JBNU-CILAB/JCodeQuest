import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from './lib/supabase'
import { Header } from './components/Header'
import { Hero } from './components/Hero'
import { Dashboard } from './components/Dashboard'

export default function App() {
  const [session, setSession] = useState<Session | null>(null)

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => setSession(session))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
    })
    return () => subscription.unsubscribe()
  }, [])

  return (
    <div className="min-h-full flex flex-col">
      <Header session={session} />
      <Hero session={session} />
      {session && <Dashboard />}

      <footer className="mt-auto p-6 text-center text-gray-400 text-xs">
        © 2026 JCodeQuest · 프로토타입
      </footer>
    </div>
  )
}
