import Icon from './Icon.jsx'

export default function Topbar({ search, onSearch, onMenu }) {
  return (
    <header className="topbar glass">
      <button className="icon-btn menu-btn" onClick={onMenu} aria-label="Open menu">
        <Icon name="Menu" size={20} />
      </button>

      <label className="search">
        <Icon name="Search" size={16} />
        <input
          type="search"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search this page..."
          aria-label="Search this page"
        />
      </label>

      <div className="topbar-right">
        <span className="chip-sample" title="This screen shows demo figures">
          <Icon name="FlaskConical" size={14} />
          Sample data
        </span>

        <button className="icon-btn bell" aria-label="Notifications, 9 unread">
          <Icon name="Bell" size={19} />
          <span className="bell-badge">9</span>
        </button>

        <button className="user" aria-label="Account menu">
          <span className="avatar">JD</span>
          <span className="user-text">
            <b>John Doe</b>
            <small>Approver</small>
          </span>
          <Icon name="ChevronDown" size={14} />
        </button>
      </div>
    </header>
  )
}
