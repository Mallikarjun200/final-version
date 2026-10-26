import { useEffect, useState } from 'react'
import './LedgerReport.css'
import './FiscalPeriodManager.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'include', ...options })
  const data = response.status === 204 ? null : await response.json()
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status}).`)
  return data
}

export default function FiscalPeriodManager() {
  const [periods, setPeriods] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    apiRequest('/api/fiscal-periods')
      .then((data) => { if (!cancelled) setPeriods(data) })
      .catch((requestError) => { if (!cancelled) setError(requestError.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  async function setPeriodStatus(period) {
    setBusy(true)
    setError('')
    try {
      const action = period.status === 'OPEN' ? 'close' : 'reopen'
      const updated = await apiRequest(`/api/fiscal-periods/${period.id}/${action}`, { method: 'POST' })
      setPeriods((current) => current.map((item) => item.id === updated.id ? updated : item))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="ledger-page">
      <header className="ledger-heading"><div><p>FICO WORKSPACE</p><h1>Fiscal Periods</h1><span>Manage open and closed periods. Closed periods reject new journal and invoice postings.</span></div></header>
      {error && <div className="ledger-error" role="alert">{error}</div>}
      {loading ? <div className="ledger-empty">Loading fiscal periods…</div> : (
        <div className="ledger-table-wrap"><table className="ledger-table">
          <thead><tr><th>Fiscal year</th><th>Period</th><th>Start date</th><th>End date</th><th>Year status</th><th>Period status</th><th>Action</th></tr></thead>
          <tbody>{periods.map((period) => (
            <tr key={period.id}>
              <td><b>{period.fiscal_year_code}</b></td><td>{String(period.period_number).padStart(2, '0')} · {period.name}</td>
              <td>{period.start_date}</td><td>{period.end_date}</td><td>{period.fiscal_year_status}</td>
              <td><span className={`period-status ${period.status.toLowerCase()}`}>{period.status}</span></td>
              <td><button className="period-action" disabled={busy} onClick={() => setPeriodStatus(period)}>{period.status === 'OPEN' ? 'Close period' : 'Reopen period'}</button></td>
            </tr>
          ))}
          {!periods.length && <tr><td colSpan="7" className="ledger-empty">Create a fiscal year to generate its twelve periods.</td></tr>}</tbody>
        </table></div>
      )}
      <p className="ledger-note">Period closure is an operational control in this MVP. Reopening a period is available to the signed-in account.</p>
    </section>
  )
}
