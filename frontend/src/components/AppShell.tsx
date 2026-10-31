import { Activity, ArrowLeftRight, Bell, BookOpen, Building2, ChartNoAxesCombined, CircleAlert, ClipboardList, CloudSun, Command, FileClock, FileText, House, LogOut, Map, Menu, Send, Shield, ShieldCheck, Sparkles, Target, UserRound, UsersRound, X } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import type { Locality } from '../types'
import { LocalitySelector } from './Shared'
import { useClimate } from '../context'
import { Button } from './ui/button'
import { useAuth } from '../auth'
const citizenNav = [
  { to: '/citizen', label: 'Overview', icon: House, end: true }, { to: '/citizen/map', label: 'Risk Map', icon: Map },
  { to: '/citizen/predictions', label: 'Predictions', icon: ChartNoAxesCombined }, { to: '/citizen/safety', label: 'Safety Center', icon: ShieldCheck },
  { to: '/citizen/report', label: 'Report Incident', icon: Send }, { to: '/citizen/reports', label: 'My Reports', icon: FileText },
  { to: '/citizen/alerts', label: 'Official Alerts', icon: Bell },
]
const authorityNav = [
  { to: '/authority', label: 'Command Overview', icon: Command, end: true }, { to: '/authority/map', label: 'Geographic Risk Map', icon: Map },
  { to: '/authority/analytics', label: 'Prediction Analytics', icon: ChartNoAxesCombined }, { to: '/authority/infrastructure', label: 'Infrastructure Exposure', icon: Building2 },
  { to: '/authority/zones', label: 'Priority Zones', icon: Target }, { to: '/authority/planner', label: 'AI Response Planner', icon: Sparkles },
  { to: '/authority/incidents', label: 'Incident Management', icon: CircleAlert }, { to: '/authority/alerts', label: 'Alerts', icon: Bell },
  { to: '/authority/history', label: 'Historical Reports', icon: FileClock },
]
export function Sidebar({ mode, close }: { mode: 'citizen' | 'authority'; close: () => void }) {
  const { profile } = useAuth()
  const nav = mode === 'citizen' ? citizenNav : profile?.role === 'admin' ? [...authorityNav, { to: '/authority/roles', label: 'Role Management', icon: UsersRound }] : authorityNav
  return <div className="sidebar-inner"><div className="brand"><div className="brand-symbol"><Shield size={21} strokeWidth={2.4}/></div><div><strong>CLIMAGUARD <em>AI</em></strong><small>Climate intelligence</small></div></div><div className="sidebar-label">{mode === 'citizen' ? 'CITIZEN PORTAL' : 'COMMAND CENTER'}</div><nav aria-label={`${mode} navigation`} className="sidebar-nav">{nav.map(item => <NavLink key={item.to} to={item.to} end={item.end} onClick={close} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><item.icon size={18}/><span>{item.label}</span></NavLink>)}</nav><div className="sidebar-bottom"><div className="help-card"><BookOpen size={18}/><strong>Need help?</strong><p>Find practical guidance for climate emergencies.</p><NavLink to="/citizen/safety" onClick={close}>Open safety center →</NavLink></div><span className="sidebar-footer">Predict Earlier. Decide Faster. Protect More.</span></div></div>
}
export function AppShell({ mode, localityId, onLocalityChange }: { mode: 'citizen' | 'authority'; localityId: string; onLocalityChange: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const { session, profile, signOut } = useAuth()
  const { localities: availableLocalities } = useClimate()
  const location = useLocation()
  const current = [...citizenNav, ...authorityNav].find(n => n.to === location.pathname)
  const locality: Locality = availableLocalities.find(l => l.id === localityId) ?? availableLocalities[0]
  return <div className="app-shell"><aside className={`sidebar ${open ? 'sidebar-open' : ''}`}><Sidebar mode={mode} close={() => setOpen(false)}/></aside>{open && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setOpen(false)}/>}<div className="main-frame"><header className="topbar"><div className="topbar-left"><button className="menu-button" aria-label={open ? 'Close menu' : 'Open menu'} onClick={() => setOpen(v => !v)}>{open ? <X size={21}/> : <Menu size={21}/>}</button><div className="breadcrumb"><span>{mode === 'citizen' ? 'Citizen portal' : 'Command center'}</span><span className="breadcrumb-separator">/</span><strong>{current?.label ?? 'Overview'}</strong></div></div><div className="topbar-actions"><span className="region-tag"><CloudSun size={16}/> Pune region</span><LocalitySelector value={localityId} options={availableLocalities} onChange={onLocalityChange}/>{(mode === 'authority' || ['authority', 'admin'].includes(profile?.role ?? '')) && <NavLink className="switch-link" to={mode === 'citizen' ? '/authority' : '/citizen'} title={`Switch to ${mode === 'citizen' ? 'authority' : 'citizen'} portal`}><ArrowLeftRight size={16}/><span>{mode === 'citizen' ? 'Authority' : 'Citizen'} view</span></NavLink>}{session ? <><NavLink className="switch-link" to="/citizen/profile" title="Profile"><UserRound size={16}/><span>Profile</span></NavLink><button className="switch-link" onClick={() => void signOut()} title="Sign out"><LogOut size={16}/><span>Sign out</span></button></> : <NavLink className="switch-link" to="/login"><UserRound size={16}/><span>Sign in</span></NavLink>}</div></header><main className="page-content"><Outlet context={{ locality }}/></main><footer className="app-footer"><span>CLIMAGUARD AI · Pune pilot</span><span><Activity size={13}/> Data provenance shown on each view</span></footer></div></div>
}
export function PortalSwitch() { return <div className="portal-switch"><Button asChild variant="outline"><NavLink to="/citizen"><House size={16}/> Citizen portal</NavLink></Button><Button asChild variant="outline"><NavLink to="/authority"><ClipboardList size={16}/> Authority center</NavLink></Button></div> }
