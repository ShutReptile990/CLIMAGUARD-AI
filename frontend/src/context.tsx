import { createContext, useContext, useState, type ReactNode } from 'react'
import { useSnapshot } from './lib/hooks'
import { demoSnapshot, localities } from './lib/demo'
import type { Incident, Snapshot } from './types'
import { authConfigured } from './lib/supabase'
import { useZonesGeojson } from './lib/hooks'
type ClimateContext = { localityId: string; setLocalityId: (id: string) => void; localities: typeof localities; demo: boolean; setDemo: (value: boolean) => void; snapshot: Snapshot; loading: boolean; error: string | null; retry: () => void; demoReports: Incident[]; addDemoReport: (incident: Incident) => void }
const Context = createContext<ClimateContext | null>(null)
const storageKey = 'climaguard-demo-reports'
function readReports(): Incident[] { try { return JSON.parse(localStorage.getItem(storageKey) ?? '[]') as Incident[] } catch { return [] } }
export function ClimateProvider({ children }: { children: ReactNode }) {
  const [localityId, setLocalityId] = useState('pune')
  const [demo, setDemo] = useState(!authConfigured)
  const [demoReports, setReports] = useState<Incident[]>(readReports)
  const query = useSnapshot(localityId, !demo)
  const zones = useZonesGeojson()
  const allLocalities = [...localities, ...(zones.data?.features ?? []).map(feature => ({ id: feature.properties.slug, name: feature.properties.name, city: feature.properties.city, center: feature.properties.centroid }))]
  const locality = allLocalities.find(l => l.id === localityId) ?? localities[0]
  const snapshot = demo ? demoSnapshot(locality) : query.data ?? { locality, weather: { temperatureC: null, humidityPercent: null, rainfallMm: null, aqi: null, observedAt: null, source: null, status: 'unavailable' as const }, risks: (['flood', 'heat', 'air_quality'] as const).map(hazard => ({ hazard, level: 'unavailable' as const, score: null, factors: [], assessedAt: null, source: 'No connected assessment', status: 'unavailable' as const })), alerts: [], facilities: [], updatedAt: null, status: 'unavailable' as const }
  const addDemoReport = (incident: Incident) => setReports(prev => { const next = [incident, ...prev]; localStorage.setItem(storageKey, JSON.stringify(next)); return next })
  return <Context.Provider value={{ localityId, setLocalityId, localities: allLocalities, demo, setDemo, snapshot, loading: !demo && query.isLoading, error: !demo && query.error ? query.error.message : null, retry: () => { void query.refetch() }, demoReports, addDemoReport }}>{children}</Context.Provider>
}
export function useClimate() { const value = useContext(Context); if (!value) throw new Error('ClimateProvider missing'); return value }
