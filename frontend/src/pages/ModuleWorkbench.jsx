import { useEffect, useMemo, useState } from 'react'
import { ficoNav } from '../data/ficoData.js'
import './ModuleWorkbench.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

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
    { key: 'account', label: 'Account', required: true },
    { key: 'debit', label: 'Debit', type: 'number' },
    { key: 'credit', label: 'Credit', type: 'number' },
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
    { key: 'invoice_date', label: 'Invoice date', type: 'date' },
    { key: 'due_date', label: 'Due date', type: 'date' },
    { key: 'amount', label: 'Amount', type: 'number', required: true },
  ],
  ar: [
    { key: 'customer', label: 'Customer', required: true },
    { key: 'invoice_no', label: 'Invoice number', required: true },
    { key: 'invoice_date', label: 'Invoice date', type: 'date' },
    { key: 'due_date', label: 'Due date', type: 'date' },
    { key: 'amount', label: 'Amount', type: 'number', required: true },
  ],
  'fixed-assets': [
    { key: 'asset_code', label: 'Asset code', required: true },
    { key: 'acquisition_date', label: 'Acquisition date', type: 'date' },
    { key: 'cost', label: 'Cost', type: 'number', required: true },
    { key: 'useful_life_years', label: 'Useful life (years)', type: 'number' },
    { key: 'description', label: 'Description' },
  ],
  budgeting: [
    { key: 'fiscal_year', label: 'Fiscal year', required: true },
    { key: 'account_code', label: 'Account code', required: true },
    { key: 'period', label: 'Period' },
    { key: 'amount', label: 'Budget amount', type: 'number', required: true },
  ],
  gst: [
    { key: 'gstin', label: 'GSTIN', required: true },
    { key: 'tax_type', label: 'Tax type', required: true, options: ['CGST', 'SGST', 'IGST', 'Cess'] },
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

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
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

export default function ModuleWorkbench({ moduleId, search = '' }) {
  const module = ficoNav.find((item) => item.id === moduleId)
  const fields = moduleFields[moduleId] || []
  const [records, setRecords] = useState([])
  const [form, setForm] = useState({ name: '', status: 'Draft', data: emptyData(fields) })
  const [editingId, setEditingId] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function refresh() {
    setLoading(true)
    setError('')
    try {
      setRecords(await apiRequest(`/api/modules/${moduleId}/records`))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    apiRequest(`/api/modules/${moduleId}/records`)
      .then((items) => { if (!cancelled) setRecords(items) })
      .catch((requestError) => { if (!cancelled) setError(requestError.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [moduleId])

  const filteredRecords = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return records
    return records.filter((record) => JSON.stringify(record).toLowerCase().includes(needle))
  }, [records, search])

  function startCreate() {
    setEditingId(null)
    setForm({ name: '', status: 'Draft', data: emptyData(fields) })
    setError('')
    setShowForm(true)
  }

  function startEdit(record) {
    setEditingId(record.id)
    setForm({ name: record.name, status: record.status, data: { ...emptyData(fields), ...record.data } })
    setError('')
    setShowForm(true)
  }

  async function save(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const data = Object.fromEntries(fields.map((field) => {
      const value = form.data[field.key]
      return [field.key, value === '' ? null : field.type === 'number' ? Number(value) : value]
    }))
    try {
      const path = `/api/modules/${moduleId}/records${editingId ? `/${editingId}` : ''}`
      const record = await apiRequest(path, {
        method: editingId ? 'PATCH' : 'POST',
        body: JSON.stringify({ ...form, data }),
      })
      setRecords((current) => editingId
        ? current.map((item) => item.id === record.id ? record : item)
        : [record, ...current])
      setShowForm(false)
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
        <div><p>FICO WORKSPACE</p><h1>{module.label}</h1><span>Manage {module.label.toLowerCase()} records in your workspace.</span></div>
        <button className="wb-primary" onClick={startCreate}>＋ New record</button>
      </header>
      {error && <div className="wb-error" role="alert">{error}</div>}
      <section className="wb-panel">
        <div className="wb-panel-head">
          <div><h2>{module.label} records</h2><p>{records.length} saved record{records.length === 1 ? '' : 's'}</p></div>
          <button className="wb-refresh" onClick={refresh} disabled={loading || busy}>Refresh</button>
        </div>
        {loading ? <div className="wb-empty">Loading records…</div> : (
          <div className="wb-table-scroll">
            <table className="wb-table">
              <thead><tr><th>Name</th>{fields.slice(0, 3).map((field) => <th key={field.key}>{field.label}</th>)}<th>Status</th><th>Updated</th><th>Actions</th></tr></thead>
              <tbody>
                {filteredRecords.map((record) => (
                  <tr key={record.id}>
                    <td><b>{record.name}</b></td>
                    {fields.slice(0, 3).map((field) => <td key={field.key}>{record.data[field.key] ?? '—'}</td>)}
                    <td><span className="wb-status">{record.status}</span></td>
                    <td>{new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(record.updated_at))}</td>
                    <td><div className="wb-actions"><button onClick={() => startEdit(record)} disabled={busy}>Edit</button><button className="danger" onClick={() => remove(record)} disabled={busy}>Delete</button></div></td>
                  </tr>
                ))}
                {!filteredRecords.length && <tr><td colSpan={fields.length + 4} className="wb-empty">{records.length ? 'No records match your search.' : `No ${module.label.toLowerCase()} records yet. Create one to get started.`}</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {showForm && (
        <div className="wb-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowForm(false) }}>
          <section className="wb-modal" role="dialog" aria-modal="true" aria-labelledby="wb-form-title">
            <header><div><p>{module.label.toUpperCase()}</p><h2 id="wb-form-title">{editingId ? 'Edit record' : 'New record'}</h2></div><button aria-label="Close form" onClick={() => setShowForm(false)}>×</button></header>
            <form onSubmit={save}>
              <label className="wb-field"><span>Record name *</span><input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} required maxLength={160} /></label>
              <label className="wb-field"><span>Status *</span><select value={form.status} onChange={(event) => setForm((current) => ({ ...current, status: event.target.value }))}><option>Draft</option><option>In Progress</option><option>Approved</option><option>Posted</option><option>Closed</option><option>Active</option><option>Inactive</option></select></label>
              <div className="wb-form-grid">
                {fields.map((field) => (
                  <label className="wb-field" key={field.key}>
                    <span>{field.label}{field.required ? ' *' : ''}</span>
                    {field.options ? (
                      <select required={field.required} value={form.data[field.key] || ''} onChange={(event) => setForm((current) => ({ ...current, data: { ...current.data, [field.key]: event.target.value } }))}>
                        <option value="">Select…</option>{field.options.map((option) => <option key={option}>{option}</option>)}
                      </select>
                    ) : (
                      <input
                        type={field.type || 'text'}
                        required={field.required}
                        step={field.type === 'number' ? 'any' : undefined}
                        value={form.data[field.key] || ''}
                        onChange={(event) => setForm((current) => ({ ...current, data: { ...current.data, [field.key]: event.target.value } }))}
                      />
                    )}
                  </label>
                ))}
              </div>
              {error && <div className="wb-error" role="alert">{error}</div>}
              <footer><button type="button" className="wb-cancel" onClick={() => setShowForm(false)}>Cancel</button><button className="wb-primary" disabled={busy}>{busy ? 'Saving…' : 'Save record'}</button></footer>
            </form>
          </section>
        </div>
      )}
    </section>
  )
}
