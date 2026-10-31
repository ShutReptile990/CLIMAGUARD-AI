import { useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ShieldCheck } from 'lucide-react'
import { useClimate } from '../context'
import { api } from '../lib/api'
import { useNugenStatus } from '../lib/hooks'
import type { NugenGuidance } from '../types'
import { Button } from './ui/button'

export function RecommendationPanel({ demo, audience = 'citizen', onGuidance }: { demo: boolean; audience?: 'citizen' | 'authority'; onGuidance?: (value: NugenGuidance | null) => void }) {
  const { localityId } = useClimate()
  const status = useNugenStatus(!demo)
  const inference = useMutation({ mutationFn: () => api.nugenGuidance(localityId, audience), onSuccess: value => onGuidance?.(value) })
  const result = inference.data?.locality_id === localityId ? inference.data : null
  useEffect(() => { onGuidance?.(null) }, [localityId, demo, onGuidance])
  return <section className="panel recommendations">
    <div className="recommendation-icon"><ShieldCheck size={23}/></div>
    <span className="eyebrow">{audience === 'authority' ? 'NUGEN RESPONSE PLANNER' : 'NUGEN SAFETY GUIDANCE'}</span>
    <h2>{audience === 'authority' ? 'Review response priorities' : 'Stay prepared, stay informed.'}</h2>
    <span className="subtle" role="status">AI status: {demo ? 'off in demo mode' : result ? 'real Nugen inference available' : status.isLoading ? 'checking configuration…' : status.data?.available ? 'recent Nugen inference succeeded' : status.data?.configured ? 'configured; inference not yet checked' : 'not configured'}</span>
    {demo ? <p>Illustrative mode. Switch to live status for locality-based Nugen guidance.</p> : <>
      <p>Nugen generates guidance only when requested for the selected area. This uses live deterministic screening, never a hypothetical scenario.</p>
      <Button type="button" disabled={inference.isPending || !status.data?.configured} onClick={() => inference.mutate()}>{inference.isPending ? 'Generating…' : result ? 'Refresh Nugen guidance' : audience === 'authority' ? 'Generate response brief' : 'Generate safety guidance'}</Button>
      {inference.isPending && <p role="status">Generating guidance from current flood, heat and US AQI analysis…</p>}
      {inference.error && <p role="alert">Nugen guidance unavailable: {inference.error.message}</p>}
      {result && <><p>{result.guidance.summary}</p>{result.guidance.risk_explanation && <p>{result.guidance.risk_explanation}</p>}
        <ul>{result.guidance.actions.map(action => <li key={action}>{action}</li>)}</ul>
        <p className="disclaimer">{result.guidance.limitations}</p>
        {result.source_analysis.priority && <p className="disclaimer">Provisional priority: {result.source_analysis.priority.score ?? 'unavailable'} / 100 · {result.source_analysis.priority.components.filter(item => item.contribution_points != null).map(item => `${item.name.replace('_', ' ')} ${item.contribution_points}`).join(' · ')}. This is not a dispatch order.</p>}
        <p className="disclaimer">{result.locality_name} · Nugen model {result.model_id} · Generated {new Date(result.inferred_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST{result.cache_hit ? ' · Cached from matching analysis' : ''} · Draft {result.persistence === 'stored' ? 'stored in Supabase' : 'not stored in Supabase'}{result.provider_request_id ? ` · Request ${result.provider_request_id}` : ''}.</p>
        <p className="disclaimer">Inputs: {result.source_analysis.hazards.map(hazard => `${hazard.hazard.replace('_', ' ')} ${hazard.status === 'available' ? `${hazard.score ?? '—'} ${hazard.score_unit ?? ''}` : 'unavailable'} (${hazard.valid_at ? new Date(hazard.valid_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : 'time unavailable'})`).join(' · ')}. {result.disclaimer}</p>
      </>}
    </>}
  </section>
}
