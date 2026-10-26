import { Fragment, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api.js'
import { ficoNav } from '../data/ficoData.js'
import ModuleInsights from './ModuleInsights.jsx'
import './ModuleWorkbench.css'

const moduleFields = {
  company: [
    { key: 'company_code', label: 'Company code', required: true },
    { key: 'country', label: 'Country' },
    { key: 'currency', label: 'Currency' },
    { key: 'description', label: 'Description' },
  ],
  'fiscal-period': [
    { key: 'fiscal_year', label: 'Fiscal year', required: true },
    { key: 'period_number', label: 'Period number', type: 'number', required: true },
    { key: 'start_date', label: 'Start date', type: 'date' },
    { key: 'end_date', label: 'End date', type: 'date' },
  ],
  'chart-of-accounts': [
    { key: 'account_code', label: 'Account code', required: true },
    { key: 'account_type', label: 'Account type', required: true, options: ['Asset', 'Liability', 'Equity', 'Income', 'Expense'] },
    { key: 'currency', label: 'Currency' },
    { key: 'description', label: 'Description' },
  ],
  'journal-entry': [
    { key: 'document_no', label: 'Document number', required: true },
    { key: 'posting_date', label: 'Posting date', type: 'date', required: true },
  ],
  'general-ledger': [
    { key: 'account', label: 'Account', required: true },
    { key: 'posting_date', label: 'Posting date', type: 'date' },
    { key: 'document_no', label: 'Document number' },
    { key: 'debit', label: 'Debit', type: 'number' },
    { key: 'credit', label: 'Credit', type: 'number' },
  ],
  ap: [
    { key: 'supplier', label: 'Supplier', required: true },
    { key: 'invoice_no', label: 'Invoice number', required: true },
    { key: 'invoice_date', label: 'Invoice date', type: 'date', required: true },
    { key: 'due_date', label: 'Due date', type: 'date' },
    { key: 'amount', label: 'Amount', type: 'number', required: true },
    { key: 'account_code', label: 'Expense account', type: 'account', accountType: 'Expense', required: true },
    { key: 'control_account_code', label: 'Accounts payable control', type: 'account', accountType: 'Liability', required: true },
    { key: 'tax_mode', label: 'GST treatment', required: true, options: ['None', 'IGST', 'CGST+SGST'] },
    { key: 'tax_rate', label: 'Total GST rate (%)', type: 'number' },
    { key: 'cgst_rate', type: 'number' },
    { key: 'sgst_rate', type: 'number' },
    { key: 'tax_account_code', label: 'IGST input-tax account', type: 'account', accountType: 'Asset' },
    { key: 'cgst_account_code', label: 'CGST input-tax account', type: 'account', accountType: 'Asset' },
    { key: 'sgst_account_code', label: 'SGST input-tax account', type: 'account', accountType: 'Asset' },
  ],
  ar: [
    { key: 'customer', label: 'Customer', required: true },
    { key: 'invoice_no', label: 'Invoice number', required: true },
    { key: 'invoice_date', label: 'Invoice date', type: 'date', required: true },
    { key: 'due_date', label: 'Due date', type: 'date' },
    { key: 'amount', label: 'Amount', type: 'number', required: true },
    { key: 'account_code', label: 'Revenue account', type: 'account', accountType: 'Income', required: true },
    { key: 'control_account_code', label: 'Accounts receivable control', type: 'account', accountType: 'Asset', required: true },
    { key: 'tax_mode', label: 'GST treatment', required: true, options: ['None', 'IGST', 'CGST+SGST'] },
    { key: 'tax_rate', label: 'Total GST rate (%)', type: 'number' },
    { key: 'cgst_rate', type: 'number' },
    { key: 'sgst_rate', type: 'number' },
    { key: 'tax_account_code', label: 'IGST output-tax account', type: 'account', accountType: 'Liability' },
    { key: 'cgst_account_code', label: 'CGST output-tax account', type: 'account', accountType: 'Liability' },
    { key: 'sgst_account_code', label: 'SGST output-tax account', type: 'account', accountType: 'Liability' },
  ],
  'fixed-assets': [
    { key: 'asset_code', label: 'Asset code', required: true },
    { key: 'acquisition_date', label: 'Acquisition date', type: 'date', required: true },
    { key: 'cost', label: 'Cost', type: 'number', required: true },
    { key: 'salvage_value', label: 'Salvage value', type: 'number' },
    { key: 'useful_life_years', label: 'Useful life (years)', type: 'number', required: true },
    { key: 'asset_account_code', label: 'Asset account', type: 'account', accountType: 'Asset', required: true },
    { key: 'acquisition_offset_account_code', label: 'Acquisition offset account', type: 'account', accountType: 'Asset,Liability,Equity', required: true },
    { key: 'accumulated_depreciation_account_code', label: 'Accumulated depreciation account', type: 'account', accountType: 'Asset', required: true },
    { key: 'depreciation_expense_account_code', label: 'Depreciation expense account', type: 'account', accountType: 'Expense', required: true },
    { key: 'description', label: 'Description' },
  ],
  budgeting: [
    { key: 'fiscal_year', label: 'Fiscal year', required: true },
    { key: 'account_code', label: 'Expense account', type: 'account', accountType: 'Expense', required: true },
    { key: 'start_date', label: 'Period start', type: 'date', required: true },
    { key: 'end_date', label: 'Period end', type: 'date', required: true },
    { key: 'amount', label: 'Budget amount', type: 'number', required: true },
  ],
  gst: [
    { key: 'gstin', label: 'GSTIN', required: true },
    { key: 'tax_type', label: 'Tax type', required: true, options: ['CGST', 'SGST', 'IGST'] },
    { key: 'rate', label: 'Rate (%)', type: 'number', required: true },
    { key: 'effective_date', label: 'Effective date', type: 'date' },
  ],
  'financial-reports': [
    { key: 'report_type', label: 'Report type', required: true, options: ['Balance sheet', 'Income statement', 'Cash flow', 'Trial balance'] },
    { key: 'period', label: 'Reporting period', required: true },
    { key: 'generated_on', label: 'Generated on', type: 'date' },
    { key: 'notes', label: 'Notes' },
  ],
}

const moduleTableFieldKeys = {
  company: ['company_code', 'country', 'currency'],
  'chart-of-accounts': ['account_code', 'account_type', 'currency'],
  'journal-entry': ['document_no', 'posting_date'],
  ap: ['supplier', 'invoice_no', 'invoice_date', 'due_date', 'amount', 'tax_mode'],
  ar: ['customer', 'invoice_no', 'invoice_date', 'due_date', 'amount', 'tax_mode'],
  'fixed-assets': ['asset_code', 'acquisition_date', 'cost', 'useful_life_years'],
  budgeting: ['account_code', 'start_date', 'end_date', 'amount'],
  gst: ['gstin', 'tax_type', 'rate', 'effective_date'],
  'financial-reports': ['report_type', 'period', 'generated_on'],
}

const moduleDescriptions = {
  company: 'Set up the legal entities used by your financial records and reporting.',
  'chart-of-accounts': 'Maintain account codes and types used by journals, invoices, and financial statements.',
  'journal-entry': 'Prepare balanced journals, route them for approval, and post approved entries to the ledger.',
  ap: 'Manage supplier invoices from draft and approval through posting, payment, and settlement.',
  ar: 'Manage customer invoices from draft and approval through posting, receipt, and settlement.',
  'fixed-assets': 'Track asset acquisition approvals, ledger posting, and monthly straight-line depreciation.',
  budgeting: 'Create expense budgets, route them for approval, and compare approved plans with posted actuals.',
  gst: 'Maintain effective-dated GST rates and review tax on posted supplier and customer invoices.',
}

const createLabels = {
  company: 'New company',
  'chart-of-accounts': 'New account',
  'journal-entry': 'New journal',
  ap: 'New supplier invoice',
  ar: 'New customer invoice',
  'fixed-assets': 'New asset',
  budgeting: 'New budget',
  gst: 'New tax rate',
}

const recordNameLabels = {
  company: 'Company name',
  'chart-of-accounts': 'Account name',
  'journal-entry': 'Journal description',
  ap: 'Supplier invoice description',
  ar: 'Customer invoice description',
  'fixed-assets': 'Asset name',
  budgeting: 'Budget name',
  gst: 'Tax rate name',
}

async function apiRequest(path, options = {}) {
  const response = await apiFetch(path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const data = response.status === 204 ? null : await response.json()
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status}).`
    throw new Error(message)
  }
  return data
}

function emptyData(fields) {
  return Object.fromEntries(fields.map((field) => [field.key, '']))
}

function initialData(moduleId, fields) {
  const data = emptyData(fields)
  if (moduleId === 'ap' || moduleId === 'ar') data.tax_mode = 'None'
  if (moduleId === 'journal-entry') {
    data.lines = [
      { account_code: '', debit: '', credit: '', description: '' },
      { account_code: '', debit: '', credit: '', description: '' },
    ]
  }
  return data
}

function localDateValue() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function RecordDetails({ record }) {
  return (
    <div className="wb-record-details">
      {Object.entries(record.data || {}).map(([key, value]) => (
        key === 'lines' && Array.isArray(value)
          ? <div className="wb-record-lines" key={key}>
              <b>Journal lines</b>
              <div className="wb-table-scroll"><table className="wb-table"><thead><tr><th>Account</th><th>Description</th><th>Debit</th><th>Credit</th></tr></thead>
                <tbody>{value.map((line, index) => <tr key={`${line.account_code || 'line'}-${index}`}><td>{line.account_code || '—'}</td><td>{line.description || '—'}</td><td>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(line.debit || 0))}</td><td>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(line.credit || 0))}</td></tr>)}</tbody>
              </table></div>
            </div>
          : <div className="wb-record-detail" key={key}>
              <span>{key.replaceAll('_', ' ')}</span>
              <b>{value == null || value === ''
                ? '—'
                : key.endsWith('_minor') && Number.isFinite(Number(value))
                  ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(value) / 100)
                  : typeof value === 'object' ? JSON.stringify(value) : String(value)}</b>
            </div>
      ))}
    </div>
  )
}

export default function ModuleWorkbench({ moduleId, search = '', onNavigate, role = 'admin' }) {
  const module = ficoNav.find((item) => item.id === moduleId)
  const fields = moduleFields[moduleId] || []
  const tableFields = (moduleTableFieldKeys[moduleId] || fields.slice(0, 3).map((field) => field.key))
    .map((key) => fields.find((field) => field.key === key))
    .filter(Boolean)
  const [records, setRecords] = useState([])
  const [form, setForm] = useState({ name: '', status: 'Draft', data: initialData(moduleId, fields) })
  const [editingId, setEditingId] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [accounts, setAccounts] = useState([])
  const [gstRates, setGstRates] = useState([])
  const [settlements, setSettlements] = useState({})
  const [paymentRecord, setPaymentRecord] = useState(null)
  const [assetSchedules, setAssetSchedules] = useState({})
  const [scheduleLoadingId, setScheduleLoadingId] = useState(null)
  const [openScheduleId, setOpenScheduleId] = useState(null)
  const [reviewRecord, setReviewRecord] = useState(null)
  const [reviewComment, setReviewComment] = useState('')
  const [depreciationRecord, setDepreciationRecord] = useState(null)
  const [depreciationDate, setDepreciationDate] = useState('')
  const [approvalHistories, setApprovalHistories] = useState({})
  const [openHistoryId, setOpenHistoryId] = useState(null)
  const [expandedRecordId, setExpandedRecordId] = useState(null)
  const [statusFilter, setStatusFilter] = useState('All statuses')
  const [paymentForm, setPaymentForm] = useState({ payment_reference: '', posting_date: localDateValue(), amount: '', cash_account_code: '' })
  const [agingAsOfDate, setAgingAsOfDate] = useState(localDateValue)
  const [refreshCount, setRefreshCount] = useState(0)
  const postingModule = ['journal-entry', 'ap', 'ar'].includes(moduleId)
  const approvalModule = ['journal-entry', 'ap', 'ar', 'fixed-assets', 'budgeting'].includes(moduleId)
  const canRequest = ['admin', 'requester', 'approver'].includes(role)
  const canReview = ['admin', 'approver'].includes(role)
  const canManage = role === 'admin'
  const invoiceModule = ['ap', 'ar'].includes(moduleId)
  const needsAccounts = postingModule || ['fixed-assets', 'budgeting'].includes(moduleId)
  const activeAccountTypes = new Set(accounts.filter((account) => account.status === 'Active').map((account) => account.account_type))
  const hasActiveAccounts = accounts.some((account) => account.status === 'Active')
  const expectedAccountTypes = moduleId === 'ap'
    ? ['Expense', 'Liability']
    : moduleId === 'ar'
      ? ['Income', 'Asset']
      : moduleId === 'budgeting'
        ? ['Expense']
        : moduleId === 'fixed-assets'
          ? ['Asset', 'Expense']
          : moduleId === 'journal-entry' && !hasActiveAccounts
            ? ['Chart of Accounts']
        : []
  const missingAccountTypes = expectedAccountTypes.filter((accountType) => !activeAccountTypes.has(accountType))

  useEffect(() => {
    let cancelled = false
    apiRequest(`/api/modules/${moduleId}/records`)
      .then((items) => { if (!cancelled) setRecords(items) })
      .catch((requestError) => { if (!cancelled) setError(requestError.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    if (needsAccounts) {
      apiRequest('/api/accounting/accounts')
        .then((items) => { if (!cancelled) setAccounts(items) })
        .catch((requestError) => { if (!cancelled) setError(requestError.message) })
    }
    if (invoiceModule) {
      apiRequest('/api/modules/gst/records')
        .then((items) => { if (!cancelled) setGstRates(items) })
        .catch((requestError) => { if (!cancelled) setError(requestError.message) })
      apiRequest(`/api/modules/${moduleId}/settlements`)
        .then((items) => {
          if (!cancelled) setSettlements(Object.fromEntries(items.map((item) => [item.invoice_record_id, item])))
        })
        .catch((requestError) => { if (!cancelled) setError(requestError.message) })
    }
    return () => { cancelled = true }
  }, [moduleId, postingModule, invoiceModule, needsAccounts, refreshCount])

  const filteredRecords = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return records.filter((record) => (
      (statusFilter === 'All statuses' || record.status === statusFilter)
      && (!needle || JSON.stringify(record).toLowerCase().includes(needle))
    ))
  }, [records, search, statusFilter])

  const recordStatuses = useMemo(
    () => [...new Set(records.map((record) => record.status))].sort(),
    [records],
  )
  const postedOrActiveCount = records.filter((record) => ['Posted', 'Active'].includes(record.status)).length
  const needsActionCount = approvalModule
    ? records.filter((record) => canReview
      ? record.status === 'Pending Approval'
      : ['Draft', 'Rejected'].includes(record.status)).length
    : records.filter((record) => ['Draft', 'Inactive'].includes(record.status)).length
  const rejectedCount = records.filter((record) => ['Rejected', 'Inactive'].includes(record.status)).length
  const openBalanceMinor = invoiceModule
    ? records
      .filter((record) => record.status === 'Posted')
      .reduce((total, record) => {
        const settlement = settlements[record.id]
        return total + (settlement?.outstanding_minor
          ?? Number(record.data.amount || 0) * 100 + Number(record.data.tax_amount_minor || 0))
      }, 0)
    : 0
  const agingBuckets = useMemo(() => {
    const buckets = [
      { label: 'Not due', count: 0, amountMinor: 0 },
      { label: '1–30 days overdue', count: 0, amountMinor: 0 },
      { label: '31–60 days overdue', count: 0, amountMinor: 0 },
      { label: '61–90 days overdue', count: 0, amountMinor: 0 },
      { label: 'Over 90 days', count: 0, amountMinor: 0 },
      { label: 'No due date', count: 0, amountMinor: 0 },
    ]
    if (!invoiceModule || !agingAsOfDate) return buckets
    const asOf = new Date(`${agingAsOfDate}T00:00:00Z`).getTime()
    for (const record of records) {
      if (record.status !== 'Posted') continue
      const outstanding = settlements[record.id]?.outstanding_minor
        ?? Number(record.data.amount || 0) * 100 + Number(record.data.tax_amount_minor || 0)
      if (outstanding <= 0) continue
      const dueDate = record.data.due_date
      const validDate = typeof dueDate === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dueDate)
      let bucketIndex = 5
      if (validDate) {
        const due = new Date(`${dueDate}T00:00:00Z`).getTime()
        if (Number.isFinite(due)) {
          const daysOverdue = Math.floor((asOf - due) / 86_400_000)
          bucketIndex = daysOverdue <= 0 ? 0 : daysOverdue <= 30 ? 1 : daysOverdue <= 60 ? 2 : daysOverdue <= 90 ? 3 : 4
        }
      }
      buckets[bucketIndex].count += 1
      buckets[bucketIndex].amountMinor += outstanding
    }
    return buckets
  }, [invoiceModule, agingAsOfDate, records, settlements])

  function startCreate() {
    setEditingId(null)
    setForm({ name: '', status: 'Draft', data: initialData(moduleId, fields) })
    setError('')
    setNotice('')
    setShowForm(true)
  }

  function startEdit(record) {
    setEditingId(record.id)
    setForm({ name: record.name, status: record.status, data: { ...emptyData(fields), ...record.data } })
    setError('')
    setNotice('')
    setShowForm(true)
  }

  async function save(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const data = { ...form.data }
    fields.forEach((field) => {
      const value = data[field.key]
      data[field.key] = value === '' ? null : field.type === 'number' ? Number(value) : value
    })
    if (moduleId === 'journal-entry') {
      data.lines = (data.lines || []).map((line) => ({
        ...line,
        debit: line.debit === '' ? 0 : Number(line.debit),
        credit: line.credit === '' ? 0 : Number(line.credit),
      }))
    }
    try {
      const path = `/api/modules/${moduleId}/records${editingId ? `/${editingId}` : ''}`
      const payload = { name: form.name, data }
      if (!approvalModule) payload.status = form.status
      const record = await apiRequest(path, {
        method: editingId ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      })
      setRecords((current) => editingId
        ? current.map((item) => item.id === record.id ? record : item)
        : [record, ...current])
      setShowForm(false)
      setNotice(approvalModule
        ? `${record.name} saved as a draft. Submit it for approval before posting.`
        : `${record.name} saved.`)
      setRefreshCount((count) => count + 1)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  function updateJournalLine(index, key, value) {
    setForm((current) => ({
      ...current,
      data: {
        ...current.data,
        lines: current.data.lines.map((line, lineIndex) => (
          lineIndex === index ? { ...line, [key]: value } : line
        )),
      },
    }))
  }

  function updateDataField(key, value) {
    setForm((current) => {
      const data = { ...current.data, [key]: value }
      if (key === 'tax_mode' || key === 'invoice_date') {
        const mode = key === 'tax_mode' ? value : data.tax_mode
        const invoiceDate = data.invoice_date || '9999-12-31'
        const requestedTypes = mode === 'IGST' ? ['IGST'] : mode === 'CGST+SGST' ? ['CGST', 'SGST'] : []
        const rates = requestedTypes.map((taxType) => gstRates
          .filter((record) => record.status === 'Active' && record.data.tax_type === taxType && (!record.data.effective_date || record.data.effective_date <= invoiceDate))
          .sort((left, right) => String(right.data.effective_date || '').localeCompare(String(left.data.effective_date || '')))[0])
        data.tax_rate = rates.length && rates.every(Boolean)
          ? rates.reduce((total, record) => total + Number(record.data.rate || 0), 0)
          : ''
        data.cgst_rate = mode === 'CGST+SGST' && rates[0] && rates[1] ? Number(rates[0].data.rate) : ''
        data.sgst_rate = mode === 'CGST+SGST' && rates[0] && rates[1] ? Number(rates[1].data.rate) : ''
      } else if (key === 'tax_rate') {
        data.cgst_rate = ''
        data.sgst_rate = ''
      }
      return { ...current, data }
    })
  }

  async function postAssetAcquisition(record) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const posted = await apiRequest(`/api/modules/fixed-assets/records/${record.id}/post-acquisition`, { method: 'POST' })
      setRecords((current) => current.map((item) => item.id === posted.id ? posted : item))
      setNotice(`${posted.name} acquisition posted to the general ledger.`)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function depreciateAsset(record) {
    setDepreciationRecord(record)
    setDepreciationDate('')
    setError('')
    setNotice('')
  }

  async function toggleAssetSchedule(record) {
    if (openScheduleId === record.id) {
      setOpenScheduleId(null)
      return
    }
    setOpenScheduleId(record.id)
    if (Object.hasOwn(assetSchedules, record.id)) return
    setScheduleLoadingId(record.id)
    setError('')
    try {
      const schedule = await apiRequest(`/api/modules/fixed-assets/records/${record.id}/depreciation-schedule`)
      setAssetSchedules((current) => ({ ...current, [record.id]: schedule }))
    } catch (requestError) {
      setError(requestError.message)
      setOpenScheduleId(null)
    } finally {
      setScheduleLoadingId(null)
    }
  }

  async function saveDepreciation(event) {
    event.preventDefault()
    if (!depreciationRecord || !depreciationDate) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const posted = await apiRequest(`/api/modules/fixed-assets/records/${depreciationRecord.id}/depreciate?period_end=${encodeURIComponent(depreciationDate)}`, { method: 'POST' })
      setRecords((current) => current.map((item) => item.id === posted.id ? posted : item))
      setAssetSchedules((current) => {
        const updated = { ...current }
        delete updated[posted.id]
        return updated
      })
      setOpenScheduleId(null)
      setDepreciationRecord(null)
      setNotice(`${posted.name} depreciation posted for ${depreciationDate}.`)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function postRecord(record) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const posted = await apiRequest(`/api/modules/${moduleId}/records/${record.id}/post`, { method: 'POST' })
      setRecords((current) => current.map((item) => item.id === posted.id ? posted : item))
      setRefreshCount((count) => count + 1)
      setNotice(`${posted.name} posted to the general ledger.`)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitApproval(record) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const submitted = await apiRequest(`/api/modules/${moduleId}/records/${record.id}/submit`, { method: 'POST' })
      setRecords((current) => current.map((item) => item.id === submitted.id ? submitted : item))
      setNotice(`${submitted.name} submitted for approval.`)
      setRefreshCount((count) => count + 1)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function reviewApproval(record, action) {
    if (action === 'reject') {
      setReviewRecord(record)
      setReviewComment('')
      setError('')
      setNotice('')
      return
    }
    await saveReview(record, action, '')
  }

  async function saveReview(record, action, comment) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const reviewed = await apiRequest(`/api/modules/${moduleId}/records/${record.id}/review`, {
        method: 'POST',
        body: JSON.stringify({ action, comment: comment.trim() || null }),
      })
      setRecords((current) => current.map((item) => item.id === reviewed.id ? reviewed : item))
      setNotice(`${reviewed.name} ${action === 'approve' ? 'approved' : 'rejected'}.`)
      setReviewRecord(null)
      setApprovalHistories((current) => ({ ...current, [record.id]: null }))
      setRefreshCount((count) => count + 1)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitRejection(event) {
    event.preventDefault()
    if (!reviewRecord || !reviewComment.trim()) return
    await saveReview(reviewRecord, 'reject', reviewComment)
  }

  async function toggleApprovalHistory(record) {
    if (openHistoryId === record.id) {
      setOpenHistoryId(null)
      return
    }
    setOpenHistoryId(record.id)
    if (approvalHistories[record.id]) return
    try {
      const history = await apiRequest(`/api/modules/${moduleId}/records/${record.id}/approvals`)
      setApprovalHistories((current) => ({ ...current, [record.id]: history }))
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  function startPayment(record) {
    setPaymentRecord(record)
    setPaymentForm({
      payment_reference: '',
      posting_date: localDateValue(),
      amount: '',
      cash_account_code: '',
    })
    setError('')
    setNotice('')
  }

  async function savePayment(event) {
    event.preventDefault()
    if (!paymentRecord) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const settlement = await apiRequest(
        `/api/modules/${moduleId}/records/${paymentRecord.id}/payments`,
        {
          method: 'POST',
          body: JSON.stringify({
            ...paymentForm,
            amount: Number(paymentForm.amount),
          }),
        },
      )
      setSettlements((current) => ({ ...current, [settlement.invoice_record_id]: settlement }))
      setPaymentRecord(null)
      setNotice(
        moduleId === 'ap'
          ? `Payment recorded. Remaining supplier balance: ${new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(settlement.outstanding_minor / 100)}.`
          : `Receipt recorded. Remaining customer balance: ${new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(settlement.outstanding_minor / 100)}.`,
      )
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function remove(record) {
    if (!window.confirm(`Delete “${record.name}”? This cannot be undone.`)) return
    setBusy(true)
    setError('')
    try {
      await apiRequest(`/api/modules/${moduleId}/records/${record.id}`, { method: 'DELETE' })
      setRecords((current) => current.filter((item) => item.id !== record.id))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  if (!module) return null

  return (
    <section className="wb-page">
      <header className="wb-heading">
        <div><p>FICO WORKSPACE / {module.label.toUpperCase()}</p><h1>{module.label}</h1><span>{moduleDescriptions[moduleId] || `Manage ${module.label.toLowerCase()} records in your workspace.`}</span></div>
        {(approvalModule ? canRequest : canManage) && <button className="wb-primary" onClick={startCreate}>＋ {createLabels[moduleId] || 'New record'}</button>}
      </header>
      {needsAccounts && missingAccountTypes.length > 0 && (
        <div className="wb-prerequisite" role="status">
          <div>
            <b>Set up active ledger accounts first</b>
            <span>{moduleId === 'ap'
              ? 'AP posting needs Expense and Liability accounts.'
              : moduleId === 'ar'
                ? 'AR posting needs Income and Asset accounts.'
                : moduleId === 'budgeting'
                  ? 'Budget comparison needs at least one active Expense account.'
                  : moduleId === 'fixed-assets'
                    ? 'Asset posting and depreciation need active Asset and Expense accounts.'
                    : 'Posting needs active chart-of-accounts entries.'} Missing: {missingAccountTypes.join(', ')}.</span>
          </div>
          <button onClick={() => onNavigate?.('chart-of-accounts')}>Open Chart of Accounts</button>
        </div>
      )}
      {postingModule && (
        <div className="wb-prerequisite wb-prerequisite-neutral" role="note">
          <div><b>Before posting</b><span>Create and activate a fiscal year, then make sure the invoice date is in an open period.</span></div>
          <button onClick={() => onNavigate?.('fiscal-year')}>Open Fiscal Year</button>
        </div>
      )}
      {(moduleId === 'budgeting' || moduleId === 'gst') && <ModuleInsights key={`${moduleId}-${refreshCount}`} moduleId={moduleId} />}
      {error && <div className="wb-error" role="alert">{error}</div>}
      {notice && <div className="wb-notice" role="status">{notice}</div>}
      <section className="wb-summary-grid" aria-label={`${module.label} summary`}>
        <article><span>Total records</span><b>{records.length}</b><small>In this workspace</small></article>
        <article><span>{approvalModule ? (canReview ? 'Awaiting review' : 'Needs your action') : 'Setup records'}</span><b>{needsActionCount}</b><small>{approvalModule ? (canReview ? 'Submitted for approval' : 'Drafts or rejected items') : 'Draft or inactive'}</small></article>
        <article><span>{invoiceModule ? 'Settled status' : 'Posted / active'}</span><b>{invoiceModule ? records.filter((record) => settlements[record.id]?.settlement_status === 'Paid').length : postedOrActiveCount}</b><small>{invoiceModule ? 'Invoices fully paid or received' : 'Available or posted records'}</small></article>
        <article><span>{invoiceModule ? 'Outstanding' : 'Rejected / inactive'}</span><b>{invoiceModule
          ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(openBalanceMinor / 100)
          : rejectedCount}</b><small>{invoiceModule ? 'Posted invoice balances' : 'Items needing attention'}</small></article>
      </section>
      {invoiceModule && (
          <section className="wb-aging-panel">
            <header><div><h2>{moduleId === 'ap' ? 'Payables aging' : 'Receivables aging'}</h2><p>Open posted invoice balances grouped by days past due.</p></div><label>As of<input type="date" value={agingAsOfDate} onChange={(event) => setAgingAsOfDate(event.target.value)} /></label></header>
            <div className="wb-aging-grid">
              {agingBuckets.map((bucket) => (
                <article key={bucket.label}><span>{bucket.label}</span><b>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(bucket.amountMinor / 100)}</b><small>{bucket.count} open invoice{bucket.count === 1 ? '' : 's'}</small></article>
              ))}
            </div>
          </section>
      )}
      <section className="wb-panel">
        <div className="wb-panel-head">
          <div><h2>{module.label} records</h2><p>Showing {filteredRecords.length} of {records.length} saved record{records.length === 1 ? '' : 's'}</p></div>
          <div className="wb-list-controls">
            <label className="wb-status-filter"><span>Status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option>All statuses</option>{recordStatuses.map((status) => <option key={status}>{status}</option>)}</select></label>
            <button className="wb-refresh" onClick={() => { setLoading(true); setRefreshCount((count) => count + 1) }} disabled={loading || busy}>Refresh</button>
          </div>
        </div>
        {loading ? <div className="wb-empty">Loading records…</div> : (
          <div className="wb-table-scroll">
            <table className="wb-table">
              <thead><tr><th>Name</th>{tableFields.map((field) => <th key={field.key}>{field.label}</th>)}{invoiceModule && <><th>Invoice total</th><th>Paid</th><th>Outstanding</th><th>Settlement</th></>}<th>Status</th><th>Updated</th><th>Actions</th></tr></thead>
              <tbody>
                {filteredRecords.map((record) => (
                  <Fragment key={record.id}>
                  <tr>
                    <td><b>{record.name}</b></td>
                    {tableFields.map((field) => {
                      const value = record.data[field.key]
                      const displayValue = value == null || value === ''
                        ? '—'
                        : field.key === 'amount' || ['cost', 'salvage_value'].includes(field.key)
                          ? new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(value))
                          : field.key === 'rate'
                            ? `${value}%`
                            : value
                      return <td key={field.key}>{displayValue}</td>
                    })}
                    {invoiceModule && (() => {
                      const settlement = settlements[record.id]
                      const invoiceTotal = settlement?.invoice_total_minor ?? Number(record.data.amount || 0) * 100 + Number(record.data.tax_amount_minor || 0)
                      return <>
                        <td>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(invoiceTotal / 100)}</td>
                        <td>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format((settlement?.paid_minor || 0) / 100)}</td>
                        <td>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format((settlement?.outstanding_minor ?? invoiceTotal) / 100)}</td>
                        <td>
                          <b>{settlement?.settlement_status || (record.status === 'Posted' ? 'Unpaid' : 'Not posted')}</b>
                          {settlement?.payments.length > 0 && (
                            <details className="wb-settlement-history">
                              <summary>{settlement.payments.length} transaction{settlement.payments.length === 1 ? '' : 's'}</summary>
                              {settlement.payments.map((payment) => (
                                <span key={payment.id}>{payment.payment_reference} · {new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(payment.amount_minor / 100)} · {payment.posting_date}</span>
                              ))}
                            </details>
                          )}
                        </td>
                      </>
                    })()}
                    <td><span className={`wb-status ${record.status.toLowerCase().replaceAll(' ', '-')}`}>{record.status}</span></td>
                    <td>{new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(record.updated_at))}</td>
                    <td><div className="wb-actions">
                      <button onClick={() => setExpandedRecordId((current) => current === record.id ? null : record.id)} disabled={busy}>{expandedRecordId === record.id ? 'Hide details' : 'Details'}</button>
                      {(approvalModule ? canRequest : canManage) && record.status === 'Rejected' && <button onClick={() => startEdit(record)} disabled={busy}>Edit</button>}
                      {(approvalModule ? canRequest : canManage) && record.status === 'Draft' && <button onClick={() => startEdit(record)} disabled={busy}>Edit</button>}
                      {approvalModule && canRequest && ['Draft', 'Rejected'].includes(record.status) && <button onClick={() => submitApproval(record)} disabled={busy}>Submit</button>}
                      {approvalModule && canReview && record.status === 'Pending Approval' && <>
                        <button onClick={() => reviewApproval(record, 'approve')} disabled={busy}>Approve</button>
                        <button className="danger" onClick={() => reviewApproval(record, 'reject')} disabled={busy}>Reject</button>
                      </>}
                      {approvalModule && <button onClick={() => toggleApprovalHistory(record)} disabled={busy}>History</button>}
                      {postingModule && canRequest && record.status === 'Approved' && <button onClick={() => postRecord(record)} disabled={busy}>Post</button>}
                      {invoiceModule && canRequest && record.status === 'Posted' && (settlements[record.id]?.outstanding_minor ?? Number(record.data.amount || 0) * 100 + Number(record.data.tax_amount_minor || 0)) > 0 && (
                        <button onClick={() => startPayment(record)} disabled={busy}>{moduleId === 'ap' ? 'Record payment' : 'Record receipt'}</button>
                      )}
                      {moduleId === 'fixed-assets' && canRequest && record.status === 'Approved' && <button onClick={() => postAssetAcquisition(record)} disabled={busy}>Post asset</button>}
                      {moduleId === 'fixed-assets' && record.status === 'Active' && <button onClick={() => toggleAssetSchedule(record)} disabled={busy || scheduleLoadingId === record.id}>{scheduleLoadingId === record.id ? 'Loading…' : openScheduleId === record.id ? 'Hide schedule' : 'Schedule'}</button>}
                      {moduleId === 'fixed-assets' && canRequest && record.status === 'Active' && <button onClick={() => depreciateAsset(record)} disabled={busy}>Post depreciation</button>}
                      {canRequest && approvalModule && ['Draft', 'Rejected'].includes(record.status) && <button className="danger" onClick={() => remove(record)} disabled={busy}>Delete</button>}
                      {!approvalModule && canManage && record.status !== 'Posted' && !(moduleId === 'fixed-assets' && record.status === 'Active') && <button className="danger" onClick={() => remove(record)} disabled={busy}>Delete</button>}
                    </div></td>
                  </tr>
                  {approvalModule && openHistoryId === record.id && (
                    <tr>
                      <td colSpan={tableFields.length + (invoiceModule ? 8 : 4)}>
                        <div className="wb-approval-history">
                          <b>Approval history</b>
                          {approvalHistories[record.id] === undefined ? <span>Loading history…</span>
                            : approvalHistories[record.id]?.length
                              ? approvalHistories[record.id].map((event) => (
                                <span key={event.id}>{event.created_at.slice(0, 16).replace('T', ' ')} · {event.actor_name} ({event.actor_email}) · {event.action}{event.comment ? ` · ${event.comment}` : ''}</span>
                              ))
                              : <span>No approval events yet.</span>}
                        </div>
                      </td>
                    </tr>
                  )}
                  {expandedRecordId === record.id && (
                    <tr>
                      <td colSpan={tableFields.length + (invoiceModule ? 8 : 4)}><RecordDetails record={record} /></td>
                    </tr>
                  )}
                  {moduleId === 'fixed-assets' && openScheduleId === record.id && assetSchedules[record.id] && (
                    <tr>
                      <td colSpan={tableFields.length + 4}>
                        <section className="wb-asset-schedule" aria-label={`${record.name} depreciation schedule`}>
                          <div className="wb-asset-schedule-heading"><b>Depreciation schedule</b><span>{assetSchedules[record.id].useful_life_months} months useful life</span></div>
                          <div className="wb-asset-schedule-summary">
                            <span>Cost <b>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(assetSchedules[record.id].cost_minor / 100)}</b></span>
                            <span>Accumulated depreciation <b>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(assetSchedules[record.id].accumulated_depreciation_minor / 100)}</b></span>
                            <span>Net book value <b>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(assetSchedules[record.id].net_book_value_minor / 100)}</b></span>
                            <span>Next period <b>{assetSchedules[record.id].next_period_end || 'Fully depreciated'}</b></span>
                          </div>
                          <div className="wb-table-scroll"><table className="wb-table"><thead><tr><th>Period end</th><th>Document</th><th>Depreciation</th></tr></thead>
                            <tbody>{assetSchedules[record.id].posted_periods.map((period) => <tr key={period.document_no}><td>{period.period_end}</td><td>{period.document_no}</td><td>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(period.amount_minor / 100)}</td></tr>)}
                              {!assetSchedules[record.id].posted_periods.length && <tr><td colSpan="3" className="wb-empty">No depreciation posted yet.</td></tr>}
                            </tbody>
                          </table></div>
                        </section>
                      </td>
                    </tr>
                  )}
                  </Fragment>
                ))}
                {!filteredRecords.length && <tr><td colSpan={tableFields.length + (invoiceModule ? 8 : 4)} className="wb-empty">{records.length ? 'No records match your search.' : `No ${module.label.toLowerCase()} records yet. Use “${createLabels[moduleId] || 'New record'}” to begin; live balances update from posted transactions.`}</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {showForm && (
        <div className="wb-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowForm(false) }}>
          <section className="wb-modal" role="dialog" aria-modal="true" aria-labelledby="wb-form-title">
            <header><div><p>{module.label.toUpperCase()}</p><h2 id="wb-form-title">{editingId ? `Edit ${createLabels[moduleId]?.replace(/^New /, '').toLowerCase() || 'record'}` : createLabels[moduleId] || 'New record'}</h2></div><button aria-label="Close form" onClick={() => setShowForm(false)}>×</button></header>
            <form onSubmit={save}>
              <label className="wb-field"><span>{recordNameLabels[moduleId] || 'Record name'} *</span><input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} required maxLength={160} /></label>
              {postingModule
                ? <label className="wb-field"><span>Status</span><input value="Draft — submit after saving" disabled /></label>
                : approvalModule
                  ? <label className="wb-field"><span>Approval status</span><input value={editingId ? form.status : 'Draft — submit after saving'} disabled /></label>
                  : <label className="wb-field"><span>Status *</span><select value={form.status} onChange={(event) => setForm((current) => ({ ...current, status: event.target.value }))}>{['Draft', 'Active', 'Inactive'].map((option) => <option key={option}>{option}</option>)}</select></label>}
              <div className="wb-form-grid">
                {fields.filter((field) => (
                  !['cgst_rate', 'sgst_rate', 'tax_account_code', 'cgst_account_code', 'sgst_account_code'].includes(field.key)
                  || (form.data.tax_mode === 'IGST' && field.key === 'tax_account_code')
                  || (form.data.tax_mode === 'CGST+SGST' && ['cgst_account_code', 'sgst_account_code'].includes(field.key))
                ) && (field.key !== 'tax_rate' || form.data.tax_mode !== 'None')).map((field) => (
                  <label className="wb-field" key={field.key}>
                    <span>{field.label}{field.required ? ' *' : ''}</span>
                    {field.options ? (
                      <select required={field.required} value={form.data[field.key] || ''} onChange={(event) => updateDataField(field.key, event.target.value)}>
                        <option value="">Select…</option>{field.options.map((option) => <option key={option}>{option}</option>)}
                      </select>
                    ) : field.type === 'account' ? (
                      <select required={field.required} value={form.data[field.key] || ''} onChange={(event) => setForm((current) => ({ ...current, data: { ...current.data, [field.key]: event.target.value } }))}>
                        <option value="">Select active account…</option>
                        {accounts.filter((account) => account.status === 'Active' && field.accountType.split(',').includes(account.account_type)).map((account) => (
                          <option key={account.account_code} value={account.account_code}>{account.account_code} · {account.account_name}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type={field.type || 'text'}
                        required={field.required}
                        step={field.type === 'number' ? 'any' : undefined}
                        value={form.data[field.key] || ''}
                        onChange={(event) => updateDataField(field.key, event.target.value)}
                      />
                    )}
                  </label>
                ))}
              </div>
              {moduleId === 'journal-entry' && (
                <section className="wb-lines">
                  <div className="wb-lines-head"><div><b>Journal lines</b><small>Debits and credits must balance before posting.</small></div><button type="button" className="wb-cancel" onClick={() => setForm((current) => ({ ...current, data: { ...current.data, lines: [...current.data.lines, { account_code: '', debit: '', credit: '', description: '' }] } }))}>＋ Add line</button></div>
                  {form.data.lines.map((line, index) => (
                    <div className="wb-journal-line" key={index}>
                      <label className="wb-field"><span>Account *</span><select required value={line.account_code} onChange={(event) => updateJournalLine(index, 'account_code', event.target.value)}><option value="">Select active account…</option>{accounts.filter((account) => account.status === 'Active').map((account) => <option key={account.account_code} value={account.account_code}>{account.account_code} · {account.account_name}</option>)}</select></label>
                      <label className="wb-field"><span>Debit (₹)</span><input type="number" min="0" step="0.01" value={line.debit} onChange={(event) => updateJournalLine(index, 'debit', event.target.value)} /></label>
                      <label className="wb-field"><span>Credit (₹)</span><input type="number" min="0" step="0.01" value={line.credit} onChange={(event) => updateJournalLine(index, 'credit', event.target.value)} /></label>
                      {form.data.lines.length > 2 && <button type="button" className="wb-remove-line" aria-label={`Remove journal line ${index + 1}`} onClick={() => setForm((current) => ({ ...current, data: { ...current.data, lines: current.data.lines.filter((_, lineIndex) => lineIndex !== index) } }))}>×</button>}
                    </div>
                  ))}
                </section>
              )}
              {error && <div className="wb-error" role="alert">{error}</div>}
              <footer><button type="button" className="wb-cancel" onClick={() => setShowForm(false)}>Cancel</button><button className="wb-primary" disabled={busy}>{busy ? 'Saving…' : approvalModule ? 'Save draft' : 'Save record'}</button></footer>
            </form>
          </section>
        </div>
      )}

      {paymentRecord && (
        <div className="wb-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPaymentRecord(null) }}>
          <section className="wb-modal" role="dialog" aria-modal="true" aria-labelledby="wb-payment-title">
            <header><div><p>{moduleId === 'ap' ? 'ACCOUNTS PAYABLE' : 'ACCOUNTS RECEIVABLE'}</p><h2 id="wb-payment-title">{moduleId === 'ap' ? 'Record supplier payment' : 'Record customer receipt'}</h2></div><button aria-label="Close payment form" onClick={() => setPaymentRecord(null)}>×</button></header>
            <form onSubmit={savePayment}>
              <div className="wb-payment-context">
                <b>{paymentRecord.name}</b>
                <span>Outstanding: {new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format((settlements[paymentRecord.id]?.outstanding_minor ?? Number(paymentRecord.data.amount || 0) * 100 + Number(paymentRecord.data.tax_amount_minor || 0)) / 100)}</span>
                <small>Posting this {moduleId === 'ap' ? 'payment' : 'receipt'} creates balanced cash and control-account entries in the General Ledger.</small>
              </div>
              <label className="wb-field"><span>{moduleId === 'ap' ? 'Payment' : 'Receipt'} reference *</span><input maxLength={100} value={paymentForm.payment_reference} onChange={(event) => setPaymentForm((current) => ({ ...current, payment_reference: event.target.value }))} required /></label>
              <div className="wb-form-grid">
                <label className="wb-field"><span>Posting date *</span><input type="date" value={paymentForm.posting_date} onChange={(event) => setPaymentForm((current) => ({ ...current, posting_date: event.target.value }))} required /></label>
                <label className="wb-field"><span>Amount (₹) *</span><input type="number" min="0.01" step="0.01" max={(settlements[paymentRecord.id]?.outstanding_minor ?? Number(paymentRecord.data.amount || 0) * 100 + Number(paymentRecord.data.tax_amount_minor || 0)) / 100} value={paymentForm.amount} onChange={(event) => setPaymentForm((current) => ({ ...current, amount: event.target.value }))} required /></label>
              </div>
              <label className="wb-field"><span>Cash / bank account *</span><select value={paymentForm.cash_account_code} onChange={(event) => setPaymentForm((current) => ({ ...current, cash_account_code: event.target.value }))} required><option value="">Select an active Asset account…</option>{accounts.filter((account) => account.status === 'Active' && account.account_type === 'Asset').map((account) => <option key={account.account_code} value={account.account_code}>{account.account_code} · {account.account_name}</option>)}</select></label>
              {error && <div className="wb-error" role="alert">{error}</div>}
              <footer><button type="button" className="wb-cancel" onClick={() => setPaymentRecord(null)}>Cancel</button><button className="wb-primary" disabled={busy}>{busy ? 'Posting…' : moduleId === 'ap' ? 'Post payment' : 'Post receipt'}</button></footer>
            </form>
          </section>
        </div>
      )}
      {reviewRecord && (
        <div className="wb-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setReviewRecord(null) }}>
          <section className="wb-modal wb-action-modal" role="dialog" aria-modal="true" aria-labelledby="wb-reject-title">
            <header><div><p>APPROVAL REVIEW</p><h2 id="wb-reject-title">Reject {reviewRecord.name}</h2></div><button aria-label="Close rejection form" onClick={() => setReviewRecord(null)} disabled={busy}>×</button></header>
            <form onSubmit={submitRejection}>
              <p className="wb-action-description">A reason is required and will be saved in the document’s approval history for the requester.</p>
              <label className="wb-field"><span>Reason for rejection *</span><textarea rows="4" maxLength={1000} value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} required /></label>
              {error && <div className="wb-error" role="alert">{error}</div>}
              <footer><button type="button" className="wb-cancel" onClick={() => setReviewRecord(null)} disabled={busy}>Cancel</button><button className="wb-primary wb-reject-submit" disabled={busy || !reviewComment.trim()}>{busy ? 'Rejecting…' : 'Reject document'}</button></footer>
            </form>
          </section>
        </div>
      )}
      {depreciationRecord && (
        <div className="wb-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setDepreciationRecord(null) }}>
          <section className="wb-modal wb-action-modal" role="dialog" aria-modal="true" aria-labelledby="wb-depreciation-title">
            <header><div><p>FIXED ASSETS</p><h2 id="wb-depreciation-title">Post monthly depreciation</h2></div><button aria-label="Close depreciation form" onClick={() => setDepreciationRecord(null)} disabled={busy}>×</button></header>
            <form onSubmit={saveDepreciation}>
              <div className="wb-payment-context"><b>{depreciationRecord.name}</b><small>Depreciation must be posted at month-end, one month at a time, starting the month after acquisition.</small></div>
              <label className="wb-field"><span>Depreciation period end *</span><input type="date" value={depreciationDate} onChange={(event) => setDepreciationDate(event.target.value)} required /></label>
              {error && <div className="wb-error" role="alert">{error}</div>}
              <footer><button type="button" className="wb-cancel" onClick={() => setDepreciationRecord(null)} disabled={busy}>Cancel</button><button className="wb-primary" disabled={busy}>{busy ? 'Posting…' : 'Post depreciation'}</button></footer>
            </form>
          </section>
        </div>
      )}
    </section>
  )
}
