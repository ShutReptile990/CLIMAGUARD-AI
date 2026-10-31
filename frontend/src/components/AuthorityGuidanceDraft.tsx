import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import type { NugenGuidance } from '../types'
import { api } from '../lib/api'
import { Button } from './ui/button'

export function AuthorityGuidanceDraft({ guidance }: { guidance: NugenGuidance }) {
  const client = useQueryClient()
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [level, setLevel] = useState<'low' | 'moderate' | 'high' | 'severe'>('moderate')
  const [hazard, setHazard] = useState<'flood' | 'heat' | 'air_quality' | 'other'>('other')
  const [source, setSource] = useState('')
  useEffect(() => {
    setTitle(`Preparedness update for ${guidance.locality_name}`)
    setBody(`${guidance.guidance.summary}\n\n${guidance.guidance.actions.join('\n')}\n\n${guidance.guidance.limitations}`)
    setSource(`Nugen ${guidance.model_id}; request ${guidance.provider_request_id ?? 'unavailable'}; live screening ${guidance.inferred_at}`)
  }, [guidance])
  const create = useMutation({ mutationFn: api.createAlert, onSuccess: () => void client.invalidateQueries({ queryKey: ['alert-drafts'] }) })
  const submit = (event: FormEvent) => { event.preventDefault(); create.mutate({ title, body, level, hazard, localityId: guidance.locality_id, source }) }
  return <section className="panel section-block"><h2>Review an advisory draft</h2><p className="disclaimer">Edit and verify every claim before saving. Saving creates an unpublished draft. A different authority reviewer must approve publication.</p>
    <form className="incident-form" onSubmit={submit}>
      <label>Title<input required minLength={5} maxLength={160} value={title} onChange={event => setTitle(event.target.value)}/></label>
      <label>Message<textarea required minLength={20} maxLength={4000} value={body} onChange={event => setBody(event.target.value)}/></label>
      <label>Risk level<select value={level} onChange={event => setLevel(event.target.value as typeof level)}><option value="low">Low</option><option value="moderate">Moderate</option><option value="high">High</option><option value="severe">Severe</option></select></label>
      <label>Hazard<select value={hazard} onChange={event => setHazard(event.target.value as typeof hazard)}><option value="other">General</option><option value="flood">Flood</option><option value="heat">Heat</option><option value="air_quality">Air quality</option></select></label>
      <label>Evidence source<input required minLength={3} maxLength={300} value={source} onChange={event => setSource(event.target.value)}/></label>
      <Button type="submit" disabled={create.isPending || create.isSuccess}>Save for authority review</Button>
      {create.error && <p role="alert" className="form-error">{create.error.message}</p>}
      {create.isSuccess && <p role="status">Draft saved. <Link to="/authority/alerts">Open the alert review queue</Link>.</p>}
    </form>
  </section>
}
