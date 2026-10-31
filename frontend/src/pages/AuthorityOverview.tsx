import { Bell, CircleAlert, MapPin, Target, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useClimate } from '../context'
import { useAlerts, useAnalysis, useComparison, useExposure, useIncidents } from '../lib/hooks'
import { Button } from '../components/ui/button'
import { ForecastChart, Panel, RiskBadge, RiskMap, SectionHeading } from '../components/Shared'
import { DataBanner } from './Citizen'

export function CommandOverview() {
  const { snapshot, demo, localityId, demoReports } = useClimate()
  const comparison = useComparison(!demo)
  const exposure = useExposure(localityId, !demo && localityId.startsWith('pune-grid-'))
  const analysis = useAnalysis(localityId, !demo)
  const alerts = useAlerts(!demo, localityId)
  const incidents = useIncidents(!demo)
  const pending = (incidents.data ?? []).filter(item => item.status === 'submitted' || item.status === 'under_review').length
  const unavailable = (analysis.data?.feature_availability ?? []).filter(item => item.status === 'unavailable').map(item => item.name)
  const metrics = [
    { label: 'Analysis cells assessed', value: demo ? '—' : comparison.data ? String(comparison.data.zones.length) : '—', note: comparison.error?.message ?? 'Provisional screening', icon: Target },
    { label: 'WorldPop in selected cell', value: !demo && exposure.data?.population_in_cell != null ? exposure.data.population_in_cell.toLocaleString('en-IN') : '—', note: exposure.error?.message ?? (localityId === 'pune' ? 'Select a grid cell' : 'Not flood-exposed population'), icon: Users },
    { label: 'Recent active alerts', value: demo ? String(snapshot.alerts.length) : alerts.data ? String(alerts.data.length) : '—', note: alerts.error?.message ?? 'Authority published and unexpired', icon: Bell },
    { label: 'Recent incident reports', value: demo ? String(demoReports.length) : incidents.data ? String(incidents.data.length) : '—', note: incidents.error?.message ?? `${pending} awaiting review`, icon: CircleAlert },
  ]
  return <><div className="hero-header"><div><span className="eyebrow">PUNE · COMMAND CENTER</span><h1>Command overview</h1><p>Current screening, public alerts and the incident queue for the selected area.</p></div><span className="authority-status"><span/> {demo ? 'Illustrative workspace' : 'Live screening'}</span></div><DataBanner/>
    <div className="command-grid">{metrics.map(item => <Panel className="command-metric" key={item.label}><span className="command-icon"><item.icon size={20}/></span><span className="card-label">{item.label}</span><strong>{item.value}</strong><span className="subtle">{item.note}</span></Panel>)}</div>
    <div className="content-grid"><Panel className="map-panel"><SectionHeading eyebrow="REGIONAL VIEW" title="Pune geographic overview" action={<Link className="text-link" to="/authority/map">Open map →</Link>}/><RiskMap locality={snapshot.locality} compact/></Panel><Panel><SectionHeading eyebrow="HAZARD PROFILE" title="Risk overview"/><div className="compact-risks">{snapshot.risks.map(risk => <div key={risk.hazard}><span>{risk.hazard === 'air_quality' ? 'Air quality' : risk.hazard[0].toUpperCase() + risk.hazard.slice(1)}</span><RiskBadge level={risk.level}/></div>)}</div><p className="disclaimer">Heuristic and rule-based screening. Flood scores are not calibrated probabilities or dispatch orders.</p></Panel></div>
    <div className="content-grid"><Panel><SectionHeading eyebrow={demo ? 'SCENARIO ONLY' : 'OPEN-METEO FORECAST'} title="Rainfall pattern"/><ForecastChart/><p className="disclaimer">{demo ? 'Illustrative scenario.' : 'Provider forecast, not a validated flood-event forecast.'}</p></Panel><Panel><SectionHeading eyebrow="OPERATIONAL QUEUE" title="What needs attention"/><p><strong>{demo ? 'Demo reports' : `${pending} reports awaiting review`}</strong></p><p>{demo ? 'Switch to live mode for persisted incident review.' : incidents.error ? incidents.error.message : 'Citizen reports are unverified until reviewed.'}</p><p><strong>Evidence limitations</strong></p><p>{demo ? 'Demo values are illustrative.' : analysis.error ? analysis.error.message : unavailable.length ? unavailable.join(', ') : 'No unavailable feature flags for this selection.'}</p><Button asChild variant="outline" size="sm"><Link to="/authority/incidents">Open incident queue →</Link></Button></Panel></div>
    <p className="disclaimer"><MapPin size={14}/> {localityId === 'pune' ? 'Pune overview does not aggregate grid-cell terrain or population.' : `Selected analysis cell: ${snapshot.locality.name}.`}</p>
  </>
}
