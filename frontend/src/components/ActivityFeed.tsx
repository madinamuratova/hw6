import { useEffect, useRef } from 'react'
import { time } from '../api.ts'
import type { AgentEvent } from '../types.ts'

// Steps worth showing a person; "sent the task to the model" bookkeeping steps are left out.
const SHOWN = new Set(['system_start', 'agent_start', 'model_response', 'final_output', 'system_end', 'system_error', 'error'])

const agentClass = (agent: string) => `agent agent-${agent.toLowerCase().replace(/\s+/g, '-')}`

function shortArgs(args: Record<string, unknown>): string {
  const text = Object.entries(args)
    .filter(([k]) => !['reason', 'body', 'proposed_by'].includes(k))
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(', ')
  return text.length > 80 ? `${text.slice(0, 80)}…` : text
}

interface Props {
  events: AgentEvent[]
  running: boolean
}

export default function ActivityFeed({ events, running }: Props) {
  const shown = events.filter((e) => SHOWN.has(e.phase))
  const end = useRef<HTMLLIElement>(null)

  useEffect(() => {
    if (running) end.current?.scrollIntoView({ block: 'nearest' })
  }, [shown.length, running])

  if (!shown.length) {
    return <p className="muted">{running ? 'Waiting for the first agent step…' : 'No agent activity for this run.'}</p>
  }

  return (
    <ol className="feed" aria-live="polite">
      {shown.map((e) => (
        <li key={e.id} className={`feed-item depth-${Math.min(e.depth ?? 0, 2)}${e.phase.includes('error') ? ' error' : ''}`}>
          <div className="feed-head">
            <span className={agentClass(e.agent)}>{e.agent}</span>
            <span className="feed-action">{e.action}</span>
            <time className="muted">{time(e.timestamp)}</time>
          </div>
          {e.delegated_to?.map((to, i) => (
            <p key={i} className="feed-detail">
              → <strong>{to.replace('_', ' ')}</strong>: {e.delegation_tasks?.[i]}
            </p>
          ))}
          {!!e.tools_called?.length && (
            <div className="chips">
              {e.tools_called.map((c, i) => (
                <code key={i} className="chip" title={JSON.stringify(c.args)}>
                  {c.tool}({shortArgs(c.args)})
                </code>
              ))}
            </div>
          )}
          {e.said && e.phase !== 'model_response' && <p className="feed-said">{e.said}</p>}
        </li>
      ))}
      <li ref={end} className="feed-end" aria-hidden="true" />
    </ol>
  )
}
