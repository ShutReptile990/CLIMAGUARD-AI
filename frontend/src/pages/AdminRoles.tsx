import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { UsersRound } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth, type Profile } from '../auth'
import { EmptyState, ErrorState, LoadingSkeleton, Panel, SectionHeading } from '../components/Shared'
import { Button } from '../components/ui/button'

export function AdminRoles() {
  const { profile } = useAuth()
  const query = useQuery({ queryKey: ['profiles'], queryFn: api.profiles })
  const client = useQueryClient()
  const [pending, setPending] = useState<Record<string, Profile['role']>>({})
  const mutation = useMutation({ mutationFn: ({ id, role }: { id: string; role: Profile['role'] }) => api.assignRole(id, role), onSuccess: () => void client.invalidateQueries({ queryKey: ['profiles'] }) })
  return <><div className="page-intro"><span className="eyebrow">ADMINISTRATION</span><h1>Role management</h1><p>Assign authority access only to verified team members.</p></div><Panel><SectionHeading title="Accounts"/>{query.isLoading ? <LoadingSkeleton/> : query.error ? <ErrorState message={query.error.message} onRetry={() => void query.refetch()}/> : query.data?.length ? <div className="role-list">{query.data.map(item => <div className="role-row" key={item.id}><div><strong>{item.display_name || item.id}</strong><span>{item.id}</span></div><label><span className="sr-only">Role for {item.display_name || item.id}</span><select disabled={item.id === profile?.id} value={pending[item.id] ?? item.role} onChange={e => setPending(prev => ({ ...prev, [item.id]: e.target.value as Profile['role'] }))}><option value="citizen">Citizen</option><option value="authority">Authority</option><option value="admin">Admin</option></select></label><Button size="sm" variant="outline" disabled={mutation.isPending || item.id === profile?.id || !pending[item.id] || pending[item.id] === item.role} onClick={() => mutation.mutate({ id: item.id, role: pending[item.id] })}>Save role</Button></div>)}</div> : <EmptyState title="No accounts found" description="New Supabase Auth users will appear here after registration." icon={UsersRound}/ >}{mutation.error && <p className="form-error" role="alert">{mutation.error.message}</p>}</Panel></>
}
