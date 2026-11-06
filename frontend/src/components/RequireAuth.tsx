import type { ReactNode } from 'react'
import { Navigate, useLocation, Link } from 'react-router-dom'
import { Shield } from 'lucide-react'
import { useAuth } from '../auth'
import { useClimate } from '../context'
import { Button } from './ui/button'

export function RequireAuth({ children, authority = false, allowDemo = false }: { children: ReactNode; authority?: boolean; allowDemo?: boolean }) {
  const { session, profile, loading, profileError, configured } = useAuth()
  const { demo } = useClimate()
  const location = useLocation()
  if (allowDemo && demo) return <>{children}</>
  if (!configured) return <AccountState title="Authentication not configured" detail="Set the Supabase browser variables to enable protected routes."/>
  if (loading) return <AccountState title="Checking your session" detail="Please wait while your account is verified."/>
  if (!session) return <Navigate to="/login" state={{ from: location.pathname }} replace/>
  if (profileError) return <AccountState title="Profile unavailable" detail={profileError}/>
  if (!profile) return <AccountState title="Loading your profile" detail="Your account role is being checked."/>
  if (authority && !['authority', 'admin'].includes(profile.role)) return <AccountState title="Authority access required" detail="This workspace is available to authorized responders only."/>
  return <>{children}</>
}

function AccountState({ title, detail }: { title: string; detail: string }) { return <div className="account-state"><span className="brand-symbol"><Shield size={22}/></span><h1>{title}</h1><p>{detail}</p><Button asChild variant="outline"><Link to="/citizen">Return to citizen portal</Link></Button></div> }
