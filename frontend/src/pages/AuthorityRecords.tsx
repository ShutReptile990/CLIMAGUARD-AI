import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, CircleAlert, Search } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { useClimate } from '../context'
import { useAuth } from '../auth'
import { api } from '../lib/api'
import { supabase } from '../lib/supabase'
import { useAlerts, useDrafts, useIncidents } from '../lib/hooks'
import type { Incident, PublicAlert } from '../types'
import { EmptyState, ErrorState, LoadingSkeleton, Panel, RiskBadge, SectionHeading } from '../components/Shared'
import { Button } from '../components/ui/button'
import { DataBanner, PageIntro } from './Citizen'

const readable = (value: string) => value.replaceAll('_', ' ')

export function IncidentManagement() {
  const { demo, localityId, setLocalityId } = useClimate()
  const query = useIncidents(!demo)
  const client = useQueryClient()
  const [search, setSearch] = useState('')
  const [zone, setZone] = useState('all')
  const [category, setCategory] = useState('all')
  const [status, setStatus] = useState('all')
  const [selected, setSelected] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [reviewMessage, setReviewMessage] = useState('')
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [imageError, setImageError] = useState<string | null>(null)
  const history = useQuery({ queryKey: ['incident-history', selected], queryFn: () => api.incidentHistory(selected!), enabled: Boolean(selected) && !demo })
  const review = useMutation({ mutationFn: ({ id, next, reason }: { id: string; next: string; reason?: string }) => api.reviewIncident(id, next, reason), onSuccess: updated => {
    client.setQueryData<Incident[]>(['incidents'], current => current?.map(item => item.id === updated.id ? updated : item))
    void client.invalidateQueries({ queryKey: ['incidents'] })
    void client.invalidateQueries({ queryKey: ['incident-history', updated.id] })
    setReviewMessage(updated.status === 'under_review' ? 'Review started and saved.' : `Report ${updated.status === 'resolved' ? 'verified' : 'rejected'} and saved.`)
    setNote('')
  }, onMutate: () => setReviewMessage('') })
  const reports = (query.data ?? []).filter(item =>
    (zone === 'all' || item.localityId === zone) && (category === 'all' || item.category === category) &&
    (status === 'all' || item.status === status) &&
    `${item.description} ${item.category} ${item.localityId}`.toLowerCase().includes(search.toLowerCase()))
  const detail = reports.find(item => item.id === selected)
  const openImage = async (report: Incident) => {
    setImageError(null); setImageUrl(null)
    if (!report.image_path || !supabase) return
    const { data, error } = await supabase.storage.from('incident-evidence').createSignedUrl(report.image_path, 60)
    if (error) setImageError(error.message)
    else setImageUrl(data.signedUrl)
  }
  return <><PageIntro eyebrow="INCIDENT MANAGEMENT" title="Review incoming reports" description="Citizen reports remain unverified until an authorized reviewer assesses them."/><DataBanner/>
    {demo ? <Panel><EmptyState title="Live review unavailable in demo" description="Switch to live mode with an authority account to review persisted reports." icon={CircleAlert}/></Panel> :
    <Panel><div className="table-toolbar"><SectionHeading title="Incident queue"/><label className="search-box"><Search size={17}/><span className="sr-only">Search incidents</span><input placeholder="Search reports" value={search} onChange={event => setSearch(event.target.value)}/></label></div>
      <div className="table-toolbar"><label>Location <select value={zone} onChange={event => setZone(event.target.value)}><option value="all">All cells</option><option value={localityId}>Selected: {localityId}</option>{Array.from(new Set(query.data?.map(item => item.localityId) ?? [])).filter(value => value !== localityId).map(value => <option key={value} value={value}>{value}</option>)}</select></label><label>Category <select value={category} onChange={event => setCategory(event.target.value)}><option value="all">All</option>{Array.from(new Set(query.data?.map(item => item.category) ?? [])).map(value => <option key={value} value={value}>{readable(value)}</option>)}</select></label><label>Status <select value={status} onChange={event => setStatus(event.target.value)}><option value="all">All</option><option value="submitted">Unverified</option><option value="under_review">Under review</option><option value="resolved">Verified</option><option value="rejected">Rejected</option></select></label></div>
      {reviewMessage && <p role="status">{reviewMessage}</p>}
      {query.isLoading ? <LoadingSkeleton/> : query.error ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()}/> : reports.length ? <div className="incident-table"><div className="table-head"><span>Report</span><span>Cell</span><span>Submitted</span><span>Status</span></div>{reports.map(report => <button type="button" className="table-row" key={report.id} onClick={() => { setSelected(report.id); setLocalityId(report.localityId); setImageUrl(null); setImageError(null) }}><div><strong>{readable(report.category)}</strong><p>{report.description}</p></div><span>{report.localityId}</span><span>{new Date(report.createdAt).toLocaleString('en-IN')}</span><span className="pending-tag">{report.status === 'resolved' ? 'Verified' : report.status === 'submitted' ? 'Unverified' : readable(report.status)}</span></button>)}</div> : <EmptyState title="No matching reports" description="Try another filter or wait for citizen submissions." icon={CircleAlert}/>}
      {detail && <div className="section-block"><SectionHeading title="Report details"/><p><strong>{readable(detail.category)}</strong> · {detail.localityId} · Reporter severity: {detail.severity ?? 'not recorded'}</p><p>{detail.description}</p><p className="disclaimer">Submitted {new Date(detail.createdAt).toLocaleString('en-IN')} · {detail.status === 'resolved' ? 'Verified report; not a historical flood-event label.' : `Status: ${readable(detail.status)}`}</p>{detail.review_note && <p>Review note: {detail.review_note}</p>}{detail.reviewed_at && <p className="disclaimer">Reviewed {new Date(detail.reviewed_at).toLocaleString('en-IN')}</p>}
        {detail.image_path && <><Button type="button" variant="outline" onClick={() => void openImage(detail)}>View private evidence image</Button>{imageUrl && <img src={imageUrl} alt="Citizen supplied incident evidence" style={{ maxWidth: '100%', maxHeight: 360, display: 'block', marginTop: 12 }}/ >}{imageError && <p role="alert" className="form-error">{imageError}</p>}</>}
        <div><strong>Review history</strong>{history.isLoading ? <p>Loading…</p> : history.error ? <p role="alert">{history.error.message}</p> : history.data?.length ? <ul>{history.data.map((entry, index) => <li key={`${entry.created_at}-${index}`}>{new Date(entry.created_at).toLocaleString('en-IN')}: {readable(entry.old_status)} → {readable(entry.new_status)}</li>)}</ul> : <p>No status changes recorded yet.</p>}</div>
        <p><Link className="text-link" to="/authority/analytics">Inspect current climate analysis for the selected cell</Link></p>
        {detail.status === 'resolved' && <><p><Link className="text-link" to={`/authority/planner?incidentId=${encodeURIComponent(detail.id)}`}>Optional: generate Nugen locality guidance</Link></p><p><Link className="text-link" to={`/authority/alerts?incidentId=${encodeURIComponent(detail.id)}`}>Create / Publish Alert</Link> · Verification alone does not notify citizens.</p></>}
        {detail.status === 'submitted' && <Button type="button" disabled={review.isPending} onClick={() => review.mutate({ id: detail.id, next: 'under_review' })}>Start review</Button>}
        {detail.status === 'under_review' && <><label>Review reason or note<textarea maxLength={1000} value={note} onChange={event => setNote(event.target.value)}/></label><div className="table-toolbar"><Button type="button" disabled={review.isPending} onClick={() => { if (window.confirm('Verify this citizen report? This decision is recorded in review history.')) review.mutate({ id: detail.id, next: 'resolved', reason: note }) }}>Verify report</Button><Button type="button" variant="outline" disabled={review.isPending || !note.trim()} onClick={() => { if (window.confirm('Reject this citizen report with the entered reason?')) review.mutate({ id: detail.id, next: 'rejected', reason: note }) }}>Reject with reason</Button></div></>}
        {review.error && <p className="form-error" role="alert">{review.error.message}</p>}</div>}
    </Panel>}</>
}

