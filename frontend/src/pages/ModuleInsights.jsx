import { useEffect, useState } from 'react'
import { apiFetch } from '../api.js'
import './ModuleInsights.css'

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })

async function apiRequest(path) {
  const response = await apiFetch(path)
  const data = await response.json()
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status}).`)
  }
  return data
}

function formatMinor(value) {
  return money.format((Number(value) || 0) / 100)
}

function today() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function defaultFiscalStart() {
  const now = new Date()
  return `${now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1}-04-01`
}

export default function ModuleInsights({ moduleId }) {
  const [data, setData] = useState(null)
  const [reportType, setReportType] = useState('income_statement')
  const [startDate, setStartDate] = useState(defaultFiscalStart)
  const [endDate, setEndDate] = useState(today)
  const [refreshCount, setRefreshCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    const path = moduleId === 'budgeting'
      ? '/api/accounting/budget-variance'
      : moduleId === 'gst'
        ? `/api/accounting/gst-summary?start_date=${startDate}&end_date=${endDate}`
        : `/api/accounting/financial-report?report_type=${reportType}&start_date=${startDate}&end_date=${endDate}`
    apiRequest(path)
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setError('')
        }
      })
      .catch((requestError) => { if (!cancelled) setError(requestError.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [moduleId, reportType, startDate, endDate, refreshCount])

  const title = moduleId === 'budgeting'
    ? 'Approved budget vs. actual'
    : moduleId === 'gst'
      ? 'Posted GST summary'
      : 'Generated financial statement'

  function exportCsv() {
    const rows = moduleId === 'budgeting'
      ? [
          ['Budget', 'Account code', 'Account name', 'Start date', 'End date', 'Budget', 'Actual', 'Remaining'],
          ...(data || []).map((row) => [
            row.budget_name,
            row.account_code,
            row.account_name,
            row.start_date,
            row.end_date,
            row.budget_minor / 100,
            row.actual_minor / 100,
            row.variance_minor / 100,
          ]),
        ]
      : moduleId === 'gst'
        ? [
            ['Direction', 'Treatment', 'Rate', 'Invoices', 'Taxable value', 'Tax'],
            ...(data || []).map((row) => [
              row.direction,
              row.tax_mode,
              `${row.rate}%`,
              row.invoice_count,
              row.taxable_minor / 100,
              row.tax_minor / 100,
            ]),
          ]
        : [
            ['Account code', 'Account name', 'Type', 'Balance'],
            ...(data?.lines || []).map((line) => [
              line.account_code,
              line.account_name,
              line.account_type,
              line.amount_minor / 100,
            ]),
          ]
    const csv = `\uFEFF${rows.map((row) => row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n')}`
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${moduleId}-${startDate}-${endDate}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="insights-panel">
      <header className="insights-heading">
        <div><h2>{title}</h2><p>Reports use posted ledger activity only.</p></div>
        {moduleId === 'financial-reports' && (
          <div className="insights-controls">
            <label><span>Statement</span><select value={reportType} onChange={(event) => setReportType(event.target.value)}><option value="income_statement">Income statement</option><option value="balance_sheet">Balance sheet</option></select></label>
            {reportType === 'income_statement' && <label><span>From</span><input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>}
            <label><span>Through</span><input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
          </div>
        )}
        {moduleId === 'gst' && (
          <div className="insights-controls">
            <label><span>Invoice date from</span><input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
            <label><span>Through</span><input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
          </div>
        )}
        <button className="insights-refresh" onClick={exportCsv} disabled={loading || (moduleId === 'financial-reports' ? !data?.lines?.length : !data?.length)}>Export CSV</button>
        <button className="insights-refresh" onClick={() => { setLoading(true); setRefreshCount((count) => count + 1) }} disabled={loading}>Refresh</button>
      </header>
      {error && <div className="insights-error" role="alert">{error}</div>}
      {loading ? <div className="insights-empty">Loading report…</div> : (
        <>
          {moduleId === 'budgeting' && (
            <div className="insights-table-wrap"><table className="insights-table">
              <thead><tr><th>Budget</th><th>Account</th><th>Period</th><th>Budget</th><th>Actual</th><th>Remaining</th></tr></thead>
              <tbody>{data?.map((row) => <tr key={row.record_id}>
                <td>{row.budget_name}</td><td>{row.account_code} · {row.account_name}</td><td>{row.start_date} – {row.end_date}</td>
                <td>{formatMinor(row.budget_minor)}</td><td>{formatMinor(row.actual_minor)}</td><td>{formatMinor(row.variance_minor)}</td>
              </tr>)}
              {!data?.length && <tr><td className="insights-empty" colSpan="6">No approved budgets yet. Create a draft in Budgeting, submit it for approval, then approve it to include it here.</td></tr>}</tbody>
            </table></div>
          )}
          {moduleId === 'gst' && (
            <div className="insights-table-wrap"><table className="insights-table">
              <thead><tr><th>Direction</th><th>Treatment</th><th>Rate</th><th>Invoices</th><th>Taxable value</th><th>Tax</th></tr></thead>
              <tbody>{data?.map((row) => <tr key={`${row.direction}-${row.tax_mode}-${row.rate}`}>
                <td>{row.direction === 'input' ? 'Input (AP)' : 'Output (AR)'}</td><td>{row.tax_mode}</td><td>{row.rate}%</td>
                <td>{row.invoice_count}</td><td>{formatMinor(row.taxable_minor)}</td><td>{formatMinor(row.tax_minor)}</td>
              </tr>)}
              {!data?.length && <tr><td className="insights-empty" colSpan="6">No posted GST invoices in this date range. Configure a tax rate, then submit, approve, and post an AP or AR invoice.</td></tr>}</tbody>
            </table></div>
          )}
          {moduleId === 'financial-reports' && data && (
            <>
              <div className="insights-summary">
                {reportType === 'income_statement' ? <>
                  <span>Income <b>{formatMinor(data.total_income_minor)}</b></span>
                  <span>Expenses <b>{formatMinor(data.total_expenses_minor)}</b></span>
                  <span>Net income <b>{formatMinor(data.net_income_minor)}</b></span>
                </> : <>
                  <span>Assets <b>{formatMinor(data.total_assets_minor)}</b></span>
                  <span>Liabilities <b>{formatMinor(data.total_liabilities_minor)}</b></span>
                  <span>Equity + current earnings <b>{formatMinor(data.total_equity_minor)}</b></span>
                  <span>Balance <b>{data.balanced ? 'Balanced' : 'Out of balance'}</b></span>
                </>}
              </div>
              <div className="insights-table-wrap"><table className="insights-table">
                <thead><tr><th>Account</th><th>Type</th><th>Balance</th></tr></thead>
                <tbody>{data.lines.map((line) => <tr key={line.account_code}><td>{line.account_code} · {line.account_name}</td><td>{line.account_type}</td><td>{formatMinor(line.amount_minor)}</td></tr>)}
                  {!data.lines.length && <tr><td className="insights-empty" colSpan="3">No posted ledger entries in this report period.</td></tr>}
                </tbody>
              </table></div>
            </>
          )}
        </>
      )}
      <p className="insights-disclaimer">Management MVP only: verify tax and statement treatment with your accountant before relying on these figures.</p>
    </section>
  )
}
