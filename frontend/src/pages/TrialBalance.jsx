import { useMemo, useState } from 'react'
import Icon from '../components/Icon.jsx'
import './TrialBalance.css'

const accounts = [
  { code: '1000', name: 'Cash and cash equivalents', category: 'Assets', openingDebit: 250000, openingCredit: 0, periodDebit: 80000, periodCredit: 50000 },
  { code: '1100', name: 'Accounts receivable', category: 'Assets', openingDebit: 180000, openingCredit: 0, periodDebit: 75000, periodCredit: 50000 },
  { code: '1200', name: 'Inventory', category: 'Assets', openingDebit: 400000, openingCredit: 0, periodDebit: 60000, periodCredit: 40000 },
  { code: '1300', name: 'Prepaid expenses', category: 'Assets', openingDebit: 0, openingCredit: 0, periodDebit: 0, periodCredit: 0 },
  { code: '1500', name: 'Property and equipment', category: 'Assets', openingDebit: 500000, openingCredit: 0, periodDebit: 100000, periodCredit: 0 },
  { code: '1590', name: 'Accumulated depreciation', category: 'Assets', openingDebit: 0, openingCredit: 0, periodDebit: 0, periodCredit: 20000 },
  { code: '2000', name: 'Accounts payable', category: 'Liabilities', openingDebit: 0, openingCredit: 160000, periodDebit: 60000, periodCredit: 150000 },
  { code: '2100', name: 'Bank loan', category: 'Liabilities', openingDebit: 0, openingCredit: 300000, periodDebit: 0, periodCredit: 0 },
  { code: '3000', name: 'Share capital and retained earnings', category: 'Equity', openingDebit: 0, openingCredit: 700000, periodDebit: 0, periodCredit: 0 },
  { code: '4000', name: 'Sales revenue', category: 'Income', openingDebit: 0, openingCredit: 300000, periodDebit: 0, periodCredit: 200000 },
  { code: '4100', name: 'Other income', category: 'Income', openingDebit: 0, openingCredit: 0, periodDebit: 0, periodCredit: 0 },
  { code: '5000', name: 'Rent expense', category: 'Expenses', openingDebit: 50000, openingCredit: 0, periodDebit: 10000, periodCredit: 0 },
  { code: '5100', name: 'Salaries and wages', category: 'Expenses', openingDebit: 80000, openingCredit: 0, periodDebit: 105000, periodCredit: 0 },
  { code: '5200', name: 'Depreciation expense', category: 'Expenses', openingDebit: 0, openingCredit: 0, periodDebit: 20000, periodCredit: 0 },
]

const currency = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const periods = [
  'April', 'May', 'June', 'July', 'August', 'September',
  'October', 'November', 'December', 'January', 'February', 'March',
]

const monthlyJournals = (() => {
  const debits = accounts
    .filter((account) => account.periodDebit > 0)
    .map(({ code, periodDebit }) => ({ code, remaining: periodDebit }))
  const credits = accounts
    .filter((account) => account.periodCredit > 0)
    .map(({ code, periodCredit }) => ({ code, remaining: periodCredit }))
  const journalLines = []
  let debitIndex = 0
  let creditIndex = 0

  while (debitIndex < debits.length && creditIndex < credits.length) {
    const amount = Math.min(debits[debitIndex].remaining, credits[creditIndex].remaining)
    journalLines.push({
      debitAccount: debits[debitIndex].code,
      creditAccount: credits[creditIndex].code,
      amount,
    })
    debits[debitIndex].remaining -= amount
    credits[creditIndex].remaining -= amount
    if (debits[debitIndex].remaining === 0) debitIndex += 1
    if (credits[creditIndex].remaining === 0) creditIndex += 1
  }

  return periods.map((_, periodIndex) => journalLines.map((line) => ({
    ...line,
    amount: Math.floor(line.amount * (periodIndex + 1) / periods.length)
      - Math.floor(line.amount * periodIndex / periods.length),
  })))
})()

function formatAmount(amount) {
  return amount === 0 ? '—' : currency.format(amount)
}

function buildRows(startPeriod, endPeriod) {
  const movements = new Map(accounts.map((account) => [
    account.code,
    { debit: 0, credit: 0 },
  ]))

  const applyPeriod = (periodIndex, isOpening) => {
    monthlyJournals[periodIndex].forEach((line) => {
      const debit = movements.get(line.debitAccount)
      const credit = movements.get(line.creditAccount)
      if (isOpening) {
        debit.openingDebit = (debit.openingDebit ?? 0) + line.amount
        credit.openingCredit = (credit.openingCredit ?? 0) + line.amount
      } else {
        debit.debit += line.amount
        credit.credit += line.amount
      }
    })
  }

  for (let index = 0; index < startPeriod; index += 1) applyPeriod(index, true)
  for (let index = startPeriod; index <= endPeriod; index += 1) applyPeriod(index, false)

  return accounts.map((account) => {
    const movement = movements.get(account.code)
    const openingNet = account.openingDebit - account.openingCredit
      + (movement.openingDebit ?? 0) - (movement.openingCredit ?? 0)
    const openingDebit = Math.max(openingNet, 0)
    const openingCredit = Math.max(-openingNet, 0)
    const closingNet = openingNet + movement.debit - movement.credit
    return {
      ...account,
      openingDebit,
      openingCredit,
      periodDebit: movement.debit,
      periodCredit: movement.credit,
      closingDebit: Math.max(closingNet, 0),
      closingCredit: Math.max(-closingNet, 0),
    }
  })
}

