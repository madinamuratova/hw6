import { useState } from 'react'
import { ApiError, api, money } from '../api.ts'
import type { Cash, Proposal } from '../types.ts'

function describe(p: Proposal): string {
  switch (p.kind) {
    case 'invoice':
      return `Pay invoice #${p.ref_id}`
    case 'rent':
      return `Pay rent for lease #${p.ref_id}`
    case 'purchase':
      return `Buy ${p.qty} × ${p.sku} size ${p.size}`
    case 'price_override':
      return `Sell ${p.qty} × ${p.sku} size ${p.size} at ${money(p.unit_price ?? 0)} each`
  }
}

interface Props {
  proposals: Proposal[] | null
  loadError: string | null
  cash: Cash | null
  name: string
  setName: (name: string) => void
  online: boolean
  onDecided: () => void
  notify: (tone: 'ok' | 'error', text: string) => void
}

export default function ApprovalsPanel({ proposals, loadError, cash, name, setName, online, onDecided, notify }: Props) {
  const [busy, setBusy] = useState<number | null>(null)
  const [errors, setErrors] = useState<Record<number, string>>({})
  const [rejecting, setRejecting] = useState<number | null>(null)
  const [note, setNote] = useState('')

  const setError = (id: number, text: string | null) =>
    setErrors((prev) => {
      const next = { ...prev }
      if (text) next[id] = text
      else delete next[id]
      return next
    })

  async function decide(p: Proposal, action: 'approve' | 'reject') {
    const who = name.trim()
    if (!who) {
      setError(p.id, `Enter your name above to ${action}.`)
      return
    }
    setBusy(p.id)
    setError(p.id, null)
    try {
      if (action === 'approve') {
        // Only the server's answer counts: it re-checks cash and the shop rules before paying.
        const result = await api.approve(p.id, who)
        notify(
          'ok',
          p.kind === 'price_override'
            ? `Approved proposal #${p.id}: price recorded, no cash moved.`
            : `Approved proposal #${p.id}: paid ${money(p.amount)}. Checking is now ${money(result.new_balance)}.`,
        )
      } else {
        await api.reject(p.id, who, note.trim())
        notify('ok', `Rejected proposal #${p.id}. No cash moved.`)
        setRejecting(null)
        setNote('')
      }
      onDecided()
    } catch (e) {
      const message = e instanceof ApiError ? e.message : String(e)
      setError(p.id, `Not ${action === 'approve' ? 'approved' : 'rejected'}: ${message}`)
      notify('error', `Proposal #${p.id} was not ${action === 'approve' ? 'approved' : 'rejected'}.`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="panel" aria-labelledby="approvals-heading">
      <h2 id="approvals-heading">Approvals</h2>
      <p className="muted small">
        Agents can only propose payments, purchases, and prices. Nothing is paid until a person approves it here.
      </p>
      <label className="field">
        <span>Your name (signs each decision)</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your full name" autoComplete="name" />
      </label>

      {loadError && <p className="error-text">{loadError}</p>}
      {proposals === null && !loadError && <p className="muted">Loading proposals…</p>}
      {proposals?.length === 0 && <p className="muted">Nothing is waiting for approval.</p>}

      <ul className="proposal-list">
        {proposals?.map((p) => {
          const movesCash = p.kind !== 'price_override'
          const after = cash && movesCash ? cash.balance - p.amount : null
          return (
            <li key={p.id} className="proposal">
              <p className="proposal-title">
                <strong>{describe(p)}</strong>
                <span className="muted small"> · #{p.id}{p.ticket_id ? ` · ticket ${p.ticket_id}` : ''}</span>
              </p>
              <p className="amount">{movesCash ? money(p.amount) : 'No cash moves'}</p>
              {after !== null && (
                <p className={`small ${after < 0 ? 'error-text' : 'muted'}`}>
                  Checking {money(cash!.balance)} → {money(after)} if approved
                  {after < 0 && ' (not enough cash; the server will refuse)'}
                </p>
              )}
              {p.reason && <p className="small">{p.reason}</p>}
              <p className="muted small">Proposed by {p.proposed_by}</p>

              {rejecting === p.id ? (
                <div className="reject-box">
                  <label className="field">
                    <span>Note (optional)</span>
                    <input value={note} onChange={(e) => setNote(e.target.value)} />
                  </label>
                  <div className="actions">
                    <button type="button" className="danger" disabled={!online || busy !== null} onClick={() => decide(p, 'reject')}>
                      {busy === p.id ? 'Rejecting…' : 'Confirm reject'}
                    </button>
                    <button type="button" disabled={busy !== null} onClick={() => setRejecting(null)}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="actions">
                  <button type="button" className="primary" disabled={!online || busy !== null} onClick={() => decide(p, 'approve')}>
                    {busy === p.id ? 'Waiting for the server…' : 'Approve'}
                  </button>
                  <button type="button" disabled={!online || busy !== null} onClick={() => setRejecting(p.id)}>
                    Reject
                  </button>
                </div>
              )}
              {errors[p.id] && (
                <p className="error-text" role="alert">
                  {errors[p.id]}
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
