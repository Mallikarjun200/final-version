import Icon from '../components/Icon.jsx'

export default function ComingSoon({ title, onBack }) {
  return (
    <div className="page-title soon">
      <h1>{title}</h1>
      <p>This module isn&apos;t built yet.</p>
      <section className="card glass soon-card">
        <p>
          The {title} screen will appear here once it&apos;s added. Fiscal Year is the only
          module wired to the backend so far.
        </p>
        <button className="btn-primary" onClick={onBack}>
          Back to FICO dashboard <Icon name="ArrowRight" size={14} />
        </button>
      </section>
    </div>
  )
}
