import { useMutation } from '@tanstack/react-query'
import { CheckCircle2, CircleSlash, Loader2, Ticket } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { api } from '@/api/endpoints'
import type { ProposedAction } from '@/api/schemas'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

/** The escalation proposed with an answer. Nothing is created until the user approves it. */
export function ActionCard({ proposal }: { proposal: ProposedAction }) {
  const [action, setAction] = useState(proposal)
  const decide = useMutation({
    mutationFn: (decision: 'approve' | 'reject') => api.decideAction(action.id, decision),
    onSuccess: (updated) => {
      setAction(updated)
      if (updated.status === 'executed') toast.success(`${updated.label} ${updated.reference} created`)
    },
    onError: (err) => toast.error('The action could not be completed', { description: err.message }),
  })

  return (
    <section aria-label={`Proposed ${action.label}`} className="space-y-2 rounded-xl border border-(--domain)/30 bg-(--domain)/5 px-3 py-2.5">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Ticket className="size-4 text-(--domain)" aria-hidden />
        <span>Suggested: open a {action.label.toLowerCase()}</span>
        <Badge variant="outline">{action.priority}</Badge>
      </div>
      <p className="text-sm">{action.title}</p>
      <p className="text-xs text-muted-foreground">{action.reason}</p>

      {action.status === 'proposed' ? (
        <div className="flex gap-2">
          <Button size="sm" onClick={() => decide.mutate('approve')} disabled={decide.isPending} className="bg-(--domain) text-white hover:bg-(--domain)/90">
            {decide.isPending && decide.variables === 'approve' ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null}
            Approve
          </Button>
          <Button size="sm" variant="outline" onClick={() => decide.mutate('reject')} disabled={decide.isPending}>
            Dismiss
          </Button>
        </div>
      ) : action.status === 'executed' ? (
        <p role="status" className="flex items-center gap-1.5 text-sm font-medium text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="size-4" aria-hidden /> {action.label} {action.reference} created
        </p>
      ) : (
        <p role="status" className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <CircleSlash className="size-4" aria-hidden /> Dismissed, nothing was created
        </p>
      )}
    </section>
  )
}
