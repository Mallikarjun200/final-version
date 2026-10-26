import { useMemo, useState } from 'react'
import Icon from '../components/Icon.jsx'
import {
  financialSummary, ficoModules, inr, inrWhole, kpis, quickActions, recentTransactions,
} from '../data/ficoData.js'

const statusClass = {
  Posted: 'ok',
  Approved: 'ok-soft',
  Created: 'warn',
  'In Progress': 'neutral',
}

export default function FicoDashboard({ onNavigate, search }) {
  const [range, setRange] = useState('This Year')

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return recentTransactions
    return recentTransactions.filter((r) =>
      [r.doc, r.module, r.description, r.status, r.date].some((v) => v.toLowerCase().includes(needle)),
    )
  }, [search])

  const modules = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return ficoModules
    return ficoModules.filter((m) => `${m.title} ${m.blurb}`.toLowerCase().includes(needle))
  }, [search])

  return (
    <div className="dash">
      <div className="dash-main">
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
              <div className="kpi-value">{k.value}</div>
              <button className="link" onClick={() => onNavigate(k.target)}>
                View All <Icon name="ArrowRight" size={13} />
              </button>
            </article>
          ))}
        </section>

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
                    <td>{r.date}</td>
                    <td>{r.doc}</td>
                    <td>{r.module}</td>
                    <td>{r.description}</td>
                    <td className="num">{inr(r.amount)}</td>
                    <td><span className={`pill ${statusClass[r.status]}`}>{r.status}</span></td>
                  </tr>
                ))}
                {!rows.length && (
                  <tr><td colSpan="6" className="empty">No transactions match &ldquo;{search}&rdquo;.</td></tr>
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
            {financialSummary.map((s) => (
              <div key={s.label} className="sum-row">
                <div>
                  <dt>{s.label}</dt>
                  <dd>{inrWhole(s.amount)}</dd>
                </div>
                <span className="delta"><span aria-hidden="true">↑</span> {s.change}</span>
              </div>
            ))}
          </dl>
        </section>
      </aside>
    </div>
  )
}
