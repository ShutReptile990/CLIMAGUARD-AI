import type { AnalysisResponse, ComparisonResponse, DemoFloodResponse, EnvironmentBundle, ExposureResponse, Incident, MapScreening, MappedFacility, MappedResponse, MappedRoad, NugenGuidance, NugenScenario, NugenScenarioId, NugenStatus, ScenarioRequest, SimulationResponse, Snapshot, ZoneCollection } from '../types'
import type { Profile } from '../auth'
import { supabase } from './supabase'
import { buildApiUrl, normalizeApiBase } from './apiConfig'
const BASE = normalizeApiBase(import.meta.env.VITE_API_BASE_URL, import.meta.env.PROD)
const apiUrl = (path: string) => buildApiUrl(BASE, path)
type ApiErrorKind = 'network' | 'cors' | 'authentication' | 'authorization' | 'not_found' | 'server' | 'service' | 'invalid_response'
export class ApiError extends Error {
  constructor(message: string, public status?: number, public kind?: ApiErrorKind) { super(message) }
}

async function connectionFailure(url: string): Promise<ApiError> {
  if (typeof navigator !== 'undefined' && !navigator.onLine) {
    return new ApiError('You appear to be offline. Reconnect and try again.', undefined, 'network')
  }
  if (BASE) {
    try {
      // An opaque response proves the host is reachable without reading or exposing its data.
      await fetch(`${BASE}/api/health`, { mode: 'no-cors', cache: 'no-store' })
      return new ApiError(`The API is reachable, but the browser blocked access. Verify that Render CORS_ORIGINS includes ${window.location.origin}.`, undefined, 'cors')
    } catch { /* The host, TLS connection, or network is unavailable. */ }
  }
  return new ApiError(`Could not reach the climate service at ${new URL(url, window.location.origin).origin}. Check your connection and try again.`, undefined, 'network')
}

function httpFailure(status: number, detail: string | null): ApiError {
  if (status === 401) return new ApiError('Your session is missing or expired. Sign in and try again.', status, 'authentication')
  if (status === 403) return new ApiError('You do not have permission to perform this action.', status, 'authorization')
  if (status === 404) return new ApiError('The requested service route was not found. Check the deployed API version.', status, 'not_found')
  if (status === 502 || status === 503) return new ApiError(detail ?? 'A required upstream service is temporarily unavailable. Try again shortly.', status, 'service')
  if (status >= 500) return new ApiError('The climate service encountered an internal error. Try again shortly.', status, 'server')
  return new ApiError(detail ?? `The request failed with HTTP ${status}.`, status)
}
async function request<T>(path: string, options?: RequestInit, retried = false): Promise<T> {
  let response: Response
  const url = apiUrl(path)
  // A failed Auth session lookup must not prevent public weather and AQI requests.
  const session = supabase ? await supabase.auth.getSession().then(({ data }) => data.session).catch(() => null) : null
  try { response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}), ...options?.headers } }) }
  catch { throw await connectionFailure(url) }
  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    throw new ApiError(`The API returned HTTP ${response.status} in an unexpected format. Check the backend URL and route prefix.`, response.status, 'invalid_response')
  }
  const body: unknown = await response.json().catch(() => { throw new ApiError('The API returned invalid JSON.', response.status, 'invalid_response') })
  if (response.status === 401 && session && supabase && !retried) {
    const refreshed = await supabase.auth.refreshSession().catch(() => null)
    if (refreshed?.data.session) return request<T>(path, options, true)
    await supabase.auth.signOut({ scope: 'local' }).catch(() => undefined)
  }
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string' ? body.detail : null
    throw httpFailure(response.status, detail)
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
