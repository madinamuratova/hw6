import type { Ticket } from '../types.ts'

const TYPE_LABELS: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price request',
}

export const typeLabel = (type: string) => TYPE_LABELS[type] ?? type.replace(/_/g, ' ')

/** Status text and color for a ticket, from the API's status, pending proposals, and active run. */
export function ticketStatus(ticket: Ticket, activeRun: string | null): { label: string; tone: string } {
  if (ticket.status === 'resolved') return { label: 'Resolved', tone: 'ok' }
  if (activeRun && ticket.last_run?.run_id === activeRun) return { label: 'Agents working', tone: 'busy' }
  const n = ticket.pending_proposal_ids.length
  if (n) return { label: `${n} waiting for approval`, tone: 'wait' }
  return { label: 'Open', tone: 'neutral' }
}

interface Props {
  tickets: Ticket[] | null
  selectedId: number | null
  activeRun: string | null
  onSelect: (id: number) => void
}

export default function TicketList({ tickets, selectedId, activeRun, onSelect }: Props) {
  return (
    <section className="panel" aria-labelledby="tickets-heading">
      <h2 id="tickets-heading">Tickets</h2>
      {tickets === null && <p className="muted">Loading tickets…</p>}
      {tickets?.length === 0 && <p className="muted">No tickets in the database.</p>}
      <ul className="ticket-list">
        {tickets?.map((t) => {
          const status = ticketStatus(t, activeRun)
          return (
            <li key={t.id}>
              <button
                type="button"
                className={`ticket-row${t.id === selectedId ? ' selected' : ''}`}
                aria-pressed={t.id === selectedId}
                onClick={() => onSelect(t.id)}
              >
                <span className="ticket-id">#{t.id}</span>
                <span className="ticket-subject">{t.subject}</span>
                <span className="ticket-meta">
                  {typeLabel(t.type)} · {t.requester}
                </span>
                <span className={`pill ${status.tone}`}>{status.label}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
