import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, Link } from 'react-router-dom'
import { Shield, UserRound } from 'lucide-react'
import { useAuth } from '../auth'
import { supabase } from '../lib/supabase'
import { api } from '../lib/api'
import { useClimate } from '../context'
import { Panel, SectionHeading } from '../components/Shared'
import { Button } from '../components/ui/button'

export function RequireAuth({ children, authority = false, allowDemo = false }: { children: React.ReactNode; authority?: boolean; allowDemo?: boolean }) {
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

export function LoginPage() {
  const [mode, setMode] = useState<'login' | 'signup' | 'recover'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const { session, configured } = useAuth()
  const location = useLocation()
  if (session) return <Navigate to={(location.state as { from?: string } | null)?.from ?? '/citizen'} replace/>
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!supabase) return
    setBusy(true); setMessage('')
    if (mode === 'recover') {
      const result = await supabase.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/reset-password` })
      setBusy(false)
      setMessage(result.error?.message ?? 'If this account exists, a recovery link has been sent. Check your email.')
      return
    }
    const result = mode === 'login' ? await supabase.auth.signInWithPassword({ email, password }) : await supabase.auth.signUp({ email, password })
    setBusy(false)
    if (result.error) setMessage(result.error.message)
    else if (mode === 'signup' && !result.data.session) setMessage('Account created. Check your email to confirm your address before signing in.')
  }
  return <div className="login-layout"><div className="login-brand"><span className="brand-symbol"><Shield size={22}/></span><strong>CLIMAGUARD AI</strong><h1>Predict Earlier.<br/>Decide Faster.<br/>Protect More.</h1><p>Climate intelligence for safer local decisions.</p></div><Panel className="login-card"><span className="eyebrow">SECURE ACCESS</span><h2>{mode === 'login' ? 'Welcome back' : mode === 'recover' ? 'Recover access' : 'Create your account'}</h2><p>{mode === 'login' ? 'Sign in to manage reports and access your workspace.' : mode === 'recover' ? 'Request a password reset link for your account.' : 'New accounts start with citizen access.'}</p>{configured ? <form className="incident-form" onSubmit={submit}><label>Email<input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required/></label>{mode !== 'recover' && <label>Password<input type="password" minLength={6} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={e => setPassword(e.target.value)} required/></label>}<Button type="submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : mode === 'recover' ? 'Send recovery link' : 'Create citizen account'}</Button>{message && <p role="status" className={message.includes('sent') || message.includes('created') ? 'form-success' : 'form-error'}>{message}</p>}</form> : <p className="form-error">Supabase Auth is not configured. Add the browser environment variables first.</p>}<button className="auth-toggle" onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setMessage('') }}>{mode === 'login' ? 'New here? Create an account' : 'Already have an account? Sign in'}</button><button className="auth-toggle" onClick={() => { setMode('recover'); setMessage('') }}>Forgot password?</button><Link className="text-link" to="/citizen">Explore the citizen demo →</Link></Panel></div>
}

export function ResetPasswordPage() {
  const { session, loading } = useAuth()
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const submit = async (event: FormEvent) => { event.preventDefault(); if (!supabase) return; setBusy(true); const result = await supabase.auth.updateUser({ password }); setBusy(false); setMessage(result.error?.message ?? 'Password updated. You can return to your account.') }
  return <div className="login-layout"><Panel className="login-card"><h1>Set a new password</h1>{loading ? <p>Checking recovery link…</p> : !session ? <p>Open the valid recovery link from your email, or request a new one from the sign-in page.</p> : <form className="incident-form" onSubmit={submit}><label>New password<input type="password" minLength={8} required autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)}/></label><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Update password'}</Button>{message && <p role="status">{message}</p>}</form>}<Link to="/login" className="text-link">Return to sign in</Link></Panel></div>
}

export function ProfilePage() {
  const { profile, refreshProfile, session } = useAuth()
  const [name, setName] = useState(profile?.display_name ?? '')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async (event: FormEvent) => { event.preventDefault(); setBusy(true); try { await api.updateProfile(name.trim()); await refreshProfile(); setMessage('Profile updated.') } catch (error) { setMessage(error instanceof Error ? error.message : 'Update failed.') } finally { setBusy(false) } }
  return <div className="profile-layout"><div className="page-intro"><span className="eyebrow">YOUR ACCOUNT</span><h1>Profile</h1><p>Manage your display name and view your verified role.</p></div><Panel><SectionHeading title="Account details"/><div className="profile-identity"><UserRound size={20}/><div><strong>{session?.user.email}</strong><span>{profile?.role ?? 'Loading role'}</span></div></div><form className="incident-form" onSubmit={save}><label>Display name<input maxLength={120} value={name} onChange={e => setName(e.target.value)} placeholder="Your name"/></label><Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save profile'}</Button>{message && <p role="status" className="form-success">{message}</p>}</form><p className="disclaimer">Authority and admin roles can only be assigned by an administrator.</p></Panel></div>
}
