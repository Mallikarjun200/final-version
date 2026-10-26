import { useEffect, useMemo, useState } from 'react'
import './FiscalYearModule.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
function getDefaultDates(variant) {
  const today = new Date()
  const year = today.getFullYear()
  const fiscalStartYear = variant === 'APR_MAR' && today.getMonth() < 3 ? year - 1 : year
  if (variant === 'APR_MAR') {
    return { start: `${fiscalStartYear}-04-01`, end: `${fiscalStartYear + 1}-03-31` }
  }
  return { start: `${year}-01-01`, end: `${year}-12-31` }
}

const INITIAL_FORM = {
  company: 'STACKLY001',
  code: '',
  name: '',
  variant: 'APR_MAR',
  ...getDefaultDates('APR_MAR'),
  description: '',
}

function errorMessage(data, fallback) {
  if (typeof data?.detail === 'string') return data.detail
  if (Array.isArray(data?.detail)) {
    return data.detail.map((item) => item.msg).filter(Boolean).join(' ')
  }
  return fallback
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const data = response.status === 204 ? null : await response.json()
  if (!response.ok) {
    const error = new Error(errorMessage(data, `Request failed (${response.status}).`))
    error.details = data?.detail
    throw error
  }
  return data
}

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('en', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T00:00:00Z`))
}

function Field({ label, name, value, onChange, error, hint, ...props }) {
  return (
    <label className="fy-field">
      <span>{label}<i>*</i></span>
      <input
        className={error ? 'has-error' : ''}
        name={name}
        value={value}
        onChange={onChange}
        aria-invalid={Boolean(error)}
        {...props}
      />
      {error && <small className="fy-error">{error}</small>}
      {hint && <small className="fy-field-hint">{hint}</small>}
    </label>
  )
}

function FiscalYearModule({ embedded = false }) {
  const [years, setYears] = useState([])
  const [selected, setSelected] = useState(null)
  const [mode, setMode] = useState('list')
  const [form, setForm] = useState(INITIAL_FORM)
  const [errors, setErrors] = useState({})
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [noticeType, setNoticeType] = useState('info')

  async function loadYears() {
    try {
      setYears(await apiRequest('/api/fiscal-years'))
    } catch (error) {
      setNotice(error.message)
      setNoticeType('error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    apiRequest('/api/fiscal-years')
      .then((data) => {
        if (!cancelled) setYears(data)
      })
      .catch((error) => {
        if (!cancelled) {
          setNotice(error.message)
          setNoticeType('error')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const filteredYears = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return years.filter((year) => {
      const matchesSearch = !needle
        || year.code.toLowerCase().includes(needle)
        || year.name.toLowerCase().includes(needle)
        || year.company.toLowerCase().includes(needle)
      return matchesSearch && (statusFilter === 'ALL' || year.status === statusFilter)
    })
  }, [years, search, statusFilter])

  const activeCount = years.filter((year) => year.status === 'ACTIVE').length
  const draftCount = years.filter((year) => year.status === 'DRAFT').length
  const totalPeriods = years.reduce((total, year) => total + year.period_count, 0)

  function startCreate() {
    setForm(INITIAL_FORM)
    setErrors({})
    setSelected(null)
    setNotice('')
    setMode('create')
  }

  function change(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
    setErrors((current) => ({ ...current, [name]: '' }))
  }

  function changeVariant(event) {
    const variant = event.target.value
    setForm((current) => ({ ...current, variant, ...getDefaultDates(variant) }))
    setErrors((current) => ({ ...current, variant: '', start: '', end: '' }))
  }

  async function createYear(event) {
    event.preventDefault()
    setBusy(true)
    setErrors({})
    try {
      const created = await apiRequest('/api/fiscal-years', {
        method: 'POST',
        body: JSON.stringify(form),
      })
      await loadYears()
      setSelected(created)
      setMode('detail')
      setNotice(`${created.code} was created with ${created.period_count} accounting periods.`)
      setNoticeType('success')
    } catch (error) {
      if (Array.isArray(error.details)) {
        const fieldAliases = { company_code: 'company', start_date: 'start', end_date: 'end' }
        const nextErrors = {}
        error.details.forEach((detail) => {
          const fieldName = detail.loc?.at(-1)
          const field = fieldAliases[fieldName] || fieldName
          if (Object.hasOwn(INITIAL_FORM, field)) nextErrors[field] = detail.msg
          if (detail.loc?.length <= 1 && /start on 1 April|start on 1 January/i.test(detail.msg)) {
            nextErrors.start = detail.msg
          }
          if (detail.loc?.length <= 1 && /end on 31 March|end on 31 December/i.test(detail.msg)) {
            nextErrors.end = detail.msg
          }
        })
        setErrors(nextErrors)
      }
      setNotice(error.message)
      setNoticeType('error')
    } finally {
      setBusy(false)
    }
  }

  async function openDetails(id) {
    setBusy(true)
    setNotice('')
    try {
      setSelected(await apiRequest(`/api/fiscal-years/${id}`))
      setMode('detail')
    } catch (error) {
      setNotice(error.message)
      setNoticeType('error')
    } finally {
      setBusy(false)
    }
  }

  async function activate() {
    if (!selected) return
    setBusy(true)
    try {
      const updated = await apiRequest(`/api/fiscal-years/${selected.id}/activate`, { method: 'POST' })
      setSelected(updated)
      await loadYears()
      setNotice(`${updated.code} is now Active.`)
      setNoticeType('success')
    } catch (error) {
      setNotice(error.message)
      setNoticeType('error')
    } finally {
      setBusy(false)
    }
  }

  const title = mode === 'create'
    ? 'Create fiscal year'
    : mode === 'detail'
      ? 'Fiscal year details'
      : 'Fiscal year management'

  return (
    <div className={`fy-module${embedded ? ' embedded' : ''}`}>
      {!embedded && (
      <aside className="fy-rail" aria-label="ERP navigation">
        <a className="fy-brand" href="/" aria-label="Stackly home">
          <span className="fy-brand-mark">S</span>
          <span className="fy-brand-copy">stackly<span>one</span><small>ONE ERP PLATFORM</small></span>
        </a>
        <div className="fy-rail-caption">FINANCE</div>
        <button className="fy-rail-item active" title="Fiscal Year" aria-label="Fiscal Year" onClick={() => { setMode('list'); setNotice('') }}><span className="fy-rail-icon">▦</span><span>Fiscal year</span></button>
        <button className="fy-rail-item muted" title="Fiscal Period" aria-label="Fiscal Period" onClick={() => { setNotice('Fiscal periods are managed within each fiscal year.'); setNoticeType('info') }}><span className="fy-rail-icon">◷</span><span>Fiscal periods</span></button>
        <div className="fy-rail-caption modules-caption">WORKSPACE</div>
        <button className="fy-rail-item muted" title="Company settings" aria-label="Company settings" onClick={() => { setNotice('Company settings are managed by your ERP administrator.'); setNoticeType('info') }}><span className="fy-rail-icon">⚙</span><span>Company settings</span></button>
        <div className="fy-rail-bottom"><span className="fy-system-dot" /> All systems operational</div>
      </aside>
      )}

      <main className="fy-workspace">
        {!embedded && (
        <header className="fy-topbar">
          <div className="fy-breadcrumb">STACKLY <span>/</span> FICO <span>/</span> <b>Fiscal Year</b></div>
          <div className="fy-profile"><span className="fy-avatar">ST</span><span><b>Workspace</b><small>FICO User</small></span></div>
        </header>
        )}

        <section className="fy-content">
          <div className="fy-page-head">
            <div>
              <div className="fy-kicker">FINANCIAL CONFIGURATION</div>
              <h1>{title}<span className="fy-title-dot">.</span></h1>
              <p>Define financial-year boundaries and manage accounting periods for your company.</p>
            </div>
            {mode === 'list' && <button className="fy-primary" onClick={startCreate}><b>＋</b> New fiscal year</button>}
            {mode !== 'list' && <button className="fy-outline" onClick={() => { setMode('list'); setNotice('') }}>← Back to list</button>}
          </div>

          <div className="fy-stat-row">
            <div className="fy-stat-card"><span className="fy-stat-icon indigo">▦</span><div><small>Fiscal years</small><strong>{years.length}</strong><em>Configured records</em></div></div>
            <div className="fy-stat-card"><span className="fy-stat-icon mint">✓</span><div><small>Active years</small><strong>{activeCount}</strong><em>Available for use</em></div></div>
            <div className="fy-stat-card"><span className="fy-stat-icon amber">◷</span><div><small>Drafts awaiting review</small><strong>{draftCount}</strong><em>Not yet activated</em></div></div>
            <div className="fy-stat-card"><span className="fy-stat-icon violet">▤</span><div><small>Regular periods</small><strong>{totalPeriods}</strong><em>Across saved years</em></div></div>
          </div>

          {notice && <div className={`fy-notice ${noticeType}`} role="status">{notice}</div>}

          {mode === 'list' && <section className="fy-panel">
            <div className="fy-panel-head"><div><h2>Financial calendar</h2><p>Fiscal years configured for your company</p></div><button className="fy-refresh" onClick={() => { setLoading(true); loadYears() }} disabled={loading}>↻ Refresh</button></div>
            <div className="fy-toolbar">
              <label className="fy-search"><span>⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by code, year name, or company" /></label>
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="Filter by status"><option value="ALL">All statuses</option><option value="DRAFT">Draft</option><option value="ACTIVE">Active</option></select>
            </div>
            {loading ? <div className="fy-empty">Loading fiscal years…</div> : <div className="fy-table-wrap"><table className="fy-table"><thead><tr><th>Fiscal year</th><th>Company</th><th>Variant</th><th>Start date</th><th>End date</th><th>Periods</th><th>Status</th><th></th></tr></thead>
              <tbody>{filteredYears.map((year) => <tr key={year.id}>
                <td><div className="fy-year-code">{year.code}</div><div className="fy-year-name">{year.name}</div></td>
                <td>{year.company}</td><td>{year.variant === 'APR_MAR' ? 'Apr – Mar' : 'Jan – Dec'}</td>
                <td>{formatDate(year.start)}</td><td>{formatDate(year.end)}</td>
                <td><span className="fy-period-count">{year.period_count} periods</span></td>
                <td><span className={`fy-status ${year.status === 'ACTIVE' ? 'active' : 'draft'}`}>{year.status}</span></td>
                <td><button className="fy-view" onClick={() => openDetails(year.id)} disabled={busy}>View ↗</button></td>
              </tr>)}
                {!filteredYears.length && <tr><td colSpan="8"><div className="fy-empty">{years.length ? 'No matching fiscal years.' : 'No fiscal years yet. Create your first financial calendar.'}</div></td></tr>}
              </tbody></table></div>}
            <div className="fy-panel-foot"><span>Showing {filteredYears.length} of {years.length} records</span><span>Dates use company fiscal calendar rules</span></div>
          </section>}

          {mode === 'create' && <section className="fy-panel fy-form-panel">
            <div className="fy-panel-head"><div><h2>Set up a financial calendar</h2><p>Fields marked * are required. Periods are generated automatically.</p></div><span className="fy-step">STEP 01 <b>/</b> CONFIGURATION</span></div>
            <form onSubmit={createYear}>
              <div className="fy-form-section"><span className="fy-section-number">01</span><div><h3>Identification</h3><p>Choose the company and identify this fiscal year.</p></div></div>
              <div className="fy-form-grid">
                <Field label="Company code" name="company" value={form.company} onChange={change} error={errors.company} maxLength={30} />
                <Field label="Fiscal year code" name="code" value={form.code} onChange={change} error={errors.code} placeholder="e.g. FY2027" maxLength={20} />
                <Field label="Fiscal year name" name="name" value={form.name} onChange={change} error={errors.name} placeholder="e.g. Financial Year 2027-28" maxLength={100} />
                <label className="fy-field"><span>Fiscal year variant<i>*</i></span><select name="variant" value={form.variant} onChange={changeVariant}><option value="APR_MAR">April – March (India)</option><option value="JAN_DEC">January – December</option></select></label>
              </div>

              <div className="fy-form-section calendar"><span className="fy-section-number">02</span><div><h3>Calendar boundaries</h3><p>The selected variant determines the valid start and end dates.</p></div></div>
              <div className="fy-form-grid">
                <Field label="Start date" name="start" type="date" value={form.start} onChange={change} error={errors.start} hint={form.variant === 'APR_MAR' ? 'Must be 1 April (for example, 2026-04-01).' : 'Must be 1 January (for example, 2026-01-01).'} />
                <Field label="End date" name="end" type="date" value={form.end} onChange={change} error={errors.end} hint={form.variant === 'APR_MAR' ? 'Must be 31 March of the next year (for example, 2027-03-31).' : 'Must be 31 December of the same year (for example, 2026-12-31).'} />
                <label className="fy-field"><span>Regular accounting periods</span><input value="12 monthly periods" disabled /></label>
                <label className="fy-field"><span>Initial status</span><input value="Draft — pending review" disabled /></label>
              </div>
              <label className="fy-field fy-description"><span>Description</span><textarea name="description" rows="3" maxLength="500" value={form.description} onChange={change} placeholder="Optional purpose or notes for this financial year" /></label>

              <div className="fy-generation-card"><div className="fy-generation-icon">✦</div><div><b>Automatic period generation</b><p>12 consecutive monthly periods are generated when saved. The year and its periods are stored together as one transaction.</p></div><div className="fy-generation-badge">12 PERIODS</div></div>
              <div className="fy-form-actions"><button type="button" className="fy-outline" onClick={() => setMode('list')}>Cancel</button><button className="fy-primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save fiscal year'}</button></div>
            </form>
          </section>}

          {mode === 'detail' && selected && <section className="fy-panel fy-detail-panel">
            <div className="fy-panel-head"><div><h2>{selected.name}</h2><p>{selected.code} · {selected.company} · {selected.variant === 'APR_MAR' ? 'April – March' : 'January – December'}</p></div><span className={`fy-status ${selected.status === 'ACTIVE' ? 'active' : 'draft'}`}>{selected.status}</span></div>
            <div className="fy-detail-grid">
              <div><small>Start date</small><b>{formatDate(selected.start)}</b></div>
              <div><small>End date</small><b>{formatDate(selected.end)}</b></div>
              <div><small>Regular periods</small><b>{selected.period_count}</b></div>
              <div><small>Description</small><b>{selected.description || '—'}</b></div>
            </div>
            {selected.status === 'DRAFT' && <div className="fy-detail-actions"><button className="fy-primary" disabled={busy} onClick={activate}>{busy ? 'Activating…' : 'Approve & activate'}</button></div>}
            <h3 className="fy-period-heading">Generated accounting periods</h3>
            <div className="fy-table-wrap"><table className="fy-table"><thead><tr><th>Period</th><th>Period name</th><th>From</th><th>To</th><th>Status</th></tr></thead><tbody>
              {(selected.periods || []).map((period) => <tr key={period.id}><td>{String(period.period_number).padStart(2, '0')}</td><td>{period.name}</td><td>{formatDate(period.start_date)}</td><td>{formatDate(period.end_date)}</td><td><span className={`fy-status ${period.status === 'OPEN' ? 'active' : 'draft'}`}>{period.status}</span></td></tr>)}
              {!selected.periods?.length && <tr><td colSpan="5" className="fy-empty">No period details returned by API.</td></tr>}
            </tbody></table></div>
          </section>}

          <footer className="fy-footer"><span>STACKLY OneERP <b>·</b> FICO Configuration</span><span>Fiscal Year Management <b>·</b> Module workspace</span></footer>
        </section>
      </main>
    </div>
  )
}

export default FiscalYearModule
