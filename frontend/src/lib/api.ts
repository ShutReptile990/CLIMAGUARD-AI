import type { AnalysisResponse, ComparisonResponse, DemoFloodResponse, EnvironmentBundle, ExposureResponse, Incident, MapScreening, MappedFacility, MappedResponse, MappedRoad, NugenGuidance, NugenScenario, NugenScenarioId, NugenStatus, ScenarioRequest, SimulationResponse, Snapshot, ZoneCollection } from '../types'
import type { Profile } from '../auth'
import { supabase } from './supabase'
import { buildApiUrl, normalizeApiBase } from './apiConfig'
const BASE = normalizeApiBase(import.meta.env.VITE_API_BASE_URL, import.meta.env.PROD)
const apiUrl = (path: string) => buildApiUrl(BASE, path)
export class ApiError extends Error { constructor(message: string, public status?: number) { super(message) } }
async function request<T>(path: string, options?: RequestInit, retried = false): Promise<T> {
  let response: Response
  const url = apiUrl(path)
  // A failed Auth session lookup must not prevent public weather and AQI requests.
  const session = supabase ? await supabase.auth.getSession().then(({ data }) => data.session).catch(() => null) : null
  try { response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}), ...options?.headers } }) }
  catch { throw new ApiError(`Could not reach FastAPI at ${BASE || 'the current origin'}. Check the backend address, Vite proxy, and CORS setting.`) }
  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    throw new ApiError(`API request ${url} returned HTTP ${response.status} without JSON. Check the backend URL and API route prefix.`, response.status)
  }
  const body: unknown = await response.json().catch(() => { throw new ApiError(`API request ${url} returned invalid JSON.`, response.status) })
  if (response.status === 401 && session && supabase && !retried) {
    const refreshed = await supabase.auth.refreshSession().catch(() => null)
    if (refreshed?.data.session) return request<T>(path, options, true)
    await supabase.auth.signOut({ scope: 'local' }).catch(() => undefined)
  }
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string' ? body.detail : null
    throw new ApiError(detail ? `${detail} (HTTP ${response.status}, ${url})` : `API request ${url} failed with HTTP ${response.status}.`, response.status)
  }
  return body as T
}
export const api = {
  profile: () => request<Profile>('/profile'),
  updateProfile: (display_name: string) => request<Profile>('/profile', { method: 'PATCH', body: JSON.stringify({ display_name }) }),
  profiles: () => request<Profile[]>('/profiles'),
  assignRole: (id: string, role: Profile['role']) => request<Profile>(`/profiles/${encodeURIComponent(id)}/role`, { method: 'PATCH', body: JSON.stringify({ role }) }),
  snapshot: (localityId: string) => request<Snapshot>(`/localities/${encodeURIComponent(localityId)}/snapshot`),
  environment: (localityId: string) => request<EnvironmentBundle>(`/environment/${encodeURIComponent(localityId)}`),
  zonesGeojson: () => request<ZoneCollection>('/zones/geojson'),
  mapScreening: () => request<MapScreening>('/map/screening'),
  mapInfrastructure: (bbox?: string) => request<MappedResponse<MappedFacility>>(`/map/infrastructure${bbox ? `?bbox=${encodeURIComponent(bbox)}` : ''}`),
  mapRoads: (bbox?: string) => request<MappedResponse<MappedRoad>>(`/map/roads${bbox ? `?bbox=${encodeURIComponent(bbox)}` : ''}`),
  analysis: (zoneId: string) => request<AnalysisResponse>(`/analysis/${encodeURIComponent(zoneId)}`),
  comparison: () => request<ComparisonResponse>('/analysis/compare'),
  extremeFloodDemo: () => request<DemoFloodResponse>('/analysis/demo/extreme-rainfall'),
  exposure: (zoneId: string) => request<ExposureResponse>(`/analysis/${encodeURIComponent(zoneId)}/exposure`),
  simulate: (scenario: ScenarioRequest) => request<SimulationResponse>('/analysis/simulate', { method: 'POST', body: JSON.stringify(scenario) }),
  nugenStatus: () => request<NugenStatus>('/nugen/status'),
  nugenScenarios: () => request<NugenScenario[]>('/nugen/scenarios'),
  nugenGuidance: (localityId: string, audience: 'citizen' | 'authority', body?: { mode: 'live' } | { mode: 'simulation'; scenario_id: NugenScenarioId }) => request<NugenGuidance>(`/nugen/${audience}/${encodeURIComponent(localityId)}`, { method: 'POST', ...(body && { body: JSON.stringify(body) }) }),
  submitIncident: (incident: Omit<Incident, 'id' | 'createdAt' | 'status'>) => request<Incident>('/incidents', { method: 'POST', body: JSON.stringify(incident) }),
  incidents: () => request<Incident[]>('/incidents'),
  incidentHistory: (id: string) => request<import('../types').IncidentHistoryEntry[]>(`/incidents/${encodeURIComponent(id)}/history`),
  reviewIncident: (id: string, status: string, review_note?: string) => request<Incident>(`/incidents/${encodeURIComponent(id)}/review`, { method: 'PATCH', body: JSON.stringify({ status, review_note }) }),
  alerts: (localityId?: string) => request<import('../types').PublicAlert[]>(`/alerts${localityId ? `?locality_id=${encodeURIComponent(localityId)}` : ''}`),
  drafts: () => request<import('../types').PublicAlert[]>('/alerts/drafts'),
  alertArchive: () => request<import('../types').PublicAlert[]>('/alerts/archive'),
  createAlert: (alert: { title: string; body: string; level: string; localityId: string; source: string; hazard: string; incidentId?: string | null }) => request<import('../types').PublicAlert>('/alerts', { method: 'POST', body: JSON.stringify(alert) }),
  editAlert: (id: string, alert: { title: string; body: string; level: string; source: string; hazard: string }) => request<import('../types').PublicAlert>(`/alerts/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(alert) }),
  editPublishedAlert: (id: string, alert: { title: string; body: string; level: string; source: string; hazard: string }) => request<import('../types').PublicAlert>(`/alerts/${encodeURIComponent(id)}/published`, { method: 'PATCH', body: JSON.stringify(alert) }),
  alertHistory: (id: string) => request<import('../types').AlertHistoryEntry[]>(`/alerts/${encodeURIComponent(id)}/history`),
  submitAlert: (id: string) => request<import('../types').PublicAlert>(`/alerts/${encodeURIComponent(id)}/submit`, { method: 'POST' }),
  reviewAlert: (id: string, approve: boolean, reason?: string) => request<import('../types').PublicAlert>(`/alerts/${encodeURIComponent(id)}/review`, { method: 'POST', body: JSON.stringify({ approve, reason }) }),
  publishAlert: (id: string, expires_at: string) => request<import('../types').PublicAlert>(`/alerts/${encodeURIComponent(id)}/publish`, { method: 'POST', body: JSON.stringify({ expires_at }) }),
  withdrawAlert: (id: string) => request<import('../types').PublicAlert>(`/alerts/${encodeURIComponent(id)}/withdraw`, { method: 'POST' }),
  expireAlert: (id: string) => request<import('../types').PublicAlert>(`/alerts/${encodeURIComponent(id)}/expire`, { method: 'POST' }),
}
