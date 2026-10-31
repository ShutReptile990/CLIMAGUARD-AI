import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, CircleAlert, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
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
        {detail.status === 'submitted' && <Button type="button" disabled={review.isPending} onClick={() => review.mutate({ id: detail.id, next: 'under_review' })}>Start review</Button>}
        {detail.status === 'under_review' && <><label>Review reason or note<textarea maxLength={1000} value={note} onChange={event => setNote(event.target.value)}/></label><div className="table-toolbar"><Button type="button" disabled={review.isPending} onClick={() => review.mutate({ id: detail.id, next: 'resolved', reason: note })}>Verify report</Button><Button type="button" variant="outline" disabled={review.isPending || !note.trim()} onClick={() => review.mutate({ id: detail.id, next: 'rejected', reason: note })}>Reject with reason</Button></div></>}
        {review.error && <p className="form-error" role="alert">{review.error.message}</p>}</div>}
    </Panel>}</>
}

export function Alerts() {
  const { demo, localityId } = useClimate()
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
  const [reason, setReason] = useState('')
  const [expiry, setExpiry] = useState('')
  const refresh = () => { void client.invalidateQueries({ queryKey: ['alert-drafts'] }); void client.invalidateQueries({ queryKey: ['alerts'] }); void client.invalidateQueries({ queryKey: ['alert-archive'] }) }
  const create = useMutation({ mutationFn: api.createAlert, onSuccess: () => { refresh(); setTitle(''); setBody(''); setSource('') } })
  const edit = useMutation({ mutationFn: (id: string) => api.editAlert(id, { title, body, level, hazard, source }), onSuccess: () => { refresh(); setEditingId(null); setTitle(''); setBody(''); setSource('') } })
  const submit = useMutation({ mutationFn: api.submitAlert, onSuccess: refresh })
  const review = useMutation({ mutationFn: ({ id, approve, reason }: { id: string; approve: boolean; reason?: string }) => api.reviewAlert(id, approve, reason), onSuccess: () => { refresh(); setReason('') } })
  const publish = useMutation({ mutationFn: (id: string) => api.publishAlert(id, new Date(expiry).toISOString()), onSuccess: refresh })
  const withdraw = useMutation({ mutationFn: api.withdrawAlert, onSuccess: refresh })
  const expire = useMutation({ mutationFn: api.expireAlert, onSuccess: refresh })
  const save = (event: FormEvent) => { event.preventDefault(); if (editingId) edit.mutate(editingId); else create.mutate({ title, body, level, hazard, localityId, source }) }
  const actionError = create.error || edit.error || submit.error || review.error || publish.error || withdraw.error || expire.error
  const queue = drafts.data ?? []
  const statusLabel = (item: PublicAlert) => readable(item.status)
  return <><PageIntro eyebrow="PUBLIC ALERTS" title="Verified warnings only" description="Drafts require submission, independent approval and an expiry before publication."/><DataBanner/>
    {demo ? <Panel><EmptyState title="Demo alert workflow unavailable" description="Switch to live mode with an authorized account to create and review database-backed alerts." icon={Bell}/></Panel> : <div className="content-grid"><Panel><SectionHeading title={editingId ? 'Edit your draft' : 'Draft an alert'}/><form className="incident-form" onSubmit={save}><label>Title<input required minLength={5} maxLength={160} value={title} onChange={event => setTitle(event.target.value)}/></label><label>Message<textarea required minLength={20} maxLength={4000} value={body} onChange={event => setBody(event.target.value)}/></label><label>Hazard<select value={hazard} onChange={event => setHazard(event.target.value as typeof hazard)}><option value="other">General</option><option value="flood">Flood</option><option value="heat">Heat</option><option value="air_quality">Air quality</option></select></label><label>Risk level<select value={level} onChange={event => setLevel(event.target.value as typeof level)}><option value="low">Low</option><option value="moderate">Moderate</option><option value="high">High</option><option value="severe">Severe</option></select></label><label>Evidence source<input required minLength={3} maxLength={300} value={source} onChange={event => setSource(event.target.value)}/></label><Button type="submit" disabled={create.isPending || edit.isPending}>{editingId ? 'Save edits' : 'Save draft'}</Button>{editingId && <Button type="button" variant="outline" onClick={() => setEditingId(null)}>Cancel editing</Button>}</form>{actionError && <p className="form-error" role="alert">{actionError.message}</p>}</Panel>
      <div className="stack"><Panel><SectionHeading title="Approval queue"/>{drafts.isLoading ? <LoadingSkeleton/> : drafts.error ? <ErrorState message={drafts.error.message} onRetry={() => void drafts.refetch()}/> : queue.length ? <div className="alert-list">{queue.map(alert => <div className="alert-row" key={alert.id}><div><RiskBadge level={alert.level}/><strong>{alert.title}</strong><p>{alert.body}</p><small>{alert.localityId} · {statusLabel(alert)} · {alert.source}</small>{alert.reviewNote && <p>Review: {alert.reviewNote}</p>}</div>
          {alert.status === 'draft' && alert.createdBy === profile?.id && <><Button size="sm" variant="outline" onClick={() => { setEditingId(alert.id); setTitle(alert.title); setBody(alert.body); setSource(alert.source); setLevel(alert.level as typeof level); setHazard((alert.hazard ?? 'other') as typeof hazard) }}>Edit draft</Button><Button size="sm" variant="outline" disabled={submit.isPending} onClick={() => submit.mutate(alert.id)}>Submit for approval</Button></>}
          {alert.status === 'pending_approval' && alert.createdBy !== profile?.id && <><label>Review reason<textarea maxLength={1000} value={reason} onChange={event => setReason(event.target.value)}/></label><Button size="sm" disabled={review.isPending} onClick={() => review.mutate({ id: alert.id, approve: true, reason })}>Approve</Button><Button size="sm" variant="outline" disabled={review.isPending || !reason.trim()} onClick={() => review.mutate({ id: alert.id, approve: false, reason })}>Reject</Button></>}
          {alert.status === 'approved' && <><label>Expires at<input type="datetime-local" value={expiry} onChange={event => setExpiry(event.target.value)}/></label><Button size="sm" disabled={publish.isPending || !expiry || Number.isNaN(new Date(expiry).getTime())} onClick={() => publish.mutate(alert.id)}>Publish approved alert</Button></>}
        </div>)}</div> : <EmptyState title="No advisory drafts" description="New drafts will appear here for independent review." icon={Bell}/>}</Panel>
      <Panel><SectionHeading title="Active official alerts"/>{published.isLoading ? <LoadingSkeleton/> : published.error ? <ErrorState message={published.error.message}/> : published.data?.length ? <div className="alert-list">{published.data.map(alert => <div className="alert-row" key={alert.id}><div><RiskBadge level={alert.level}/><strong>{alert.title}</strong><p>{alert.body}</p><small>Approved {alert.approvedAt ? new Date(alert.approvedAt).toLocaleString('en-IN') : '—'} · {alert.source} · Expires {alert.expiresAt ? new Date(alert.expiresAt).toLocaleString('en-IN') : 'not set (legacy alert)'}</small></div><Button size="sm" variant="outline" disabled={withdraw.isPending} onClick={() => withdraw.mutate(alert.id)}>Withdraw</Button></div>)}</div> : <EmptyState title="No active alerts" description="Only approved, published and unexpired alerts appear here." icon={Bell}/>}</Panel>
      <Panel><SectionHeading title="Publication history"/>{archive.isLoading ? <LoadingSkeleton/> : archive.error ? <ErrorState message={archive.error.message}/> : archive.data?.length ? <div className="alert-list">{archive.data.map(alert => { const expired = alert.status === 'published' && alert.expiresAt && new Date(alert.expiresAt) <= new Date(); return <div className="alert-row" key={alert.id}><div><strong>{alert.title}</strong><p>{alert.localityId} · {expired ? 'Expired by time' : statusLabel(alert)}</p><small>{alert.publishedAt ? new Date(alert.publishedAt).toLocaleString('en-IN') : 'Publication time unavailable'}</small></div>{expired && <Button size="sm" variant="outline" disabled={expire.isPending} onClick={() => expire.mutate(alert.id)}>Record expiry</Button>}</div> })}</div> : <EmptyState title="No publication history" description="Published, withdrawn and expired alerts appear here." icon={Bell}/>}</Panel></div></div>}</>
}
