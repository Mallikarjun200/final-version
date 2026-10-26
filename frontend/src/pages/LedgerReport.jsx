import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api.js'
import './LedgerReport.css'

const categories = {
  Asset: 'Assets',
  Liability: 'Liabilities',
  Equity: 'Equity',
  Income: 'Income',
  Expense: 'Expenses',
}

function defaultDateRange() {
  const today = new Date()
  const startYear = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1
  return { startDate: `${startYear}-04-01`, endDate: today.toISOString().slice(0, 10) }
}

async function apiRequest(path) {
  const response = await apiFetch(path)
  const data = response.status === 204 ? null : await response.json()
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status}).`)
  }
  return data
}

function rupees(minor) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 }).format(minor / 100)
}

function csvValue(value) {
  return `"${String(value).replaceAll('"', '""')}"`
}

export default function LedgerReport({ mode, search = '' }) {
  const [dateRange, setDateRange] = useState(defaultDateRange)
  const [category, setCategory] = useState('All categories')
  const [accountCode, setAccountCode] = useState('')
  const [includeZero, setIncludeZero] = useState(false)
  const [report, setReport] = useState(null)
  const [accounts, setAccounts] = useState([])
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const isTrialBalance = mode === 'trial-balance'

  useEffect(() => {
    let cancelled = false
    const params = new URLSearchParams()
    if (dateRange.startDate) params.set('start_date', dateRange.startDate)
    if (dateRange.endDate) params.set('end_date', dateRange.endDate)
    if (!isTrialBalance && accountCode) params.set('account_code', accountCode)
    Promise.all([
      apiRequest('/api/accounting/accounts'),
      isTrialBalance
        ? apiRequest(`/api/accounting/trial-balance?${params}`)
        : apiRequest(`/api/accounting/general-ledger?${params}`),
    ])
      .then(([accountList, data]) => {
        if (cancelled) return
        setAccounts(accountList)
        if (isTrialBalance) setReport(data)
        else setEntries(data)
        setError('')
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message)
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [isTrialBalance, dateRange, accountCode])

  const filteredAccounts = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return (report?.accounts || []).filter((account) => {
      const matchesSearch = !needle || `${account.account_code} ${account.account_name} ${account.account_type}`.toLowerCase().includes(needle)
      const matchesCategory = category === 'All categories' || categories[account.account_type] === category
      const hasBalance = account.opening_debit_minor + account.opening_credit_minor
        + account.period_debit_minor + account.period_credit_minor
        + account.closing_debit_minor + account.closing_credit_minor > 0
      return matchesSearch && matchesCategory && (includeZero || hasBalance)
    })
  }, [report, search, category, includeZero])

  const filteredEntries = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return entries.filter((entry) => !needle
      || `${entry.account_code} ${entry.account_name} ${entry.document_no} ${entry.description} ${entry.source_module}`.toLowerCase().includes(needle))
  }, [entries, search])

  function exportCsv() {
    const headings = isTrialBalance
      ? ['Account code', 'Account name', 'Type', 'Opening debit', 'Opening credit', 'Period debit', 'Period credit', 'Closing debit', 'Closing credit']
      : ['Date', 'Document', 'Account code', 'Account name', 'Description', 'Debit', 'Credit', 'Source']
    const rows = isTrialBalance
      ? filteredAccounts.map((row) => [row.account_code, row.account_name, row.account_type, row.opening_debit_minor / 100, row.opening_credit_minor / 100, row.period_debit_minor / 100, row.period_credit_minor / 100, row.closing_debit_minor / 100, row.closing_credit_minor / 100])
      : filteredEntries.map((row) => [row.posting_date, row.document_no, row.account_code, row.account_name, row.description, row.debit_minor / 100, row.credit_minor / 100, row.source_module])
    const csv = `\uFEFF${[headings, ...rows].map((row) => row.map(csvValue).join(',')).join('\r\n')}`
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${isTrialBalance ? 'trial-balance' : 'general-ledger'}-${dateRange.startDate}-${dateRange.endDate}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="ledger-page">
      <header className="ledger-heading">
        <div><p>FINANCIAL ACCOUNTING / LIVE POSTED DATA</p><h1>{isTrialBalance ? 'Trial Balance' : 'General Ledger'}</h1><span>{isTrialBalance ? 'Balances are calculated from posted transactions only.' : 'Posted source documents, account-by-account.'}</span></div>
        <button className="ledger-export" onClick={exportCsv} disabled={loading || (isTrialBalance ? !filteredAccounts.length : !filteredEntries.length)}>Export CSV</button>
      </header>
      {error && <div className="ledger-error" role="alert">{error}</div>}
      <section className="ledger-filters">
        <label>From<input type="date" value={dateRange.startDate} onChange={(event) => { setLoading(true); setDateRange((range) => ({ ...range, startDate: event.target.value })) }} /></label>
        <label>To<input type="date" value={dateRange.endDate} onChange={(event) => { setLoading(true); setDateRange((range) => ({ ...range, endDate: event.target.value })) }} /></label>
        {isTrialBalance ? (
          <>
            <label>Account category<select value={category} onChange={(event) => setCategory(event.target.value)}><option>All categories</option>{['Assets', 'Liabilities', 'Equity', 'Income', 'Expenses'].map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="ledger-check"><input type="checkbox" checked={includeZero} onChange={(event) => setIncludeZero(event.target.checked)} /> Include zero balances</label>
          </>
        ) : (
          <label>Account<select value={accountCode} onChange={(event) => { setLoading(true); setAccountCode(event.target.value) }}><option value="">All accounts</option>{accounts.map((account) => <option key={account.account_code} value={account.account_code}>{account.account_code} · {account.account_name}</option>)}</select></label>
        )}
      </section>

      {loading ? <div className="ledger-empty">Loading live ledger data…</div> : isTrialBalance ? (
        <>
          <div className="ledger-summary">
            <article><span>Accounts</span><strong>{filteredAccounts.length}</strong></article>
            <article><span>Closing debits</span><strong>{rupees(report?.total_debit_minor || 0)}</strong></article>
            <article><span>Closing credits</span><strong>{rupees(report?.total_credit_minor || 0)}</strong></article>
            <article><span>Ledger status</span><strong className={report?.balanced ? 'ledger-balanced' : 'ledger-unbalanced'}>{report?.balanced ? 'Balanced' : 'Out of balance'}</strong></article>
          </div>
          <div className="ledger-table-wrap"><table className="ledger-table">
            <thead><tr><th>Account</th><th>Category</th><th>Opening Dr</th><th>Opening Cr</th><th>Period Dr</th><th>Period Cr</th><th>Closing Dr</th><th>Closing Cr</th></tr></thead>
            <tbody>{filteredAccounts.map((row) => <tr key={row.account_code}>
              <td><b>{row.account_code}</b> · {row.account_name}</td><td>{categories[row.account_type] || row.account_type}</td>
              <td>{rupees(row.opening_debit_minor)}</td><td>{rupees(row.opening_credit_minor)}</td><td>{rupees(row.period_debit_minor)}</td><td>{rupees(row.period_credit_minor)}</td><td>{rupees(row.closing_debit_minor)}</td><td>{rupees(row.closing_credit_minor)}</td>
            </tr>)}
            {!filteredAccounts.length && <tr><td colSpan="8" className="ledger-empty">No accounts or posted transactions for these filters. Create and activate chart-of-accounts entries, then post a balanced document.</td></tr>}</tbody>
          </table></div>
        </>
      ) : (
        <div className="ledger-table-wrap"><table className="ledger-table">
          <thead><tr><th>Date</th><th>Document</th><th>Account</th><th>Description</th><th>Debit</th><th>Credit</th><th>Source</th></tr></thead>
          <tbody>{filteredEntries.map((entry) => <tr key={entry.id}>
            <td>{entry.posting_date}</td><td>{entry.document_no}</td><td><b>{entry.account_code}</b> · {entry.account_name}</td><td>{entry.description}</td><td>{rupees(entry.debit_minor)}</td><td>{rupees(entry.credit_minor)}</td><td>{entry.source_module}</td>
          </tr>)}
          {!filteredEntries.length && <tr><td colSpan="7" className="ledger-empty">No posted ledger entries match these filters.</td></tr>}</tbody>
        </table></div>
      )}
      <p className="ledger-note">MVP accounting report. Validate results with a qualified accountant before relying on them for statutory or tax reporting.</p>
    </section>
  )
}
