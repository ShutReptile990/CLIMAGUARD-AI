import React, { Suspense, lazy } from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { LoadingSkeleton } from './components/Shared'
import { ClimateProvider, useClimate } from './context'
import { AuthProvider, useAuth } from './auth'
import { RequireAuth } from './components/RequireAuth'
import './styles.css'
import 'leaflet/dist/leaflet.css'
import './ux.css'

const LoginPage = lazy(() => import('./pages/Account').then(module => ({ default: module.LoginPage })))
const ProfilePage = lazy(() => import('./pages/Account').then(module => ({ default: module.ProfilePage })))
const ResetPasswordPage = lazy(() => import('./pages/Account').then(module => ({ default: module.ResetPasswordPage })))
const CitizenAlerts = lazy(() => import('./pages/Citizen').then(module => ({ default: module.CitizenAlerts })))
const AlertDetail = lazy(() => import('./components/LiveAlerts').then(module => ({ default: module.AlertDetail })))
const CitizenMap = lazy(() => import('./pages/Citizen').then(module => ({ default: module.CitizenMap })))
const CitizenOverview = lazy(() => import('./pages/Citizen').then(module => ({ default: module.CitizenOverview })))
const CitizenPredictions = lazy(() => import('./pages/Citizen').then(module => ({ default: module.CitizenPredictions })))
const SafetyCenter = lazy(() => import('./pages/Citizen').then(module => ({ default: module.SafetyCenter })))
const IncidentForm = lazy(() => import('./pages/IncidentPages').then(module => ({ default: module.IncidentForm })))
const MyReports = lazy(() => import('./pages/IncidentPages').then(module => ({ default: module.MyReports })))
const AIResponsePlanner = lazy(() => import('./pages/Authority').then(module => ({ default: module.AIResponsePlanner })))
const GeographicMap = lazy(() => import('./pages/Authority').then(module => ({ default: module.GeographicMap })))
const HistoricalReports = lazy(() => import('./pages/Authority').then(module => ({ default: module.HistoricalReports })))
const InfrastructureExposure = lazy(() => import('./pages/Authority').then(module => ({ default: module.InfrastructureExposure })))
const PredictionAnalytics = lazy(() => import('./pages/Authority').then(module => ({ default: module.PredictionAnalytics })))
const PriorityZones = lazy(() => import('./pages/Authority').then(module => ({ default: module.PriorityZones })))
const CommandOverview = lazy(() => import('./pages/AuthorityOverview').then(module => ({ default: module.CommandOverview })))
const Alerts = lazy(() => import('./pages/AuthorityRecords').then(module => ({ default: module.Alerts })))
const IncidentManagement = lazy(() => import('./pages/AuthorityRecords').then(module => ({ default: module.IncidentManagement })))
const AdminRoles = lazy(() => import('./pages/AdminRoles').then(module => ({ default: module.AdminRoles })))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: boolean }> {
  state = { error: false }
  static getDerivedStateFromError() { return { error: true } }
  render() { return this.state.error ? <div className="fatal-error"><h1>Something went wrong</h1><p>Refresh the page to try again.</p><button onClick={() => window.location.reload()}>Refresh page</button></div> : this.props.children }
}

const page = (content: React.ReactNode) => <Suspense fallback={<div role="status" aria-label="Loading page"><LoadingSkeleton/></div>}>{content}</Suspense>

function RoutesWithContext() {
  const { localityId, setLocalityId } = useClimate()
  return <Routes>
    <Route path="/" element={<Navigate to="/citizen" replace/>}/>
    <Route path="/login" element={page(<LoginPage/>)}/>
    <Route path="/reset-password" element={page(<ResetPasswordPage/>)}/>
    <Route element={<AppShell mode="citizen" localityId={localityId} onLocalityChange={setLocalityId}/>}>
      <Route path="/citizen" element={page(<CitizenOverview/>)}/>
      <Route path="/citizen/map" element={page(<CitizenMap/>)}/>
      <Route path="/citizen/predictions" element={page(<CitizenPredictions/>)}/>
      <Route path="/citizen/safety" element={page(<SafetyCenter/>)}/>
      <Route path="/citizen/alerts" element={page(<CitizenAlerts/>)}/>
      <Route path="/citizen/alerts/:id" element={page(<AlertDetail/>)}/>
      <Route path="/citizen/report" element={<RequireAuth allowDemo>{page(<IncidentForm/>)}</RequireAuth>}/>
      <Route path="/citizen/reports" element={<RequireAuth allowDemo>{page(<MyReports/>)}</RequireAuth>}/>
      <Route path="/citizen/profile" element={<RequireAuth>{page(<ProfilePage/>)}</RequireAuth>}/>
    </Route>
    <Route element={<RequireAuth authority><AppShell mode="authority" localityId={localityId} onLocalityChange={setLocalityId}/></RequireAuth>}>
      <Route path="/authority" element={page(<CommandOverview/>)}/>
      <Route path="/authority/map" element={page(<GeographicMap/>)}/>
      <Route path="/authority/analytics" element={page(<PredictionAnalytics/>)}/>
      <Route path="/authority/infrastructure" element={page(<InfrastructureExposure/>)}/>
      <Route path="/authority/zones" element={page(<PriorityZones/>)}/>
      <Route path="/authority/planner" element={page(<AIResponsePlanner/>)}/>
      <Route path="/authority/incidents" element={page(<IncidentManagement/>)}/>
      <Route path="/authority/alerts" element={page(<Alerts/>)}/>
      <Route path="/authority/history" element={page(<HistoricalReports/>)}/>
      <Route path="/authority/roles" element={<AdminOnly>{page(<AdminRoles/>)}</AdminOnly>}/>
    </Route>
    <Route path="*" element={<Navigate to="/citizen" replace/>}/>
  </Routes>
}

function AdminOnly({ children }: { children: React.ReactNode }) { const { profile } = useAuth(); return profile?.role === 'admin' ? <>{children}</> : <Navigate to="/authority" replace/> }

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary><QueryClientProvider client={queryClient}><AuthProvider><ClimateProvider><BrowserRouter><RoutesWithContext/></BrowserRouter></ClimateProvider></AuthProvider></QueryClientProvider></ErrorBoundary></React.StrictMode>)
