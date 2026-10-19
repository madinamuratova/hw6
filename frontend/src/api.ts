// Every call the dashboard makes to the FastAPI backend. No data is hardcoded in the frontend.
import type { AgentEvent, Cash, Draft, Health, Proposal, RunInfo, Ticket } from './types.ts'

export const API_BASE: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number // 0 means the API could not be reached at all

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// FastAPI sends errors as {"detail": "reason"} or, for invalid input, {"detail": [{"msg": ...}]}.
function detailOf(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string }).msg ?? '').join('; ')
  return null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { headers: { 'Content-Type': 'application/json' }, ...init })
  } catch {
    throw new ApiError(0, `Can't reach the API at ${API_BASE}.`)
  }
  const body: unknown = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, detailOf(body) ?? `Request failed (${res.status}).`)
  return body as T
}

const post = <T>(path: string, body?: object) =>
  request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined })

export const api = {
  health: () => request<Health>('/api/health'),
  tickets: () => request<Ticket[]>('/api/tickets'),
  runTicket: (ticketId: number) => post<RunInfo>(`/api/tickets/${ticketId}/run`),
  resolveTicket: (ticketId: number, name: string) => post(`/api/tickets/${ticketId}/resolve`, { resolved_by: name }),
  run: (runId: string) => request<RunInfo>(`/api/runs/${runId}`),
  events: (ticketId: number) =>
    request<{ events: AgentEvent[] }>(`/api/events?ticket_id=${ticketId}&limit=500`).then((r) => r.events),
  approvals: () => request<Proposal[]>('/api/approvals'),
  approve: (id: number, name: string) => post<{ new_balance: number }>(`/api/approvals/${id}/approve`, { approved_by: name }),
  reject: (id: number, name: string, note: string) => post(`/api/approvals/${id}/reject`, { rejected_by: name, note }),
  cash: () => request<Cash>('/api/cash'),
  drafts: (ticketId: number) => request<Draft[]>(`/api/drafts?ticket_id=${ticketId}`),
  reset: (name: string) => post('/api/reset', { requested_by: name }),
}

export const money = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
export const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
