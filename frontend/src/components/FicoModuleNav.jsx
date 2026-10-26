import { ficoNav } from '../data/ficoData.js'
import Icon from './Icon.jsx'
import './FicoModuleNav.css'

export default function FicoModuleNav({ page, onNavigate }) {
  return (
    <nav className="fico-module-nav" aria-label="FICO submodules">
      <div className="fico-module-nav-heading">
        <span>FICO WORKSPACE</span>
        <b>{ficoNav.find((item) => item.id === page)?.label || 'Financial workspace'}</b>
      </div>
      <div className="fico-module-nav-items">
        {ficoNav.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`fico-module-link${page === item.id ? ' active' : ''}`}
            aria-current={page === item.id ? 'page' : undefined}
            onClick={() => onNavigate(item.id)}
          >
            <Icon name={item.icon} size={15} />
            <span>{item.label}</span>
          </button>
        ))}
      </div>
    </nav>
  )
}
