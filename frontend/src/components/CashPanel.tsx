import { useEffect, useRef, useState } from 'react'
import { money } from '../api.ts'
import type { Cash } from '../types.ts'

interface Props {
  cash: Cash | null
  error: string | null
}

export default function CashPanel({ cash, error }: Props) {
  // Briefly mark the balance when the server reports a new value (e.g. right after an approval).
  // Keyed on the number, not the object: every poll returns a new object, which would keep resetting the timer.
  const balance = cash?.balance ?? null
  const previous = useRef<number | null>(null)
  const [changed, setChanged] = useState(false)
  useEffect(() => {
    if (balance === null) return
    const before = previous.current
    previous.current = balance
    if (before === null || before === balance) return
    setChanged(true)
    const timer = setTimeout(() => setChanged(false), 2500)
    return () => clearTimeout(timer)
  }, [balance])

  return (
    <section className="panel" aria-labelledby="cash-heading">
      <h2 id="cash-heading">Cash</h2>
      {error && <p className="error-text">{error}</p>}
      {!cash && !error && <p className="muted">Loading cash…</p>}
      {cash && (
        <>
          <p className="eyebrow">Checking balance</p>
          <p className={`balance${changed ? ' changed' : ''}`} aria-live="polite">
            {money(cash.balance)}
          </p>
          <p className="muted small">
            From cash_accounts, updated {cash.as_of}
            {changed && <span className="pill ok">updated</span>}
          </p>
          <dl className="facts compact">
            <dt>Waiting for approval</dt>
            <dd>{money(cash.pending_total)}</dd>
            <dt>If all are approved</dt>
            <dd className={cash.balance_if_all_pending_approved < 0 ? 'error-text' : undefined}>
              {money(cash.balance_if_all_pending_approved)}
            </dd>
          </dl>
          <h3>Payments made</h3>
          {cash.recent_payments.length === 0 && <p className="muted small">No payments yet.</p>}
          <ul className="payments">
            {cash.recent_payments.map((p) => (
              <li key={p.id}>
                <span>
                  {p.kind} #{p.ref_id}
                  <span className="muted small"> · {p.approved_by}</span>
                </span>
                <span className="amount-out">−{money(p.amount)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
