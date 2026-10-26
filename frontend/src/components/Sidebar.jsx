import Icon from './Icon.jsx'
import { ficoNav } from '../data/ficoData.js'

export default function Sidebar({ page, onNavigate, open, onClose }) {
  const go = (id) => {
    onNavigate(id)
    onClose?.()
  }

  return (
    <>
      <div className={`scrim ${open ? 'show' : ''}`} onClick={onClose} />
      <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Main navigation">
        <div className="brand">
          <span className="brand-dot" aria-hidden="true" />
          <span className="brand-name">STACKLY</span>
          <span className="brand-sub">OneERP</span>
          <button className="icon-btn sidebar-close" onClick={onClose} aria-label="Close menu">
            <Icon name="X" />
          </button>
        </div>

        <nav className="nav">
          <button
            className={`nav-item home ${page === 'home' ? 'active' : ''}`}
            onClick={() => go('home')}
            aria-current={page === 'home' ? 'page' : undefined}
          >
            <Icon name="House" />
            <span>Home</span>
          </button>

          <button className="nav-group" onClick={() => go('home')}>
            <Icon name="FileSpreadsheet" />
            <span>FICO</span>
            <Icon name="ChevronDown" size={16} className="group-chevron" />
          </button>

          <ul className="nav-sub">
            {ficoNav.map((item) => (
              <li key={item.id}>
                <button
                  className={`nav-item ${page === item.id ? 'active' : ''}`}
                  onClick={() => go(item.id)}
                  aria-current={page === item.id ? 'page' : undefined}
                >
                  <Icon name={item.icon} size={16} />
                  <span>{item.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
    </>
  )
}
