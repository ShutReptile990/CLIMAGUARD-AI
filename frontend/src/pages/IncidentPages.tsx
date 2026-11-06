import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, ChevronRight, Send, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { supabase } from '../lib/supabase'
import { useClimate } from '../context'
import { useAuth } from '../auth'
import { useIncidents } from '../lib/hooks'
import type { Incident, IncidentCategory } from '../types'
import { Button } from '../components/ui/button'
import { EmptyState, ErrorState, LoadingSkeleton, Panel, SectionHeading } from '../components/Shared'
import { DataBanner, PageIntro } from './Citizen'

const imageTypes: Record<string, string> = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' }
export function IncidentForm() {
  const { localityId, demo, addDemoReport } = useClimate()
  const { session } = useAuth()
  const client = useQueryClient()
  const [category, setCategory] = useState<IncidentCategory>('flood')
  const [severity, setSeverity] = useState<'low' | 'moderate' | 'high' | 'severe'>('moderate')
  const [description, setDescription] = useState('')
  const [contact, setContact] = useState('')
  const [image, setImage] = useState<File | null>(null)
  const [fileError, setFileError] = useState('')
  const [descriptionError, setDescriptionError] = useState('')
  const [sent, setSent] = useState(false)
  const mutation = useMutation({ mutationFn: async () => {
    if (!session || !supabase) throw new Error('Sign in to submit a live report.')
    let image_path: string | undefined
    if (image) {
      const extension = imageTypes[image.type]
      if (!extension || image.size > 5 * 1024 * 1024) throw new Error('Use a JPEG, PNG or WebP image no larger than 5 MB.')
      image_path = `${session.user.id}/${crypto.randomUUID()}.${extension}`
      const uploaded = await supabase.storage.from('incident-evidence').upload(image_path, image, { contentType: image.type, upsert: false })
      if (uploaded.error) throw new Error(`Private evidence upload failed: ${uploaded.error.message}`)
    }
    try { return await api.submitIncident({ localityId, category, severity, description: description.trim(), contact: contact.trim() || undefined, image_path }) }
    catch (error) { if (image_path) await supabase.storage.from('incident-evidence').remove([image_path]); throw error }
  }, onSuccess: () => { void client.invalidateQueries({ queryKey: ['incidents'] }); setSent(true); setDescription(''); setContact(''); setImage(null) } })
  const submit = (event: FormEvent) => {
    event.preventDefault(); setSent(false)
    if (description.trim().length < 20) { setDescriptionError('Please describe what happened in at least 20 non-space characters.'); return }
    setDescriptionError('')
    if (demo) {
      addDemoReport({ id: crypto.randomUUID(), localityId, category, severity, description: description.trim(), createdAt: new Date().toISOString(), status: 'submitted', contact: contact.trim() || null })
      setSent(true); setDescription(''); setContact(''); setImage(null)
    } else mutation.mutate()
  }
  return <><PageIntro eyebrow="REPORT INCIDENT" title="Tell us what you observed" description="Reports are unverified until an authorized reviewer checks them. Avoid exact home addresses."/><DataBanner/><div className="form-layout"><Panel><SectionHeading title="Incident details"/><form onSubmit={submit} className="incident-form">
    <label>Selected area<input value={localityId} disabled/></label>
    <label>Type of incident<select value={category} onChange={event => setCategory(event.target.value as IncidentCategory)}><option value="flood">Flooding</option><option value="waterlogging">Waterlogging</option><option value="blocked_road">Blocked road</option><option value="fallen_tree">Fallen tree</option><option value="heat">Extreme heat concern</option><option value="air_quality">Air pollution concern</option><option value="other">Other environmental hazard</option></select></label>
    <label>Reporter severity<select value={severity} onChange={event => setSeverity(event.target.value as typeof severity)}><option value="low">Low</option><option value="moderate">Moderate</option><option value="high">High</option><option value="severe">Severe</option></select></label>
    <label>What happened? <span className="required-mark">required</span><textarea required minLength={20} maxLength={2000} aria-invalid={Boolean(descriptionError)} aria-describedby={descriptionError ? 'incident-description-error' : 'incident-description-help'} value={description} onChange={event => { setDescription(event.target.value); setDescriptionError('') }} placeholder="Describe what you observed and when, without sharing a home address."/><small id="incident-description-help">At least 20 characters. Reporter severity is unverified.</small></label>
    <label>Evidence image <span className="optional">optional</span><input type="file" accept="image/jpeg,image/png,image/webp" disabled={demo} onChange={event => { const file = event.target.files?.[0] ?? null; setFileError(file && (!imageTypes[file.type] || file.size > 5 * 1024 * 1024) ? 'Use a JPEG, PNG or WebP image no larger than 5 MB.' : ''); setImage(file) }}/><small>Private storage, maximum 5 MB. Available in live mode after migration 008.</small></label>
    <label>Contact information <span className="optional">optional</span><input value={contact} onChange={event => setContact(event.target.value)} maxLength={120}/></label>
    <Button type="submit" disabled={mutation.isPending || Boolean(fileError)}><Send size={16}/>{mutation.isPending ? 'Submitting…' : demo ? 'Save demo report' : 'Submit report'}</Button>
    {descriptionError && <p id="incident-description-error" className="form-error" role="alert">{descriptionError}</p>}{fileError && <p className="form-error" role="alert">{fileError}</p>}{mutation.error && <p className="form-error" role="alert">{mutation.error.message}</p>}{sent && <p className="form-success" role="status"><CheckCircle2 size={17}/>{demo ? 'Demo report saved on this device.' : 'Report persisted as unverified. Track it in My Reports.'}</p>}
  </form></Panel><Panel className="aside-info"><span className="safety-icon"><ShieldCheck size={24}/></span><h2>What happens next?</h2><div className="step"><span>01</span><p>Your report is recorded as unverified.</p></div><div className="step"><span>02</span><p>An authorized team reviews the details and evidence.</p></div><div className="step"><span>03</span><p>Verification does not automatically create an official warning or flood training label.</p></div><p className="disclaimer">For an immediate emergency, contact local emergency services directly. This form is not a dispatch channel.</p></Panel></div></>
}

