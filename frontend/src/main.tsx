import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ClimateProvider, useClimate } from './context'
import { AuthProvider, useAuth } from './auth'
import { RequireAuth, LoginPage, ProfilePage, ResetPasswordPage } from './pages/Account'
import { CitizenAlerts, CitizenMap, CitizenOverview, CitizenPredictions, SafetyCenter } from './pages/Citizen'
import { IncidentForm, MyReports } from './pages/IncidentPages'
import { AIResponsePlanner, GeographicMap, HistoricalReports, InfrastructureExposure, PredictionAnalytics, PriorityZones } from './pages/Authority'
import { CommandOverview } from './pages/AuthorityOverview'
import { Alerts, IncidentManagement } from './pages/AuthorityRecords'
import { AdminRoles } from './pages/AdminRoles'
import './styles.css'
import 'leaflet/dist/leaflet.css'
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: boolean }> {
  state = { error: false }
  static getDerivedStateFromError() { return { error: true } }
  render() { return this.state.error ? <div className="fatal-error"><h1>Something went wrong</h1><p>Refresh the page to try again.</p><button onClick={() => window.location.reload()}>Refresh page</button></div> : this.props.children }
}
function RoutesWithContext() { const { localityId, setLocalityId } = useClimate(); return <Routes><Route path="/" element={<Navigate to="/citizen" replace/>}/><Route path="/login" element={<LoginPage/>}/><Route path="/reset-password" element={<ResetPasswordPage/>}/><Route element={<AppShell mode="citizen" localityId={localityId} onLocalityChange={setLocalityId}/>}><Route path="/citizen" element={<CitizenOverview/>}/><Route path="/citizen/map" element={<CitizenMap/>}/><Route path="/citizen/predictions" element={<CitizenPredictions/>}/><Route path="/citizen/safety" element={<SafetyCenter/>}/><Route path="/citizen/alerts" element={<CitizenAlerts/>}/><Route path="/citizen/report" element={<RequireAuth allowDemo><IncidentForm/></RequireAuth>}/><Route path="/citizen/reports" element={<RequireAuth allowDemo><MyReports/></RequireAuth>}/><Route path="/citizen/profile" element={<RequireAuth><ProfilePage/></RequireAuth>}/></Route><Route element={<RequireAuth authority><AppShell mode="authority" localityId={localityId} onLocalityChange={setLocalityId}/></RequireAuth>}><Route path="/authority" element={<CommandOverview/>}/><Route path="/authority/map" element={<GeographicMap/>}/><Route path="/authority/analytics" element={<PredictionAnalytics/>}/><Route path="/authority/infrastructure" element={<InfrastructureExposure/>}/><Route path="/authority/zones" element={<PriorityZones/>}/><Route path="/authority/planner" element={<AIResponsePlanner/>}/><Route path="/authority/incidents" element={<IncidentManagement/>}/><Route path="/authority/alerts" element={<Alerts/>}/><Route path="/authority/history" element={<HistoricalReports/>}/><Route path="/authority/roles" element={<AdminOnly><AdminRoles/></AdminOnly>}/></Route><Route path="*" element={<Navigate to="/citizen" replace/>}/></Routes> }
function AdminOnly({ children }: { children: React.ReactNode }) { const { profile } = useAuth(); return profile?.role === 'admin' ? <>{children}</> : <Navigate to="/authority" replace/> }
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary><QueryClientProvider client={queryClient}><AuthProvider><ClimateProvider><BrowserRouter><RoutesWithContext/></BrowserRouter></ClimateProvider></AuthProvider></QueryClientProvider></ErrorBoundary></React.StrictMode>)
