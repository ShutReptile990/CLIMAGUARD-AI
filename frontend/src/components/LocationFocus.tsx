import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useClimate } from '../context'
import { useAnalysis } from '../lib/hooks'
import { Button } from './ui/button'
import { LocalitySelector, Panel, SectionHeading } from './Shared'

const evidence = [
  { name: 'Terrain slope', value: (metrics: { slope_mean_degrees: number | null }) => metrics.slope_mean_degrees == null ? null : `${metrics.slope_mean_degrees}° mean slope` },
  { name: 'Mapped drainage proximity', value: (metrics: { mapped_drain_distance_m: number | null }) => metrics.mapped_drain_distance_m == null ? null : `${metrics.mapped_drain_distance_m.toLocaleString('en-IN')} m to mapped drain` },
  { name: 'Zone population', value: (metrics: { population_estimate: number | null }) => metrics.population_estimate == null ? null : `${metrics.population_estimate.toLocaleString('en-IN')} estimated people` },
] as const

export function LocationFocus() {
  const { localityId, setLocalityId, localities, demo } = useClimate()
  const selected = localities.find(item => item.id === localityId)
  const isGridCell = localityId.startsWith('pune-grid-')
  const analysis = useAnalysis(localityId, !demo && isGridCell)
  const features = new Map(analysis.data?.feature_availability.map(item => [item.name, item]))

  return <Panel className="location-focus section-block">
    <div className="location-focus-header">
      <SectionHeading eyebrow="LOCATION FOCUS" title="Explore a Pune analysis cell"/>
      <div className="location-focus-actions"><LocalitySelector value={localityId} options={localities} onChange={setLocalityId}/><Link className="text-link" to="/citizen/map">Choose on map <ArrowRight size={15}/></Link></div>
    </div>
    {isGridCell ? <>
      <p className="body-copy"><strong>{selected?.name ?? 'Selected Pune grid cell'}</strong> is a reproducible analysis cell, not an official locality or ward.</p>
      {demo ? <p className="disclaimer">Switch to live mode to see sourced terrain, mapped drainage and WorldPop estimates.</p>
        : analysis.isLoading ? <p className="subtle">Loading source-backed cell data…</p>
        : analysis.error ? <p className="form-error" role="alert">Cell data unavailable: {analysis.error.message}</p>
        : <div className="location-evidence">{evidence.map(item => {
            const feature = features.get(item.name)
            const value = analysis.data?.metrics ? item.value(analysis.data.metrics) : null
            return <div key={item.name}><span>{item.name}</span><strong>{value ?? 'Unavailable'}</strong><small>{feature?.status === 'available' ? 'Available' : feature?.status === 'partial' ? 'Partial coverage' : 'Unavailable'} · {feature?.source ?? 'No verified source'}</small></div>
          })}</div>}
      <p className="disclaimer">Mapped drainage proximity does not measure drain capacity. Population is the cell estimate, not the number exposed to flooding.</p>
    </> : <div className="location-overview"><p className="body-copy"><strong>{localityId === 'pune' ? 'Pune overview' : selected?.name ?? 'Pune locality'}:</strong> weather screening applies to this selection. Terrain, mapped drainage and WorldPop estimates are available for individual grid cells; they do not become Pune-wide values.</p><Button variant="outline" size="sm" disabled={!localities.some(item => item.id === 'pune-grid-r2-c2')} onClick={() => setLocalityId('pune-grid-r2-c2')}>Try grid B2 example</Button><span className="disclaimer">Grid B2 is an analysis cell, not an official locality or ward.</span></div>}
  </Panel>
}
