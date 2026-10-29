import { AlertTriangle, Check, Copy, ListTree, Loader2, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import type { ChatMessage } from '@/hooks/use-chat'
import { nextStatus } from '@/lib/trace'
import { cn } from '@/lib/utils'
import { ActionCard } from './ActionCard'
import { Citations } from './Citations'
import { Markdown } from './Markdown'
import { SourceBadges } from './SourceBadges'
import { TriageBadges } from './TriageBadges'

interface Props {
  message: ChatMessage
  webWarning: string
  selected: boolean
  onShowTrace: () => void
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <Button variant="ghost" size="icon-xs" onClick={copy} aria-label="Copy answer">
      {copied ? <Check /> : <Copy />}
    </Button>
  )
}

export function MessageItem({ message, webWarning, selected, onShowTrace }: Props) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-(--domain) px-4 py-2.5 text-sm whitespace-pre-wrap text-white shadow-sm">
          {message.content}
        </div>
      </div>
    )
  }

  const streaming = message.status === 'streaming'
  return (
    <div className="flex gap-3">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-(--domain)/15 text-(--domain)">
        <Sparkles className="size-4" aria-hidden />
      </div>
      <div
        className={cn(
          'min-w-0 flex-1 space-y-3 rounded-2xl rounded-tl-md border bg-card px-4 py-3 shadow-sm transition-colors',
          selected && 'ring-2 ring-(--domain)/30',
        )}
      >
        {streaming ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            {nextStatus(message.steps.at(-1))}
          </div>
        ) : message.status === 'error' ? (
          <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
            {message.content}
          </div>
        ) : (
          <>
            <TriageBadges triage={message.response?.triage} />
            <Markdown>{message.content}</Markdown>
            {message.sourceUsed === 'web_search' && (
              <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
                {webWarning}
              </p>
            )}
            <Citations citations={message.citations} />
            {message.response?.proposed_action ? <ActionCard proposal={message.response.proposed_action} /> : null}
            <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-2">
              <SourceBadges source={message.sourceUsed} support={message.response?.support_status} />
              <div className="flex items-center gap-1">
                {message.steps.length > 0 && (
                  <Button variant="ghost" size="xs" onClick={onShowTrace}>
                    <ListTree data-icon="inline-start" /> Trace
                  </Button>
                )}
                <CopyButton text={message.content} />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
