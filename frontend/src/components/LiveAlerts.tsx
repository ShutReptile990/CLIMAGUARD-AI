import { Bell, ArrowRight } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useClimate } from '../context'
import { useAlerts } from '../lib/hooks'
import type { PublicAlert } from '../types'
import { Button } from './ui/button'
import { ErrorState, LoadingSkeleton, Panel, RiskBadge, SectionHeading } from './Shared'

function locationLabel(id: string) {
  const match = /^pune-grid-r([1-3])-c([1-3])$/.exec(id)
  return match ? `Pune grid cell ${'ABC'[Number(match[2]) - 1]}${match[1]}` : id === 'pune' ? 'Pune overview' : id
}

function publishedTime(alert: PublicAlert) {
  return alert.publishedAt ? new Date(alert.publishedAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : 'Publication time unavailable'
}

function AlertEntry({ alert, compact = false }: { alert: PublicAlert; compact?: boolean }) {
  return <Link className={`live-alert-item ${alert.level === 'severe' ? 'live-alert-critical' : ''}`} to={`/citizen/alerts/${encodeURIComponent(alert.id)}`}>
    <div className="live-alert-item-head"><RiskBadge level={alert.level}/><time dateTime={alert.publishedAt ?? undefined}>{publishedTime(alert)}</time></div>
    <strong>{alert.title}</strong>
    <span>{locationLabel(alert.localityId)}</span>
    <p>{compact && alert.body.length > 150 ? `${alert.body.slice(0, 147)}…` : alert.body}</p>
  </Link>
}

export function LiveAlerts({ sidebar = false }: { sidebar?: boolean }) {
  const { localityId, demo } = useClimate()
  const query = useAlerts(!demo, localityId)
  const alerts = (query.data ?? []).filter(alert => alert.status === 'published' && (!alert.expiresAt || new Date(alert.expiresAt).getTime() > Date.now()))
    .sort((a, b) => new Date(b.publishedAt ?? b.createdAt).getTime() - new Date(a.publishedAt ?? a.createdAt).getTime())
  return <Panel className={sidebar ? 'live-alerts-sidebar' : 'live-alerts-page'}>
    <SectionHeading eyebrow="OFFICIAL UPDATES" title="Live Alerts" action={<Bell size={19} aria-hidden="true"/>}/>
    <p className="live-alert-context">{localityId === 'pune' ? 'Published alerts across Pune analysis cells' : `Published alerts for ${locationLabel(localityId)}`}</p>
    {demo ? <p className="live-alert-empty">Live alerts require live mode. No demo advisory is shown as official.</p>
      : query.isLoading ? <LoadingSkeleton/>
      : query.error ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()}/>
      : alerts.length ? <div className="live-alert-list">{(sidebar ? alerts.slice(0, 5) : alerts).map(alert => <AlertEntry key={alert.id} alert={alert} compact={sidebar}/>)}</div>
      : <p className="live-alert-empty">No active alerts for your area.</p>}
    {sidebar && <Link className="text-link live-alert-all" to="/citizen/alerts">View All Alerts <ArrowRight size={15}/></Link>}
  </Panel>
}

export function AlertDetail() {
  const { id } = useParams()
  const { localityId, demo } = useClimate()
  const query = useAlerts(!demo, localityId)
  const alert = query.data?.find(item => item.id === id && item.status === 'published' && (!item.expiresAt || new Date(item.expiresAt).getTime() > Date.now()))
  return <><div className="page-intro"><span className="eyebrow">OFFICIAL ALERT</span><h1>Alert details</h1><p>Published advisories for the selected Pune area.</p></div>
    <Panel className="live-alert-detail">{demo ? <p>Switch to live mode to view official alerts.</p> : query.isLoading ? <LoadingSkeleton/> : query.error ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()}/> : alert ? <>
      <RiskBadge level={alert.level}/><h2>{alert.title}</h2><p className="live-alert-meta">{locationLabel(alert.localityId)} · Published {publishedTime(alert)}</p><p className="live-alert-body">{alert.body}</p><p className="disclaimer">Official authority alert · Source: {alert.source}{alert.expiresAt ? ` · Expires ${new Date(alert.expiresAt).toLocaleString('en-IN')}` : ''}</p>
    </> : <p>This alert is not active for the selected area. It may have expired or been withdrawn.</p>}</Panel>
    <Button asChild variant="outline"><Link to="/citizen/alerts">Back to alerts</Link></Button>
  </>
}
