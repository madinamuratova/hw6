import { useEffect, useRef, useState } from 'react'
import { ApiError, api, time } from '../api.ts'
import type { Ticket } from '../types.ts'
import { usePolling } from '../usePolling.ts'
import ActivityFeed from './ActivityFeed.tsx'
import { ticketStatus, typeLabel } from './TicketList.tsx'

const OUTCOME_LABELS = { handled: 'Handled', waiting_on_human: 'Waiting on a human', blocked: 'Blocked' }

interface Props {
  ticket: Ticket
  online: boolean
  activeRun: string | null
  name: string
  onChanged: () => void
  notify: (tone: 'ok' | 'error', text: string) => void
}

export default function TicketPanel({ ticket, online, activeRun, name, onChanged, notify }: Props) {
  const [startedRun, setStartedRun] = useState<string | null>(null)
  const [busy, setBusy] = useState<'run' | 'resolve' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const runId = startedRun ?? ticket.last_run?.run_id ?? null
  const serverRunning = !!activeRun && activeRun === runId // from /api/health, polled by App
  const run = usePolling(() => (runId ? api.run(runId) : Promise.resolve(null)), serverRunning ? 1500 : 10000, runId)
  // The run's own status wins once we have it. A run we just started counts as running until the server
  // reports on it, so the buttons can't flicker back on.
  const runKnown = !!runId && run.data?.run_id === runId
  const awaitingFirstStatus = startedRun !== null && !runKnown && !run.error
  const running = runKnown ? run.data!.status === 'running' : serverRunning || awaitingFirstStatus
  const events = usePolling(() => api.events(ticket.id), running ? 1500 : 5000, ticket.id)
  const drafts = usePolling(() => api.drafts(ticket.id), running ? 3000 : 5000, ticket.id)

  // When a run ends, refresh tickets, cash, and approvals once, and fetch the final steps and drafts.
  const wasRunning = useRef(running)
  const { refresh: refreshDrafts } = drafts
  const { refresh: refreshEvents } = events
  useEffect(() => {
    if (wasRunning.current && !running) {
      onChanged()
      void refreshDrafts()
      void refreshEvents()
    }
    wasRunning.current = running
  }, [running, onChanged, refreshDrafts, refreshEvents])

  const runEvents = (events.data ?? []).filter((e) => e.run_id === runId)
  const outcome = run.data?.report?.tickets.find((t) => t.ticket_id === ticket.id)
  // If the API restarted, the run report is gone from memory; the Boss's last words are still in the audit trail.
  const bossSaid = runEvents.filter((e) => e.agent === 'Boss' && e.phase === 'final_output').at(-1)?.said
  const runFailed = run.data?.status === 'failed' || (!run.data && ticket.last_run?.status === 'failed')
  const status = ticketStatus(ticket, activeRun)
  const pending = ticket.pending_proposal_ids.length

  async function startRun() {
    setBusy('run')
    setError(null)
    try {
      const info = await api.runTicket(ticket.id)
      setStartedRun(info.run_id)
      notify('ok', `Agent team started on ticket ${ticket.id}.`)
      onChanged()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  async function markResolved() {
    if (!name.trim()) {
      setError('Enter your name under Approvals before marking a ticket resolved.')
      return
    }
    setBusy('resolve')
    setError(null)
    try {
      await api.resolveTicket(ticket.id, name.trim())
      notify('ok', `Ticket ${ticket.id} marked resolved by ${name.trim()}.`)
      onChanged()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const runBlocked = !online
    ? 'The API is offline.'
    : ticket.status === 'resolved'
      ? 'This ticket is resolved. Reset the data to run it again.'
      : activeRun
        ? 'Another run is going. One run at a time keeps the cash checks honest.'
        : null

  return (
    <section className="panel ticket-panel" aria-labelledby="ticket-heading">
      <header className="ticket-header">
        <div>
          <p className="eyebrow">
            #{ticket.id} · {typeLabel(ticket.type)}
          </p>
          <h2 id="ticket-heading">{ticket.subject}</h2>
        </div>
        <span className={`pill ${status.tone}`}>{status.label}</span>
      </header>

      <dl className="facts">
        <dt>From</dt>
        <dd>{ticket.requester}</dd>
        {ticket.sku && (
          <>
            <dt>Item</dt>
            <dd>
              {ticket.qty} × {ticket.sku} {ticket.size && `size ${ticket.size}`}
            </dd>
          </>
        )}
        {ticket.lease_id !== null && (
          <>
            <dt>Lease</dt>
            <dd>#{ticket.lease_id}</dd>
          </>
        )}
        {ticket.invoice_id !== null && (
          <>
            <dt>Invoice</dt>
            <dd>#{ticket.invoice_id}</dd>
          </>
        )}
        <dt>Notes</dt>
        <dd>{ticket.notes ?? '—'}</dd>
      </dl>

      <div className="actions">
        <button type="button" className="primary" disabled={!!runBlocked || busy !== null} onClick={startRun}>
          {busy === 'run' ? 'Starting…' : runId ? 'Run agent team again' : 'Run agent team'}
        </button>
        {ticket.status === 'open' && runId && !running && pending === 0 && (
          <button type="button" disabled={!online || busy !== null} onClick={markResolved}>
            {busy === 'resolve' ? 'Saving…' : 'Mark resolved'}
          </button>
        )}
        {runBlocked && <span className="hint">{runBlocked}</span>}
      </div>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}

      {runId && (
        <>
          <h3>
            Agent activity {running && <span className="pill busy">working…</span>}
          </h3>
          <ActivityFeed events={runEvents} running={running} />

          <h3>
            What happened
            {!running && run.data?.finished_at && (
              <span className="report-time">Boss's report from the run at {time(run.data.finished_at)}</span>
            )}
          </h3>
          {running && <p className="muted">The Boss will report when the team is done.</p>}
          {runFailed && (
            <p className="error-text" role="alert">
              The run failed{run.data?.error ? `: ${run.data.error}` : '.'}
            </p>
          )}
          {!running && outcome && (
            <div className="outcome">
              <p>
                <span className={`pill ${outcome.status === 'handled' ? 'ok' : outcome.status === 'blocked' ? 'bad' : 'wait'}`}>
                  {OUTCOME_LABELS[outcome.status]}
                </span>
              </p>
              <p>{outcome.summary}</p>
              {!!outcome.actions_taken.length && (
                <>
                  <h4>Done by the agents</h4>
                  <ul>{outcome.actions_taken.map((a, i) => <li key={i}>{a}</li>)}</ul>
                </>
              )}
              {!!outcome.human_decisions_needed.length && (
                <>
                  <h4>Needs a human</h4>
                  <ul>{outcome.human_decisions_needed.map((a, i) => <li key={i}>{a}</li>)}</ul>
                </>
              )}
              {run.data?.usage && (
                <p className="muted small">
                  {run.data.usage.requests} model requests · {run.data.usage.tool_calls} tool calls ·{' '}
                  {run.data.usage.input_tokens.toLocaleString()} input / {run.data.usage.output_tokens.toLocaleString()} output tokens
                </p>
              )}
            </div>
          )}
          {!running && !outcome && !runFailed && bossSaid && <p className="outcome">{bossSaid}</p>}
          {pending > 0 && !running && (
            <p className="hint">
              {pending} proposal{pending > 1 ? 's' : ''} for this ticket {pending > 1 ? 'are' : 'is'} waiting for your
              approval on the right.
            </p>
          )}
        </>
      )}

      <h3>Drafts</h3>
      {drafts.data === null && !drafts.error && <p className="muted">Loading drafts…</p>}
      {drafts.data?.length === 0 && <p className="muted">No drafts for this ticket yet.</p>}
      {drafts.data?.map((d) => (
        <article key={d.draft_id} className="draft">
          <p className="draft-head">
            <strong>To {d.to}</strong> · {d.subject} <span className="pill neutral">Draft, not sent</span>
          </p>
          <p className="draft-body">{d.body}</p>
        </article>
      ))}
    </section>
  )
}
