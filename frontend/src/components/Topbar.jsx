import Icon from './Icon.jsx'

export default function Topbar({ search, onSearch, onMenu, user, onLogout, logoutError }) {
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

        <div className="user">
          <span className="avatar">{user?.display_name?.slice(0, 2).toUpperCase() || 'U'}</span>
          <span className="user-text">
            <b>{user?.display_name || 'Workspace user'}</b>
            <small>{user?.email || ''}</small>
          </span>
        </div>
        <div className="logout-control">
          {logoutError && <small role="alert">{logoutError}</small>}
          <button className="logout-btn" onClick={onLogout}>Sign out</button>
        </div>
      </div>
    </header>
  )
}
