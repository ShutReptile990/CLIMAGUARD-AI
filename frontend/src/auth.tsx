import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase, authConfigured } from './lib/supabase'
import { api } from './lib/api'
import { useQueryClient } from '@tanstack/react-query'

export type Profile = { id: string; display_name: string | null; role: 'citizen' | 'authority' | 'admin'; created_at: string; updated_at: string }
type AuthContextValue = { session: Session | null; profile: Profile | null; loading: boolean; profileError: string | null; configured: boolean; refreshProfile: () => Promise<void>; signOut: () => Promise<void> }
const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [session, setSession] = useState<Session | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(authConfigured)
  const [profileError, setProfileError] = useState<string | null>(null)
  const refreshProfile = async () => {
    if (!supabase) return
    const { data } = await supabase.auth.getSession()
    if (!data.session) { setSession(null); setProfile(null); setProfileError(null); return }
    try { setProfile(await api.profile()); setProfileError(null) }
    catch (error) { setProfile(null); setProfileError(error instanceof Error ? error.message : 'Profile unavailable') }
  }
  useEffect(() => {
    if (!supabase) return
    let active = true
    void supabase.auth.getSession().then(async ({ data, error }) => { if (!active) return; setSession(error ? null : data.session); if (!error && data.session) await refreshProfile(); if (active) setLoading(false) }).catch(() => { if (active) { setSession(null); setProfile(null); setLoading(false) } })
    const { data: listener } = supabase.auth.onAuthStateChange((event, current) => {
      if (!active) return
      if (event === 'SIGNED_IN' || event === 'SIGNED_OUT') queryClient.clear()
      setSession(current)
      if (current) { window.setTimeout(() => { if (active) void refreshProfile() }, 0) }
      else { setProfile(null); setProfileError(null) }
    })
    return () => { active = false; listener.subscription.unsubscribe() }
  }, [])
  const signOut = async () => { await supabase?.auth.signOut(); queryClient.clear(); setSession(null); setProfile(null) }
  return <AuthContext.Provider value={{ session, profile, loading, profileError, configured: authConfigured, refreshProfile, signOut }}>{children}</AuthContext.Provider>
}
export function useAuth() { const value = useContext(AuthContext); if (!value) throw new Error('AuthProvider missing'); return value }
