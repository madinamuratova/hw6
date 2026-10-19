import { useCallback, useEffect, useState } from 'react'
import { API_BASE, ApiError, api } from './api.ts'
import ApprovalsPanel from './components/ApprovalsPanel.tsx'
import CashPanel from './components/CashPanel.tsx'
import TicketList from './components/TicketList.tsx'
import TicketPanel from './components/TicketPanel.tsx'
import { usePolling } from './usePolling.ts'

interface Notice {
  id: number
  tone: 'ok' | 'error'
  text: string
}

const NAME_KEY = 'campus-customs-approver'

export default function App() {
  const health = usePolling(api.health, 3000)
  const tickets = usePolling(api.tickets, 3000)
  const cash = usePolling(api.cash, 3000)
  const approvals = usePolling(api.approvals, 3000)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [name, setNameState] = useState(() => localStorage.getItem(NAME_KEY) ?? '')
  const [notices, setNotices] = useState<Notice[]>([])
  const [resetting, setResetting] = useState(false)

  const online = health.data !== null && health.error === null
  const activeRun = health.data?.active_run ?? null

  const setName = (value: string) => {
    setNameState(value)
    localStorage.setItem(NAME_KEY, value)
  }

  const notify = useCallback((tone: Notice['tone'], text: string) => {
    const id = Date.now() + Math.random()
    setNotices((all) => [...all, { id, tone, text }])
    setTimeout(() => setNotices((all) => all.filter((n) => n.id !== id)), 7000)
  }, [])

  const refreshAll = useCallback(() => {
    void health.refresh()
    void tickets.refresh()
    void cash.refresh()
    void approvals.refresh()
  }, [health.refresh, tickets.refresh, cash.refresh, approvals.refresh])

  // Select the first ticket once the list arrives.
  useEffect(() => {
    if (selectedId === null && tickets.data?.length) setSelectedId(tickets.data[0].id)
  }, [selectedId, tickets.data])

  async function resetData() {
    const who = name.trim()
    if (!who) {
      notify('error', 'Enter your name under Approvals before resetting the data.')
      return
    }
    const ok = window.confirm(
      'Reset the working database to the original values?\n\n' +
        'Pending proposals, payments, and ticket statuses go back to the start. Drafts and the audit trail are kept.',
    )
    if (!ok) return
    setResetting(true)
    try {
      await api.reset(who)
      notify('ok', `Data reset by ${who}. Checking and tickets are back to their original values.`)
      refreshAll()
    } catch (e) {
      notify('error', `Reset failed: ${e instanceof ApiError ? e.message : String(e)}`)
    } finally {
      setResetting(false)
    }
  }

  const selected = tickets.data?.find((t) => t.id === selectedId) ?? null

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Campus Customs</h1>
          <p className="muted">Operations desk</p>
        </div>
        <div className="topbar-meta">
          {cash.data && <span>Shop date {cash.data.today}</span>}
          {health.data && (
            <span className="muted" title={health.data.database}>
              {health.data.model} · {health.data.database.split('/').pop()}
            </span>
          )}
          <span className={`status-dot ${online ? 'on' : 'off'}`}>{online ? 'API connected' : 'API offline'}</span>
          <button type="button" disabled={!online || !!activeRun || resetting} onClick={resetData}>
            {resetting ? 'Resetting…' : 'Reset data'}
          </button>
        </div>
      </header>

      {!online && health.error && (
        <div className="banner" role="alert">
          <strong>Can't reach the API at {API_BASE}.</strong> Start it from the HW 6 folder with{' '}
          <code>.venv/bin/uvicorn backend.main:app --port 8000</code>. The page keeps trying every few seconds, and buttons
          stay off until it's back.
        </div>
      )}

      <div className="notices" role="status" aria-live="polite">
        {notices.map((n) => (
          <p key={n.id} className={`notice ${n.tone}`}>
            {n.text}
          </p>
        ))}
      </div>

      {/* While offline the panels show the last data we received, dimmed so it isn't mistaken for live numbers. */}
      <main className={`layout${online ? '' : ' stale'}`}>
        <TicketList tickets={tickets.data} selectedId={selectedId} activeRun={activeRun} onSelect={setSelectedId} />
        {selected ? (
          <TicketPanel
            key={selected.id}
            ticket={selected}
            online={online}
            activeRun={activeRun}
            name={name}
            onChanged={refreshAll}
            notify={notify}
          />
        ) : (
          <section className="panel">
            <p className="muted">{tickets.error ? 'Tickets could not be loaded.' : 'Select a ticket.'}</p>
          </section>
        )}
        <aside className="side">
          <CashPanel cash={cash.data} error={cash.error && cash.error.status !== 0 ? cash.error.message : null} />
          <ApprovalsPanel
            proposals={approvals.data}
            loadError={approvals.error && approvals.error.status !== 0 ? approvals.error.message : null}
            cash={cash.data}
            name={name}
            setName={setName}
            online={online}
            onDecided={refreshAll}
            notify={notify}
          />
        </aside>
      </main>
    </div>
  )
}