function sumAccounts(accountRows) {
  return accountRows.reduce((sum, account) => {
    return {
      openingDebit: sum.openingDebit + account.openingDebit,
      openingCredit: sum.openingCredit + account.openingCredit,
      periodDebit: sum.periodDebit + account.periodDebit,
      periodCredit: sum.periodCredit + account.periodCredit,
      closingDebit: sum.closingDebit + account.closingDebit,
      closingCredit: sum.closingCredit + account.closingCredit,
    }
  }, {
    openingDebit: 0,
    openingCredit: 0,
    periodDebit: 0,
    periodCredit: 0,
    closingDebit: 0,
    closingCredit: 0,
  })
}

function csvValue(value) {
  return `"${String(value).replaceAll('"', '""')}"`
}

export default function TrialBalance({ search: globalSearch = '', onResetSearch = () => {} }) {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All categories')
  const [startPeriod, setStartPeriod] = useState(0)
  const [endPeriod, setEndPeriod] = useState(11)
  const [includeZero, setIncludeZero] = useState(false)
  const reportRows = useMemo(() => buildRows(startPeriod, endPeriod), [startPeriod, endPeriod])
  const needle = `${globalSearch} ${search}`.trim().toLowerCase()
  const rows = useMemo(() => reportRows.filter((account) => {
    const matchesSearch = !needle
      || `${account.code} ${account.name} ${account.category}`.toLowerCase().includes(needle)
    const matchesCategory = category === 'All categories' || account.category === category
    const hasBalance = account.openingDebit + account.openingCredit + account.periodDebit
      + account.periodCredit + account.closingDebit + account.closingCredit > 0
    return matchesSearch && matchesCategory && (includeZero || hasBalance)
  }), [reportRows, needle, category, includeZero])
  const totals = useMemo(() => sumAccounts(reportRows), [reportRows])
  const visibleTotals = useMemo(() => sumAccounts(rows), [rows])
  const isBalanced = totals.closingDebit === totals.closingCredit
  const periodLabel = startPeriod === 0 && endPeriod === 11
    ? 'Full fiscal year'
    : `${periods[startPeriod]}${startPeriod === endPeriod ? '' : ` – ${periods[endPeriod]}`}`

  function updateStartPeriod(event) {
    const value = Number(event.target.value)
    setStartPeriod(value)
    if (value > endPeriod) setEndPeriod(value)
  }

  function updateEndPeriod(event) {
    const value = Number(event.target.value)
    setEndPeriod(value)
    if (value < startPeriod) setStartPeriod(value)
  }

  function resetFilters() {
    setSearch('')
    setCategory('All categories')
    setStartPeriod(0)
    setEndPeriod(11)
    setIncludeZero(false)
    onResetSearch()
  }

  function exportCsv() {
    const headings = [
      'Account code', 'Account name', 'Category', 'Opening debit', 'Opening credit',
      'Period debit', 'Period credit', 'Closing debit', 'Closing credit',
    ]
    const csvRows = rows.map((account) => [
      account.code, account.name, account.category, account.openingDebit,
      account.openingCredit, account.periodDebit, account.periodCredit,
      account.closingDebit, account.closingCredit,
    ])
    csvRows.push([
      'TOTAL', '', '', visibleTotals.openingDebit, visibleTotals.openingCredit,
      visibleTotals.periodDebit, visibleTotals.periodCredit, visibleTotals.closingDebit,
      visibleTotals.closingCredit,
    ])
    const csv = `\uFEFF${[headings, ...csvRows].map((row) => row.map(csvValue).join(',')).join('\r\n')}`
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `trial-balance-${startPeriod + 1}-${endPeriod + 1}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="trial-balance">
      <header className="page-title tb-page-title">
        <div>
          <div className="tb-eyebrow">FINANCIAL REPORTS <span>/</span> GENERAL LEDGER</div>
          <h1>Trial Balance</h1>
          <p>Review account balances and confirm the ledger is in balance.</p>
        </div>
        <div className="tb-page-actions">
          <button className="tb-reset" onClick={resetFilters}>Reset filters</button>
          <button className="tb-print" onClick={() => window.print()}>Print</button>
          <button className="tb-export" onClick={exportCsv} disabled={!rows.length}>
            <Icon name="Download" size={16} /> Export CSV
          </button>
        </div>
      </header>

      <section className="tb-context glass" aria-label="Report details">
        <div className="tb-context-item">
          <span>Company</span>
          <strong>Stackly India Pvt. Ltd. <small>STACKLY001</small></strong>
        </div>
        <div className="tb-context-divider" />
        <div className="tb-context-item">
          <span>Fiscal year</span>
          <strong>FY 2025–26</strong>
        </div>
        <div className="tb-context-divider" />
        <div className="tb-context-item">
          <span>Report period</span>
          <strong>{periodLabel}</strong>
        </div>
        <span className={`tb-status ${isBalanced ? 'balanced' : 'unbalanced'}`}>
          <span aria-hidden="true" /> {isBalanced ? 'Balanced' : 'Out of balance'}
        </span>
      </section>

      <section className="tb-filters card glass" aria-label="Trial balance filters">
        <div className="tb-filter">
          <label htmlFor="tb-period-start">Period from</label>
          <select id="tb-period-start" value={startPeriod} onChange={updateStartPeriod}>
            {periods.map((period, index) => <option value={index} key={period}>{period}</option>)}
          </select>
        </div>
        <div className="tb-filter">
          <label htmlFor="tb-period-end">Period to</label>
          <select id="tb-period-end" value={endPeriod} onChange={updateEndPeriod}>
            {periods.map((period, index) => <option value={index} key={period}>{period}</option>)}
          </select>
        </div>
        <div className="tb-filter">
          <label htmlFor="tb-category">Account category</label>
          <select id="tb-category" value={category} onChange={(event) => setCategory(event.target.value)}>
            <option>All categories</option>
            {['Assets', 'Liabilities', 'Equity', 'Income', 'Expenses'].map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </div>
        <label className="tb-zero-filter">
          <input type="checkbox" checked={includeZero} onChange={(event) => setIncludeZero(event.target.checked)} />
          Include zero-balance accounts
        </label>
      </section>

      <div className="tb-stats" aria-label="Trial balance totals">
        <article className="tb-stat glass">
          <span className="tb-stat-mark blue"><Icon name="ListTree" size={17} /></span>
          <div><span>Accounts included</span><strong>{rows.length}</strong></div>
        </article>
        <article className="tb-stat glass">
          <span className="tb-stat-mark green"><Icon name="TrendingUp" size={17} /></span>
          <div><span>Total debits</span><strong>₹ {currency.format(totals.closingDebit)}</strong></div>
        </article>
        <article className="tb-stat glass">
          <span className="tb-stat-mark purple"><Icon name="Scale" size={17} /></span>
          <div><span>Total credits</span><strong>₹ {currency.format(totals.closingCredit)}</strong></div>
        </article>
      </div>

      <section className="card glass tb-report">
        <div className="tb-report-heading">
          <div>
            <h2>Account balances</h2>
            <p>Opening balance, {periodLabel.toLowerCase()} activity, and closing balance</p>
          </div>
          <label className="tb-search">
            <Icon name="Search" size={16} />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search accounts"
              aria-label="Search accounts"
            />
          </label>
        </div>

        <div className="tb-table-wrap">
          <table className="tb-table">
            <thead>
              <tr>
                <th rowSpan="2">Account</th>
                <th rowSpan="2">Category</th>
                <th colSpan="2">Opening balance</th>
                <th colSpan="2">Period activity</th>
                <th colSpan="2">Closing balance</th>
              </tr>
              <tr>
                <th className="tb-num">Debit</th><th className="tb-num">Credit</th>
                <th className="tb-num">Debit</th><th className="tb-num">Credit</th>
                <th className="tb-num">Debit</th><th className="tb-num">Credit</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((account) => (
                  <tr key={account.code}>
                  <td><span className="tb-account-code">{account.code}</span><strong>{account.name}</strong></td>
                  <td><span className="tb-category">{account.category}</span></td>
                  <td className="tb-num">{formatAmount(account.openingDebit)}</td>
                  <td className="tb-num">{formatAmount(account.openingCredit)}</td>
                  <td className="tb-num">{formatAmount(account.periodDebit)}</td>
                  <td className="tb-num">{formatAmount(account.periodCredit)}</td>
                  <td className="tb-num">{formatAmount(account.closingDebit)}</td>
                  <td className="tb-num">{formatAmount(account.closingCredit)}</td>
                  </tr>
                ))}
              {!rows.length && (
                <tr><td colSpan="8" className="tb-empty">No accounts match the selected filters.</td></tr>
              )}
            </tbody>
            <tfoot>
              <tr>
                <th colSpan="2">Visible total ({rows.length})</th>
                <th className="tb-num">{formatAmount(visibleTotals.openingDebit)}</th>
                <th className="tb-num">{formatAmount(visibleTotals.openingCredit)}</th>
                <th className="tb-num">{formatAmount(visibleTotals.periodDebit)}</th>
                <th className="tb-num">{formatAmount(visibleTotals.periodCredit)}</th>
                <th className="tb-num">{formatAmount(visibleTotals.closingDebit)}</th>
                <th className="tb-num">{formatAmount(visibleTotals.closingCredit)}</th>
              </tr>
            </tfoot>
          </table>
        </div>
        <div className="tb-footnote">
          <span><i /> Sample ledger data</span>
          <span>Debits and credits {isBalanced ? 'are equal' : 'do not match'} for this report.</span>
        </div>
      </section>
    </div>
  )
}
