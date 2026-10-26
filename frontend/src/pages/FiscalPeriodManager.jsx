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

export default function FiscalPeriodManager({ onNavigate }) {
  const [periods, setPeriods] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name: '', start_date: '', end_date: '' })

  async function loadPeriods() {
    setLoading(true)
    setError('')
    try {
      setPeriods(await apiRequest('/api/fiscal-periods'))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    apiRequest('/api/fiscal-periods')
      .then((data) => { if (!cancelled) setPeriods(data) })
      .catch((requestError) => { if (!cancelled) setError(requestError.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  function startEdit(period) {
    setEditing(period)
    setForm({
      name: period.name,
      start_date: period.start_date,
      end_date: period.end_date,
    })
    setError('')
    setNotice('')
  }

  async function savePeriod(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await apiRequest(`/api/fiscal-periods/${editing.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      setPeriods(await apiRequest('/api/fiscal-periods'))
      setEditing(null)
      setNotice(`${editing.fiscal_year_code} period ${String(editing.period_number).padStart(2, '0')} was updated.`)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function setPeriodStatus(period) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const action = period.status === 'OPEN' ? 'close' : 'reopen'
      const updated = await apiRequest(`/api/fiscal-periods/${period.id}/${action}`, { method: 'POST' })
      setPeriods((current) => current.map((item) => item.id === updated.id ? updated : item))
      setNotice(`${updated.name} is now ${updated.status.toLowerCase()}.`)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="ledger-page">
      <header className="ledger-heading">
        <div><p>FICO WORKSPACE</p><h1>Fiscal Periods</h1><span>Automatic fiscal-year periods can be adjusted while preserving a continuous calendar. Closed periods reject new postings.</span></div>
        <div className="period-heading-actions">
          <button className="ledger-export" onClick={loadPeriods} disabled={loading || busy}>Refresh</button>
          <button className="period-action" onClick={() => onNavigate?.('fiscal-year')}>Create fiscal year</button>
        </div>
      </header>
      {error && <div className="ledger-error" role="alert">{error}</div>}
      {notice && <div className="period-notice" role="status">{notice}</div>}
      {loading ? <div className="ledger-empty">Loading fiscal periods…</div> : (
        <div className="ledger-table-wrap"><table className="ledger-table">
          <thead><tr><th>Fiscal year</th><th>Period</th><th>Start date</th><th>End date</th><th>Year status</th><th>Period status</th><th>Actions</th></tr></thead>
          <tbody>{periods.map((period) => (
            <tr key={period.id}>
              <td><b>{period.fiscal_year_code}</b></td><td>{String(period.period_number).padStart(2, '0')} · {period.name}</td>
              <td>{period.start_date}</td><td>{period.end_date}</td><td>{period.fiscal_year_status}</td>
              <td><span className={`period-status ${period.status.toLowerCase()}`}>{period.status}</span></td>
              <td className="period-row-actions">
                <button className="period-action" disabled={busy} onClick={() => startEdit(period)}>Edit</button>
                <button className="period-action" disabled={busy} onClick={() => setPeriodStatus(period)}>{period.status === 'OPEN' ? 'Close period' : 'Reopen period'}</button>
              </td>
            </tr>
          ))}
          {!periods.length && <tr><td colSpan="7" className="ledger-empty">Create a fiscal year to generate its twelve periods.<br /><button className="period-action" onClick={() => onNavigate?.('fiscal-year')}>Open Fiscal Year</button></td></tr>}</tbody>
        </table></div>
      )}
      <p className="ledger-note">Fiscal years generate twelve periods automatically. Changing a period boundary shifts the adjoining open period to avoid gaps or overlaps; dates that contain posted ledger entries cannot be reassigned.</p>
      {editing && (
        <div className="period-modal-backdrop" role="presentation">
          <section className="period-modal" role="dialog" aria-modal="true" aria-labelledby="period-edit-title">
            <header><div><p>FISCAL PERIOD</p><h2 id="period-edit-title">Edit {editing.fiscal_year_code} · {String(editing.period_number).padStart(2, '0')}</h2></div><button aria-label="Close" onClick={() => setEditing(null)} disabled={busy}>×</button></header>
            <form onSubmit={savePeriod}>
              <label className="period-field">Period name<input required maxLength="60" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} /></label>
              <div className="period-form-grid">
                <label className="period-field">Start date<input required type="date" value={form.start_date} disabled={editing.status === 'CLOSED'} onChange={(event) => setForm((current) => ({ ...current, start_date: event.target.value }))} /></label>
                <label className="period-field">End date<input required type="date" value={form.end_date} disabled={editing.status === 'CLOSED'} onChange={(event) => setForm((current) => ({ ...current, end_date: event.target.value }))} /></label>
              </div>
              <p className="period-edit-note">Dates must stay inside the fiscal year. Moving a boundary also adjusts the neighboring open period, and is blocked if it would reassign a posted ledger entry.</p>
              <footer><button type="button" className="ledger-export" onClick={() => setEditing(null)} disabled={busy}>Cancel</button><button type="submit" className="period-action" disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button></footer>
            </form>
          </section>
        </div>
      )}
    </section>
  )
}