function EvidenceLink({ report }: { report: Incident }) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState('')
  if (!report.image_path) return null
  return <><Button type="button" size="sm" variant="outline" onClick={async () => { if (!supabase) return; const result = await supabase.storage.from('incident-evidence').createSignedUrl(report.image_path!, 60); if (result.error) setError(result.error.message); else setUrl(result.data.signedUrl) }}>View private image</Button>{url && <img src={url} alt="Your submitted incident evidence" style={{ maxWidth: '100%', maxHeight: 320 }}/ >}{error && <p role="alert" className="form-error">{error}</p>}</>
}

function ReportHistory({ id }: { id: string }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['incident-history', id], queryFn: () => api.incidentHistory(id), enabled: open })
  return <div><Button type="button" size="sm" variant="outline" onClick={() => setOpen(value => !value)}>{open ? 'Hide status history' : 'View status history'}</Button>{open && (query.isLoading ? <p>Loading history…</p> : query.error ? <p role="alert">{query.error.message}</p> : query.data?.length ? <ul>{query.data.map((entry, index) => <li key={`${entry.created_at}-${index}`}>{new Date(entry.created_at).toLocaleString('en-IN')}: {entry.old_status.replaceAll('_', ' ')} → {entry.new_status.replaceAll('_', ' ')}</li>)}</ul> : <p>No status changes yet.</p>)}</div>
}

export function MyReports() {
  const { demo, demoReports } = useClimate()
  const { session } = useAuth()
  const query = useIncidents(!demo && Boolean(session))
  const reports = demo ? demoReports : query.data ?? []
  return <><PageIntro eyebrow="MY REPORTS" title="Your submitted reports" description={demo ? 'Demo reports are saved on this device only.' : 'Live reports are private to you and authorized reviewers.'}/><DataBanner/>{query.isLoading && !demo ? <LoadingSkeleton/> : query.error && !demo ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()}/> : reports.length ? <div className="report-list">{reports.map(report => <Panel key={report.id} className="report-item"><div><span className="eyebrow">{report.category.replaceAll('_', ' ').toUpperCase()}{demo ? ' · DEMO' : ''}</span><h2>{report.description}</h2><p>{new Date(report.createdAt).toLocaleString('en-IN')} · {report.localityId} · Severity reported: {report.severity ?? 'not recorded'}</p>{report.review_note && <p>Review note: {report.review_note}</p>}{report.reviewed_at && <p>Reviewed {new Date(report.reviewed_at).toLocaleString('en-IN')}</p>}<EvidenceLink report={report}/>{!demo && <ReportHistory id={report.id}/>}</div><span className="pending-tag">{demo ? 'Saved locally' : report.status === 'submitted' ? 'Unverified' : report.status === 'resolved' ? 'Verified' : report.status.replaceAll('_', ' ')}</span></Panel>)}</div> : <Panel><EmptyState title="No reports to show" description="Your reports will appear here after a successful submission." icon={Send}/><div className="empty-action"><Button asChild><Link to="/citizen/report">Report an incident <ChevronRight size={16}/></Link></Button></div></Panel>}</>
}
