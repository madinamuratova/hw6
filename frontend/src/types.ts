// Shapes of the JSON returned by the FastAPI backend (backend/main.py).

export interface Health {
  ok: boolean
  model: string
  database: string
  active_run: string | null
}

export interface RunSummary {
  run_id: string
  status: 'running' | 'finished' | 'failed' | 'unknown'
  started_at: string
  finished_at: string | null
}

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: 'open' | 'resolved'
  notes: string | null
  created_at: string
  pending_proposal_ids: number[]
  last_run: RunSummary | null
}

export interface TicketOutcome {
  ticket_id: number
  status: 'handled' | 'waiting_on_human' | 'blocked'
  summary: string
  actions_taken: string[]
  human_decisions_needed: string[]
}

export interface ShiftReport {
  shop_date: string
  tickets: TicketOutcome[]
  payments_made: string[]
  drafts_saved: string[]
  notes: string[]
}

export interface RunInfo {
  run_id: string
  ticket_id: number
  status: 'running' | 'finished' | 'failed'
  started_at: string
  finished_at: string | null
  report: ShiftReport | null
  error: string | null
  usage: Record<string, number> | null
}

export interface AgentEvent {
  id: number
  timestamp: string
  run_id: string
  ticket_id: number | null
  agent: string
  depth: number
  called_by: string | null
  phase: string
  action: string
  said?: string | null
  delegated_to?: string[]
  delegation_tasks?: string[]
  tools_called?: { tool: string; args: Record<string, unknown> }[]
}

export interface Proposal {
  id: number
  kind: 'invoice' | 'rent' | 'purchase' | 'price_override'
  ref_id: number
  sku: string | null
  size: string | null
  qty: number | null
  unit_price: number | null
  amount: number
  account: string
  ticket_id: number | null
  reason: string | null
  proposed_by: string
  status: 'pending' | 'approved' | 'rejected'
}

export interface Payment {
  id: number
  kind: string
  ref_id: number
  amount: number
  account: string
  paid_at: string
  approved_by: string
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  today: string
  pending_total: number
  balance_if_all_pending_approved: number
  recent_payments: Payment[]
}

export interface Draft {
  draft_id: number
  created_at: string
  kind: string
  ticket_id: number | null
  to: string
  subject: string
  body: string
  status: string
}
