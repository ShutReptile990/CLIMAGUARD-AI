import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { CloudRain, Flame, ShieldCheck, Wind } from 'lucide-react'
import { useClimate } from '../context'
import { api } from '../lib/api'
import { useNugenStatus } from '../lib/hooks'
import type { Hazard, NugenGuidance, NugenScenarioId, RiskLevel } from '../types'
import { Button } from './ui/button'

const hazards: { id: Hazard; label: string; icon: typeof CloudRain }[] = [
  { id: 'flood', label: 'Flood risk', icon: CloudRain },
  { id: 'heat', label: 'Heat risk', icon: Flame },
  { id: 'air_quality', label: 'Air quality risk', icon: Wind },
]

function safeError(error: Error): string {
  if (error.message.includes('Could not reach FastAPI')) return 'The guidance service cannot be reached. Check your connection and try again.'
  return error.message.split(' (HTTP')[0].replace(/https?:\/\/\S+/g, '').trim() || 'Please try again shortly.'
}

function localTime(value: string | null | undefined): string {
  return value ? `${new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST` : 'Time unavailable'
}

export function RecommendationPanel({ demo, audience = 'citizen', onGuidance }: { demo: boolean; audience?: 'citizen' | 'authority'; onGuidance?: (value: NugenGuidance | null) => void }) {
  const { localityId, localities, snapshot } = useClimate()
  const status = useNugenStatus(true)
  const scenarios = useQuery({ queryKey: ['nugen-scenarios'], queryFn: api.nugenScenarios, enabled: demo })
  const [scenarioId, setScenarioId] = useState<NugenScenarioId>('extreme_rainfall')
  const scenario = scenarios.data?.find(item => item.id === scenarioId)
  const [lastValid, setLastValid] = useState<NugenGuidance | null>(null)
  const requestKey = `${localityId}:${audience}:${demo ? `simulation:${scenarioId}` : 'live'}`
  const selection = useRef(requestKey)
  const generation = useRef(0)
  if (selection.current !== requestKey) generation.current += 1
  selection.current = requestKey
  const inference = useMutation({
    mutationFn: ({ area, scenarioId: selected }: { area: string; scenarioId: NugenScenarioId | null; key: string; generation: number }) => api.nugenGuidance(area, audience, selected ? { mode: 'simulation', scenario_id: selected } : { mode: 'live' }),
    onSuccess: (value, variables) => { if (selection.current === variables.key && generation.current === variables.generation && value.mode === (variables.scenarioId ? 'simulation' : 'live') && value.scenario_id === variables.scenarioId) { setLastValid(value); onGuidance?.(value) } },
  })
  const result = lastValid?.locality_id === localityId && lastValid.audience === audience && lastValid.mode === (demo ? 'simulation' : 'live') && lastValid.scenario_id === (demo ? scenarioId : null) ? lastValid : null
  const areaName = result?.locality_name ?? localities.find(item => item.id === localityId)?.name ?? 'Selected area'
  useEffect(() => { setLastValid(null); inference.reset(); onGuidance?.(null) }, [requestKey, onGuidance])
  const generate = () => inference.mutate({ area: localityId, scenarioId: demo ? scenarioId : null, key: requestKey, generation: generation.current })

  return <section className="panel recommendations guidance-panel" aria-labelledby={`guidance-heading-${audience}`}>
    <div className="guidance-header">
      <span className="guidance-icon" aria-hidden="true"><ShieldCheck size={25}/></span>
      <div className="guidance-title"><span className="eyebrow">{audience === 'authority' ? 'NUGEN RESPONSE PLANNER' : 'NUGEN SAFETY GUIDANCE'}</span><h2 id={`guidance-heading-${audience}`}>{demo ? 'AI Guidance for Simulated Scenario' : audience === 'authority' ? 'Response planning guidance' : 'Your Safety Guidance'}</h2><p>For {areaName}{result ? ` · Updated ${localTime(result.inferred_at)}` : ''}</p></div>
      <div className="guidance-header-actions"><span className="guidance-ai-status" role="status">AI: {result ? 'available' : status.isLoading ? 'checking…' : status.data?.available ? 'recently available' : status.data?.configured ? 'ready to generate' : 'unavailable'}</span><Button type="button" disabled={inference.isPending || !status.data?.configured || (demo && !scenario)} onClick={generate}>{inference.isPending ? 'Generating…' : result ? 'Refresh guidance' : audience === 'authority' ? 'Generate response brief' : 'Generate safety guidance'}</Button></div>
    </div>

    {demo && <div className="guidance-simulation-context"><strong className="guidance-simulation-badge">SIMULATION — NOT LIVE CONDITIONS</strong><label htmlFor={`guidance-scenario-${audience}`}>Hypothetical scenario</label><select id={`guidance-scenario-${audience}`} value={scenarioId} onChange={event => setScenarioId(event.target.value as NugenScenarioId)} disabled={scenarios.isLoading || !scenarios.data?.length}>{scenarios.data?.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select>{scenarios.error && <p role="alert">Scenario options unavailable: {safeError(scenarios.error)}.</p>}{scenario && <p>Assumed inputs: {[scenario.rainfall_intensity_mm_h != null ? `${scenario.rainfall_intensity_mm_h} mm/h rain for ${scenario.rainfall_duration_hours} hours` : null, scenario.temperature_c != null ? `${scenario.temperature_c}°C air temperature` : null, scenario.humidity_percent != null ? `${scenario.humidity_percent}% humidity` : null].filter(Boolean).join(' · ')}. {scenario.limitation}</p>}</div>}
      <div className="guidance-risk-grid" aria-label={demo ? 'Simulated risk screening' : 'Current risk screening'}>
        {hazards.map(({ id, label, icon: Icon }) => {
          const source = result?.source_analysis.hazards.find(item => item.hazard === id)
          const live = !demo && snapshot.status === 'live' && snapshot.locality.id === localityId ? snapshot.risks.find(item => item.hazard === id) : undefined
          const available = source ? source.status === 'available' : live?.status === 'live'
          const level: RiskLevel = available ? (source?.level ?? live?.level ?? 'unavailable') : 'unavailable'
          return <div className="guidance-risk" key={id}><Icon size={20} aria-hidden="true"/><span>{label}</span><strong className={`guidance-risk-level level-${level}`}>{available ? level[0].toUpperCase() + level.slice(1) : demo && !result ? 'Awaiting simulation' : 'Data unavailable'}</strong></div>
        })}
      </div>

      {inference.isPending && <p className="guidance-loading" role="status" aria-live="polite">Generating safety recommendations from {demo ? 'hypothetical screening' : 'current risk analysis'}…</p>}
      {inference.error && <div className="guidance-error" role="alert"><p><strong>{result ? 'Refresh did not succeed. Previous guidance remains below.' : 'Guidance could not be generated.'}</strong> {safeError(inference.error)}</p><Button type="button" variant="outline" disabled={inference.isPending} onClick={generate}>Retry guidance</Button></div>}

      {result ? <>
        <h3 className="guidance-actions-heading">Recommended actions</h3>
        <ol className="guidance-actions">{result.guidance.actions.map((action, index) => <li key={`${index}-${action}`}><span className="guidance-action-number" aria-hidden="true">{index + 1}</span><div><strong>Action {index + 1}</strong><p>{action}</p></div></li>)}</ol>
        {audience === 'authority' && result.source_analysis.priority && <p className="guidance-priority">Provisional priority: {result.source_analysis.priority.score ?? 'unavailable'} / 100. This is not a dispatch order.</p>}
        <p className="guidance-notice">{demo ? 'These recommendations are generated for a hypothetical demonstration scenario. They do not describe current conditions or constitute an official emergency alert.' : 'AI-generated preparedness guidance based on available environmental data. This is not an official emergency alert.'}</p>
        <details className="guidance-details"><summary>How was this guidance generated?</summary><div className="guidance-details-body">
          <p><strong>Analysis summary</strong><br/>{result.guidance.summary}</p>
          {result.guidance.risk_explanation && <p><strong>Risk-screening explanation</strong><br/>{result.guidance.risk_explanation}</p>}
          <p><strong>Environmental indicators</strong></p><ul>{result.source_analysis.hazards.map(item => <li key={item.hazard}>{hazards.find(hazard => hazard.id === item.hazard)?.label ?? item.hazard}: {item.status === 'available' ? `${item.level} · ${item.score ?? 'Value unavailable'} ${item.score_unit ?? ''}` : 'Data unavailable'} · Data time: {localTime(item.valid_at)} · Method: {item.method} · Source: {item.sources.join(', ') || 'Unavailable'}</li>)}</ul>
          {result.source_analysis.priority && <p><strong>Priority factors</strong><br/>{result.source_analysis.priority.components.filter(item => item.contribution_points != null).map(item => `${item.name.replace('_', ' ')}: ${item.contribution_points}`).join(' · ') || 'Unavailable'}</p>}
          <p><strong>Limitations</strong><br/>{result.guidance.limitations}</p>
          <p>Flood screening is a heuristic index, not a validated flood probability. Heat screening is not an official heatwave warning. Air-quality values use US AQI where applicable, not Indian AQI.</p>
          <p><strong>Inference record</strong><br/>Mode: {result.mode}{result.scenario_label ? ` · ${result.scenario_label}` : ''}<br/>Nugen model: <span className="guidance-identifier">{result.model_id}</span><br/>Generated: {localTime(result.inferred_at)}{result.cache_hit ? ' · Cached from matching analysis' : ''}<br/>Draft: {result.persistence === 'stored' ? 'stored in Supabase' : result.persistence === 'not_stored_simulation' ? 'simulation guidance is not stored' : 'not stored in Supabase'}{result.provider_request_id && <><br/>Request ID: <span className="guidance-identifier">{result.provider_request_id}</span></>}</p>
        </div></details>
      </> : !inference.isPending && !inference.error && <p className="guidance-empty">Generate guidance to see recommendations from the aligned Nugen model for this area. {demo ? 'Only the selected hypothetical inputs are used for hazard screening; air quality cannot be simulated here.' : 'Risk levels above come from live deterministic analysis when available.'}</p>}
  </section>
}
