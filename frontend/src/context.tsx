import { createContext, useContext, useState, type ReactNode } from 'react'
import { useExtremeFloodDemo, useSnapshot } from './lib/hooks'
import { demoSnapshot, localities } from './lib/demo'
import type { DemoFloodResponse, Incident, NugenScenarioId, Snapshot } from './types'
import { authConfigured } from './lib/supabase'
import { useZonesGeojson } from './lib/hooks'
type ClimateContext = { localityId: string; setLocalityId: (id: string) => void; localities: typeof localities; demo: boolean; setDemo: (value: boolean) => void; demoScenarioId: NugenScenarioId; setDemoScenarioId: (id: NugenScenarioId) => void; demoFlood: DemoFloodResponse | null; snapshot: Snapshot; loading: boolean; error: string | null; retry: () => void; demoReports: Incident[]; addDemoReport: (incident: Incident) => void }
const Context = createContext<ClimateContext | null>(null)
const storageKey = 'climaguard-demo-reports'
function readReports(): Incident[] { try { return JSON.parse(localStorage.getItem(storageKey) ?? '[]') as Incident[] } catch { return [] } }
export function ClimateProvider({ children }: { children: ReactNode }) {
  const [localityId, setLocalityId] = useState('pune')
  const [demo, setDemo] = useState(!authConfigured)
  const [demoScenarioId, setDemoScenarioId] = useState<NugenScenarioId>('extreme_rainfall')
  const [demoReports, setReports] = useState<Incident[]>(readReports)
  const query = useSnapshot(localityId, !demo)
  const demoQuery = useExtremeFloodDemo(demo && demoScenarioId === 'extreme_rainfall')
  const zones = useZonesGeojson()
  const allLocalities = [...localities, ...(zones.data?.features ?? []).map(feature => ({ id: feature.properties.slug, name: feature.properties.name, city: feature.properties.city, center: feature.properties.centroid }))]
  const locality = allLocalities.find(l => l.id === localityId) ?? localities[0]
  const demoBase = demoSnapshot(locality)
  const demoFlood = demoScenarioId === 'extreme_rainfall' ? demoQuery.data ?? null : null
  const demoAnalysis = (demoFlood?.zones[localityId] ?? demoFlood?.overview)?.assessments.find(item => item.hazard === 'flood')
  const demoRisk = demoAnalysis && { hazard: 'flood' as const, level: demoAnalysis.level, score: demoAnalysis.score, factors: demoAnalysis.factors.map(item => `${item.name}: ${item.value ?? 'unavailable'} ${item.unit ?? ''} (${item.source})`), assessedAt: demoAnalysis.assessed_at, source: 'Deterministic hypothetical rainfall screening', status: 'demo' as const, method: demoAnalysis.method, scoreUnit: demoAnalysis.score_unit, category: demoAnalysis.category, warnings: demoAnalysis.warnings, rulesVersion: demoAnalysis.rules_version }
  const snapshot = demo ? { ...demoBase, risks: demoBase.risks.map(item => item.hazard === 'flood' && demoScenarioId === 'extreme_rainfall' ? demoRisk ?? { ...item, score: null, level: 'unavailable' as const, factors: [], status: 'unavailable' as const, source: 'Simulation calculation unavailable' } : item) } : query.data ?? { locality, weather: { temperatureC: null, humidityPercent: null, rainfallMm: null, aqi: null, observedAt: null, source: null, status: 'unavailable' as const }, risks: (['flood', 'heat', 'air_quality'] as const).map(hazard => ({ hazard, level: 'unavailable' as const, score: null, factors: [], assessedAt: null, source: 'No connected assessment', status: 'unavailable' as const })), alerts: [], facilities: [], updatedAt: null, status: 'unavailable' as const }
  const addDemoReport = (incident: Incident) => setReports(prev => { const next = [incident, ...prev]; localStorage.setItem(storageKey, JSON.stringify(next)); return next })
  const switchDemo = (value: boolean) => { if (value) setDemoScenarioId('extreme_rainfall'); setDemo(value) }
  return <Context.Provider value={{ localityId, setLocalityId, localities: allLocalities, demo, setDemo: switchDemo, demoScenarioId, setDemoScenarioId, demoFlood, snapshot, loading: demo && demoScenarioId === 'extreme_rainfall' ? demoQuery.isLoading : !demo && query.isLoading, error: demo && demoScenarioId === 'extreme_rainfall' ? demoQuery.error?.message ?? null : !demo ? query.error?.message ?? null : null, retry: () => { void (demo ? demoQuery.refetch() : query.refetch()) }, demoReports, addDemoReport }}>{children}</Context.Provider>
}
export function useClimate() { const value = useContext(Context); if (!value) throw new Error('ClimateProvider missing'); return value }
