import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api.js'
import './LedgerReport.css'
import './FiscalPeriodManager.css'

async function apiRequest(path, options = {}) {
  const response = await apiFetch(path, options)
  const data = response.status === 204 ? null : await response.json()
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status}).`)
  return data
}

export default function FiscalPeriodManager({ onNavigate, role = 'requester' }) {
  const canManage = role === 'admin'
  const [periods, setPeriods] = useState([])
  const [fiscalYearFilter, setFiscalYearFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [today, setToday] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name: '', start_date: '', end_date: '' })
  const fiscalYears = useMemo(
    () => [...new Set(periods.map((period) => period.fiscal_year_code))].sort((left, right) => right.localeCompare(left)),
    [periods],
  )
  const filteredPeriods = useMemo(() => {
    const query = search.trim().toLowerCase()
    return periods.filter((period) => (
      (fiscalYearFilter === 'all' || period.fiscal_year_code === fiscalYearFilter)
      && (statusFilter === 'ALL' || period.status === statusFilter)
      && (!query || `${period.fiscal_year_code} ${period.period_number} ${period.name} ${period.status}`.toLowerCase().includes(query))
    ))
  }, [periods, fiscalYearFilter, statusFilter, search])
  const openCount = periods.filter((period) => period.status === 'OPEN').length
  const closedCount = periods.filter((period) => period.status === 'CLOSED').length
  const activeYearCount = new Set(periods.filter((period) => period.fiscal_year_status === 'ACTIVE').map((period) => period.fiscal_year_code)).size
  const currentPeriod = periods.find((period) => period.start_date <= today && period.end_date >= today)

  function exportPeriods() {
    const rows = [
      ['Fiscal year', 'Period number', 'Period name', 'Start date', 'End date', 'Fiscal year status', 'Period status'],
      ...filteredPeriods.map((period) => [
        period.fiscal_year_code,
        period.period_number,
        period.name,
        period.start_date,
        period.end_date,
        period.fiscal_year_status,
        period.status,
      ]),
    ]
    const csv = `\uFEFF${rows.map((row) => row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n')}`
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `fiscal-periods-${fiscalYearFilter === 'all' ? 'all-years' : fiscalYearFilter}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

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
      .then((data) => {
        if (!cancelled) {
          setToday(new Date().toISOString().slice(0, 10))
          setPeriods(data)
        }
      })
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
        <div><p>FINANCIAL CALENDAR / PERIOD CONTROL</p><h1>Fiscal Periods</h1><span>Review the posting calendar, monitor open periods, and manage controls for each fiscal year.</span></div>
        <div className="period-heading-actions">
          <button className="ledger-export" onClick={exportPeriods} disabled={loading || !filteredPeriods.length}>Export CSV</button>
          <button className="ledger-export" onClick={loadPeriods} disabled={loading || busy}>Refresh</button>
          {canManage
            ? <button className="period-action" onClick={() => onNavigate?.('fiscal-year')}>Create fiscal year</button>
            : <span className="period-admin-note">Period changes are restricted to workspace admins.</span>}
        </div>
      </header>
      {error && <div className="ledger-error" role="alert">{error}</div>}
      {notice && <div className="period-notice" role="status">{notice}</div>}
      <section className="period-overview" aria-label="Fiscal period overview">
        <article className="period-overview-card calendar">
          <span className="period-overview-icon">▦</span>
          <div><small>Total periods</small><b>{periods.length}</b><em>{fiscalYears.length} fiscal year{fiscalYears.length === 1 ? '' : 's'} configured</em></div>
        </article>
        <article className="period-overview-card open">
          <span className="period-overview-icon">✓</span>
          <div><small>Open for posting</small><b>{openCount}</b><em>Available accounting periods</em></div>
        </article>
        <article className="period-overview-card closed">
          <span className="period-overview-icon">◷</span>
          <div><small>Closed periods</small><b>{closedCount}</b><em>Posting is restricted</em></div>
        </article>
        <article className="period-overview-card active-year">
          <span className="period-overview-icon">✦</span>
          <div><small>Current calendar</small><b>{currentPeriod?.fiscal_year_code || `${activeYearCount} active`}</b><em>{currentPeriod ? `${currentPeriod.name} · ${currentPeriod.status.toLowerCase()}` : 'No period covers today'}</em></div>
        </article>
      </section>
      {loading ? <div className="ledger-empty">Loading fiscal periods…</div> : (
        <section className="period-list-panel">
          <header className="period-list-heading">
            <div><p>POSTING CALENDAR</p><h2>Accounting periods</h2><span>Showing {filteredPeriods.length} of {periods.length} periods</span></div>
            <div className="period-filters">
              <label className="period-search"><span aria-hidden="true">⌕</span><input aria-label="Search fiscal periods" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search periods" /></label>
              <label className="period-filter-select"><span>Fiscal year</span><select aria-label="Filter by fiscal year" value={fiscalYearFilter} onChange={(event) => setFiscalYearFilter(event.target.value)}><option value="all">All years</option>{fiscalYears.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
              <label className="period-filter-select"><span>Status</span><select aria-label="Filter by period status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="ALL">All statuses</option><option value="OPEN">Open</option><option value="CLOSED">Closed</option></select></label>
            </div>
          </header>
          <div className="ledger-table-wrap"><table className="ledger-table">
            <thead><tr><th>Fiscal year</th><th>Period</th><th>Start date</th><th>End date</th><th>Year status</th><th>Period status</th><th>Actions</th></tr></thead>
            <tbody>{filteredPeriods.map((period) => (
              <tr key={period.id} className={period.start_date <= today && period.end_date >= today ? 'current-period-row' : ''}>
                <td><b>{period.fiscal_year_code}</b>{period.fiscal_year_status === 'ACTIVE' && <span className="period-year-active">Active year</span>}</td>
                <td><span className="period-number">{String(period.period_number).padStart(2, '0')}</span>{period.name}</td>
                <td>{period.start_date}</td><td>{period.end_date}</td>
                <td><span className={`period-year-status ${period.fiscal_year_status.toLowerCase()}`}>{period.fiscal_year_status}</span></td>
                <td><span className={`period-status ${period.status.toLowerCase()}`}>{period.status}</span></td>
                <td className="period-row-actions">
                  {canManage && <>
                    <button className="period-action" disabled={busy} onClick={() => startEdit(period)}>Edit</button>
                    <button className="period-action" disabled={busy} onClick={() => setPeriodStatus(period)}>{period.status === 'OPEN' ? 'Close period' : 'Reopen period'}</button>
                  </>}
                </td>
              </tr>
            ))}
            {!filteredPeriods.length && <tr><td colSpan="7" className="ledger-empty">{periods.length ? 'No periods match these filters.' : canManage ? <>Create a fiscal year to generate its twelve periods.<br /><button className="period-action" onClick={() => onNavigate?.('fiscal-year')}>Create a fiscal year</button></> : 'No fiscal periods are configured for this workspace.'}</td></tr>}</tbody>
          </table></div>
          <footer className="period-list-footer"><span>Closed periods reject new postings.</span><span>Period boundaries remain continuous within each fiscal year.</span></footer>
        </section>
      )}
      <p className="ledger-note">Fiscal years generate twelve periods automatically. Changing a period boundary shifts the adjoining open period to avoid gaps or overlaps; dates that contain posted ledger entries cannot be reassigned.</p>
      {editing && canManage && (
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
