import { useEffect, useMemo, useState } from 'react'
import Icon from '../components/Icon.jsx'
import {
  ficoModules, inr, kpis, quickActions,
} from '../data/ficoData.js'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

const statusClass = {
  Posted: 'ok',
  Approved: 'ok-soft',
  Created: 'warn',
  'In Progress': 'neutral',
}

async function fetchDashboard(period) {
  const response = await fetch(`${API_BASE}/api/accounting/dashboard-summary?period=${encodeURIComponent(period)}`, {
    credentials: 'include',
  })
  const data = await response.json()
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Dashboard request failed (${response.status}).`)
  }
  return data
}

export default function FicoDashboard({ onNavigate, search }) {
  const [range, setRange] = useState('This Year')
  const [dashboard, setDashboard] = useState(null)
  const [dashboardError, setDashboardError] = useState('')

  useEffect(() => {
    let cancelled = false
    fetchDashboard(range)
      .then((summary) => {
        if (!cancelled) {
          setDashboard(summary)
          setDashboardError('')
        }
      })
      .catch((error) => { if (!cancelled) setDashboardError(error.message) })
    return () => { cancelled = true }
  }, [range])

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const transactions = dashboard?.recent_transactions || []
    if (!needle) return transactions
    return transactions.filter((r) =>
      [r.doc, r.module, r.description, r.status, r.date].some((v) => v.toLowerCase().includes(needle)),
    )
  }, [dashboard, search])

  const modules = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return ficoModules
    return ficoModules.filter((m) => `${m.title} ${m.blurb}`.toLowerCase().includes(needle))
  }, [search])

  return (
    <div className="dash">
      <div className="dash-main">
        {dashboardError && <div className="wb-error" role="alert">{dashboardError}</div>}
        <div className="page-title">
          <h1>FICO - Financial Accounting</h1>
          <p>Manage your company&apos;s financial transactions and reports</p>
        </div>

        <section className="kpi-grid" aria-label="Key figures">
          {kpis.map((k) => (
            <article key={k.id} className={`kpi glass tone-${k.tone}`}>
              <span className="kpi-blob" aria-hidden="true" />
              <span className="tile-icon"><Icon name={k.icon} size={19} /></span>
              <div className="kpi-label">{k.label}</div>
              <div className="kpi-value">{dashboard ? dashboard.kpis[k.id] : '—'}</div>
              <button className="link" onClick={() => onNavigate(k.target)}>
                View All <Icon name="ArrowRight" size={13} />
              </button>
            </article>
          ))}
        </section>

        {dashboard && (
          <section className="setup-card" aria-labelledby="setup-heading">
            <div className="setup-heading">
              <div>
                <p>WORKSPACE SETUP</p>
                <h2 id="setup-heading">Get started with connected accounting</h2>
                <span>Set up your company, chart of accounts, and fiscal year before posting transactions.</span>
              </div>
            </div>
            <div className="setup-steps">
              {[
                { id: 'company', label: 'Company', detail: 'Add your company details', complete: dashboard.kpis.companies > 0 },
                { id: 'chart-of-accounts', label: 'Chart of Accounts', detail: 'Create and activate ledger accounts', complete: dashboard.kpis.accounts > 0 },
                { id: 'fiscal-year', label: 'Fiscal Year', detail: 'Create and activate an open year', complete: dashboard.kpis.years > 0 },
              ].map((step, index) => (
                <div className={`setup-step ${step.complete ? 'complete' : ''}`} key={step.id}>
                  <span className="setup-step-number">{step.complete ? '✓' : index + 1}</span>
                  <div><b>{step.label}</b><small>{step.complete ? 'Setup started' : step.detail}</small></div>
                  <button onClick={() => onNavigate(step.id)}>{step.complete ? 'Review' : 'Set up'}</button>
                </div>
              ))}
            </div>
            <p className="setup-note">After setup, create a draft in Journal Entry, AP, or AR and choose <b>Post</b> to update the General Ledger and Trial Balance.</p>
          </section>
        )}

        <section className="card glass">
          <div className="card-head">
            <h2>Recent Transactions</h2>
            <button className="link" onClick={() => onNavigate('general-ledger')}>
              View All <Icon name="ArrowRight" size={13} />
            </button>
          </div>
          <div className="table-wrap">
            <table className="txn">
              <thead>
                <tr>
                  <th>Date</th><th>Document No.</th><th>Module</th>
                  <th>Description</th><th className="num">Amount</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.doc}>
                    <td>{new Intl.DateTimeFormat('en-IN').format(new Date(`${r.date}T00:00:00`))}</td>
                    <td>{r.doc}</td>
                    <td>{r.module}</td>
                    <td>{r.description}</td>
                    <td className="num">{inr(r.amount_minor / 100)}</td>
                    <td><span className={`pill ${statusClass[r.status]}`}>{r.status}</span></td>
                  </tr>
                ))}
                {!rows.length && (
                  <tr><td colSpan="6" className="empty">{search ? `No transactions match “${search}”.` : 'No posted transactions yet.'}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card glass modules" aria-label="FICO modules">
          <div className="card-head">
            <h2>FICO Modules</h2>
            <button className="link" onClick={() => onNavigate('company')}>
              View All Modules <Icon name="ArrowRight" size={13} />
            </button>
          </div>
          <div className="module-grid">
            {modules.map((m) => (
              <button key={m.id} className="module" onClick={() => onNavigate(m.id)}>
                <span className={`tile-icon tone-${m.tone}`}><Icon name={m.icon} size={18} /></span>
                <span className="module-text">
                  <b>{m.title}</b>
                  <small>{m.blurb}</small>
                </span>
                <Icon name="ChevronRight" size={16} className="module-chevron" />
              </button>
            ))}
            {!modules.length && <div className="empty">No modules match &ldquo;{search}&rdquo;.</div>}
          </div>
        </section>
      </div>

      <aside className="dash-side">
        <section className="card glass quick" aria-label="Quick actions">
          <h2>Quick Actions</h2>
          <ul>
            {quickActions.map((a) => (
              <li key={a.label}>
                <button className="qa" onClick={() => onNavigate(a.target)}>
                  <span className={`tile-icon sm tone-${a.tone}`}><Icon name={a.icon} size={16} /></span>
                  <span>{a.label}</span>
                  <Icon name="ChevronRight" size={15} className="qa-chevron" />
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="card glass summary" aria-label="Financial summary">
          <div className="card-head">
            <h2>Financial Summary</h2>
            <select value={range} onChange={(e) => setRange(e.target.value)} aria-label="Summary period">
              <option>This Year</option>
              <option>This Quarter</option>
              <option>This Month</option>
            </select>
          </div>
          <dl>
            {[
              { label: 'Total Income', amount: dashboard?.financial_summary.total_income_minor },
              { label: 'Total Expenses', amount: dashboard?.financial_summary.total_expenses_minor },
              { label: 'Net Income', amount: dashboard?.financial_summary.net_income_minor },
            ].map((s) => (
              <div key={s.label} className="sum-row">
                <div>
                  <dt>{s.label}</dt>
                  <dd>{s.amount === undefined ? '—' : inr(s.amount / 100)}</dd>
                </div>
              </div>
            ))}
          </dl>
        </section>
      </aside>
    </div>
  )
}
