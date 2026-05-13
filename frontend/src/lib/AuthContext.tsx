import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from './supabase'
import { apiGet, ApiError } from './api'
import type { UserMe } from '../types'

interface AuthContextValue {
  session: Session | null
  profile: UserMe | null
  loading: boolean
  profileError: string | null
  refreshProfile: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue>({
  session: null,
  profile: null,
  loading: true,
  profileError: null,
  refreshProfile: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [profile, setProfile] = useState<UserMe | null>(null)
  const [loading, setLoading] = useState(true)
  const [profileError, setProfileError] = useState<string | null>(null)

  const fetchProfile = async () => {
    try {
      const me = await apiGet<UserMe>('/me')
      setProfile(me)
      setProfileError(null)
    } catch (err) {
      setProfile(null)
      if (err instanceof ApiError) {
        setProfileError(`/me ${err.status}`)
      } else {
        setProfileError(err instanceof Error ? err.message : 'unknown error')
      }
    }
  }

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      setLoading(false)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => setSession(session),
    )
    return () => subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (session) {
      void fetchProfile()
    } else {
      setProfile(null)
      setProfileError(null)
    }
  }, [session?.access_token])

  return (
    <AuthContext.Provider
      value={{ session, profile, loading, profileError, refreshProfile: fetchProfile }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