export function Alerts() {
  const { demo, localityId } = useClimate()
  const [searchParams] = useSearchParams()
  const incidentId = searchParams.get('incidentId')
  const linkedReports = useIncidents(Boolean(incidentId) && !demo)
  const linkedIncident = linkedReports.data?.find(item => item.id === incidentId && item.status === 'resolved')
  const { profile } = useAuth()
  const published = useAlerts(!demo)
  const drafts = useDrafts(!demo)
  const archive = useQuery({ queryKey: ['alert-archive'], queryFn: api.alertArchive, enabled: !demo })
  const client = useQueryClient()
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [source, setSource] = useState('')
  const [level, setLevel] = useState<'low' | 'moderate' | 'high' | 'severe'>('moderate')
  const [hazard, setHazard] = useState<'flood' | 'heat' | 'air_quality' | 'other'>('other')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingPublished, setEditingPublished] = useState(false)
  const [historyId, setHistoryId] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState('')
  const [reason, setReason] = useState('')
  const [expiry, setExpiry] = useState('')
  const alertHistory = useQuery({ queryKey: ['alert-history', historyId], queryFn: () => api.alertHistory(historyId!), enabled: Boolean(historyId) && !demo })
  const refresh = () => { void client.invalidateQueries({ queryKey: ['alert-drafts'] }); void client.invalidateQueries({ queryKey: ['alerts'] }); void client.invalidateQueries({ queryKey: ['alert-archive'] }) }
  const resetForm = () => { setEditingId(null); setEditingPublished(false); setTitle(''); setBody(''); setSource('') }
  const create = useMutation({ mutationFn: api.createAlert, onSuccess: () => { refresh(); resetForm(); setActionMessage('Unpublished advisory draft saved.') } })
  const edit = useMutation({ mutationFn: (id: string) => api.editAlert(id, { title, body, level, hazard, source }), onSuccess: () => { refresh(); resetForm(); setActionMessage('Draft changes saved.') } })
  const updatePublished = useMutation({ mutationFn: (id: string) => api.editPublishedAlert(id, { title, body, level, hazard, source }), onSuccess: updated => { refresh(); void client.invalidateQueries({ queryKey: ['alert-history', updated.id] }); resetForm(); setActionMessage('Published alert updated and audited.') } })
  const submit = useMutation({ mutationFn: api.submitAlert, onSuccess: () => { refresh(); setActionMessage('Advisory submitted for your explicit approval.') } })
  const review = useMutation({ mutationFn: ({ id, approve, reason }: { id: string; approve: boolean; reason?: string }) => api.reviewAlert(id, approve, reason), onSuccess: updated => { refresh(); void client.invalidateQueries({ queryKey: ['alert-history', updated.id] }); setReason(''); setActionMessage(updated.status === 'approved' ? 'Advisory approved. Choose an expiry and publish explicitly.' : 'Advisory rejected and saved.') } })
  const publish = useMutation({ mutationFn: (id: string) => api.publishAlert(id, new Date(expiry).toISOString()), onSuccess: updated => { refresh(); void client.invalidateQueries({ queryKey: ['alert-history', updated.id] }); setActionMessage('Official alert published for the selected cell.') } })
  const withdraw = useMutation({ mutationFn: api.withdrawAlert, onSuccess: updated => { refresh(); void client.invalidateQueries({ queryKey: ['alert-history', updated.id] }); setActionMessage('Published alert withdrawn.') } })
  const expire = useMutation({ mutationFn: api.expireAlert, onSuccess: refresh })
  const save = (event: FormEvent) => { event.preventDefault(); setActionMessage(''); if (editingId && editingPublished) updatePublished.mutate(editingId); else if (editingId) edit.mutate(editingId); else if (!incidentId || linkedIncident) create.mutate({ title, body, level, hazard, localityId: linkedIncident?.localityId ?? localityId, source, incidentId: linkedIncident?.id }) }
  const actionError = create.error || edit.error || updatePublished.error || submit.error || review.error || publish.error || withdraw.error || expire.error
  const workflowBusy = create.isPending || edit.isPending || updatePublished.isPending || submit.isPending || review.isPending || publish.isPending || withdraw.isPending || expire.isPending
  const queue = drafts.data ?? []
  const statusLabel = (item: PublicAlert) => item.status === 'pending_approval' ? 'Ready for authority approval' : readable(item.status)
  return <><PageIntro eyebrow="PUBLIC ALERTS" title="Verified warnings only" description="One authorized authority can draft, approve and publish. Each action is explicit and audited."/><DataBanner/>
    {demo ? <Panel><EmptyState title="Demo alert workflow unavailable" description="Switch to live mode with an authorized account to create and review database-backed alerts." icon={Bell}/></Panel> : <div className="content-grid"><Panel><SectionHeading title={editingId ? editingPublished ? 'Update published alert' : 'Edit your draft' : 'Draft an alert'}/>{incidentId && <p className="body-copy">{linkedReports.isLoading ? 'Loading verified incident…' : linkedReports.error ? `Could not load incident: ${linkedReports.error.message}` : linkedIncident ? `Linked to verified report in ${linkedIncident.localityId}. The advisory remains unpublished until you explicitly approve and publish it.` : 'The linked incident is not verified or cannot be found.'}</p>}<form className="incident-form" onSubmit={save}><label>Title <span className="required-mark">required</span><input required minLength={5} maxLength={160} value={title} onChange={event => setTitle(event.target.value)}/></label><label>Message <span className="required-mark">required</span><textarea required minLength={20} maxLength={4000} value={body} onChange={event => setBody(event.target.value)}/></label><label>Hazard<select value={hazard} onChange={event => setHazard(event.target.value as typeof hazard)}><option value="other">General</option><option value="flood">Flood</option><option value="heat">Heat</option><option value="air_quality">Air quality</option></select></label><label>Risk level<select value={level} onChange={event => setLevel(event.target.value as typeof level)}><option value="low">Low</option><option value="moderate">Moderate</option><option value="high">High</option><option value="severe">Severe</option></select></label><label>Evidence source <span className="required-mark">required</span><input required minLength={3} maxLength={300} value={source} onChange={event => setSource(event.target.value)}/></label><Button type="submit" disabled={workflowBusy || (Boolean(incidentId) && !linkedIncident)}>{editingId ? editingPublished ? 'Save alert update' : 'Save draft edits' : 'Save draft'}</Button>{editingId && <Button type="button" variant="outline" onClick={resetForm}>Cancel editing</Button>}</form>{actionMessage && <p role="status">{actionMessage}</p>}{actionError && <p className="form-error" role="alert">{actionError.message}</p>}</Panel>
      <div className="stack"><Panel><SectionHeading title="Advisory review queue"/>{drafts.isLoading ? <LoadingSkeleton/> : drafts.error ? <ErrorState message={drafts.error.message} onRetry={() => void drafts.refetch()}/> : queue.length ? <div className="alert-list">{queue.map(alert => <div className="alert-row" key={alert.id}><div><RiskBadge level={alert.level}/><strong>{alert.title}</strong><p>{alert.body}</p><small>{alert.localityId} · {statusLabel(alert)} · {alert.source}{alert.incidentId ? ` · Incident ${alert.incidentId}` : ''}</small>{alert.reviewNote && <p>Review: {alert.reviewNote}</p>}</div>
          {alert.status === 'draft' && alert.createdBy === profile?.id && <><Button size="sm" variant="outline" disabled={workflowBusy} onClick={() => { setEditingId(alert.id); setEditingPublished(false); setTitle(alert.title); setBody(alert.body); setSource(alert.source); setLevel(alert.level as typeof level); setHazard((alert.hazard ?? 'other') as typeof hazard) }}>Edit draft</Button><Button size="sm" variant="outline" disabled={workflowBusy} onClick={() => submit.mutate(alert.id)}>Submit for approval</Button></>}
          {alert.status === 'pending_approval' && <><label>Review reason<textarea maxLength={1000} value={reason} onChange={event => setReason(event.target.value)}/></label><Button size="sm" disabled={workflowBusy} onClick={() => review.mutate({ id: alert.id, approve: true, reason })}>Approve advisory</Button><Button size="sm" variant="outline" disabled={workflowBusy || !reason.trim()} onClick={() => review.mutate({ id: alert.id, approve: false, reason })}>Reject</Button></>}
          {alert.status === 'approved' && <><label>Expires at<input type="datetime-local" value={expiry} onChange={event => setExpiry(event.target.value)}/></label><Button size="sm" disabled={workflowBusy || !expiry || Number.isNaN(new Date(expiry).getTime())} onClick={() => { if (window.confirm('Publish this official alert for the selected area? It will be visible to citizens until withdrawn or expired.')) publish.mutate(alert.id) }}>Publish official alert</Button></>}
          <Button size="sm" variant="outline" onClick={() => setHistoryId(alert.id)}>History</Button>
        </div>)}</div> : <EmptyState title="No advisory drafts" description="New drafts will appear here for authority review." icon={Bell}/>}</Panel>
      <Panel><SectionHeading title="Active official alerts"/>{published.isLoading ? <LoadingSkeleton/> : published.error ? <ErrorState message={published.error.message}/> : published.data?.length ? <div className="alert-list">{published.data.map(alert => <div className="alert-row" key={alert.id}><div><RiskBadge level={alert.level}/><strong>{alert.title}</strong><p>{alert.body}</p><small>Approved {alert.approvedAt ? new Date(alert.approvedAt).toLocaleString('en-IN') : '—'} · {alert.source} · Expires {alert.expiresAt ? new Date(alert.expiresAt).toLocaleString('en-IN') : 'not set (legacy alert)'}</small></div><Button size="sm" variant="outline" disabled={workflowBusy} onClick={() => { setEditingId(alert.id); setEditingPublished(true); setTitle(alert.title); setBody(alert.body); setSource(alert.source); setLevel(alert.level as typeof level); setHazard((alert.hazard ?? 'other') as typeof hazard) }}>Update</Button><Button size="sm" variant="outline" disabled={workflowBusy} onClick={() => { if (window.confirm('Withdraw this published alert? It will stop appearing in the citizen alert feed.')) withdraw.mutate(alert.id) }}>Withdraw</Button><Button size="sm" variant="outline" onClick={() => setHistoryId(alert.id)}>History</Button></div>)}</div> : <EmptyState title="No active alerts" description="Only approved, published and unexpired alerts appear here." icon={Bell}/>}</Panel>
      {historyId && <Panel><SectionHeading title="Advisory audit history"/><Button size="sm" variant="outline" onClick={() => setHistoryId(null)}>Close history</Button>{alertHistory.isLoading ? <LoadingSkeleton/> : alertHistory.error ? <ErrorState message={alertHistory.error.message}/> : alertHistory.data?.length ? <ul>{alertHistory.data.map((entry, index) => <li key={`${entry.createdAt}-${index}`}>{new Date(entry.createdAt).toLocaleString('en-IN')} · {entry.action} · {entry.oldStatus && entry.newStatus ? `${readable(entry.oldStatus)} → ${readable(entry.newStatus)}` : entry.changedFields.join(', ')} · Authority {entry.actorId ?? 'unknown'}</li>)}</ul> : <p>No audit entries recorded.</p>}</Panel>}
      <Panel><SectionHeading title="Publication history"/>{archive.isLoading ? <LoadingSkeleton/> : archive.error ? <ErrorState message={archive.error.message}/> : archive.data?.length ? <div className="alert-list">{archive.data.map(alert => { const expired = alert.status === 'published' && alert.expiresAt && new Date(alert.expiresAt) <= new Date(); return <div className="alert-row" key={alert.id}><div><strong>{alert.title}</strong><p>{alert.localityId} · {expired ? 'Expired by time' : statusLabel(alert)}</p><small>{alert.publishedAt ? new Date(alert.publishedAt).toLocaleString('en-IN') : 'Publication time unavailable'}</small></div>{expired && <Button size="sm" variant="outline" disabled={expire.isPending} onClick={() => expire.mutate(alert.id)}>Record expiry</Button>}</div> })}</div> : <EmptyState title="No publication history" description="Published, withdrawn and expired alerts appear here." icon={Bell}/>}</Panel></div></div>}</>
}
