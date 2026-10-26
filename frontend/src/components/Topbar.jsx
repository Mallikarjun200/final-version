import { useState } from 'react'
import { apiFetch } from '../api.js'
import Icon from './Icon.jsx'

export default function Topbar({
  search,
  onSearch,
  onMenu,
  user,
  workspaces,
  activeWorkspaceId,
  onWorkspaceChange,
  onWorkspacesChange,
  onLogout,
  logoutError,
}) {
  const [showMembers, setShowMembers] = useState(false)
  const [members, setMembers] = useState([])
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('requester')
  const [loadingMembers, setLoadingMembers] = useState(false)
  const [busy, setBusy] = useState(false)
  const [memberError, setMemberError] = useState('')
  const [memberNotice, setMemberNotice] = useState('')
  const activeWorkspace = workspaces.find((workspace) => String(workspace.id) === String(activeWorkspaceId))

  async function loadMembers() {
    setLoadingMembers(true)
    setMemberError('')
    try {
      const response = await apiFetch('/api/workspaces/members')
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status}).`)
      setMembers(data)
    } catch (error) {
      setMemberError(error.message || 'Unable to load workspace members.')
    } finally {
      setLoadingMembers(false)
    }
  }

  async function refreshWorkspaces() {
    const response = await apiFetch('/api/workspaces')
    const data = await response.json()
    if (!response.ok) throw new Error(data?.detail || `Workspace request failed (${response.status}).`)
    onWorkspacesChange(data)
    if (!data.some((workspace) => String(workspace.id) === String(activeWorkspaceId)) && data.length) {
      onWorkspaceChange(data[0].id)
    }
  }

  async function saveMember(event) {
    event.preventDefault()
    setBusy(true)
    setMemberError('')
    setMemberNotice('')
    try {
      const response = await apiFetch('/api/workspaces/members', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, role }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status}).`)
      setEmail('')
      setMemberNotice(`${data.display_name} is now a ${data.role}.`)
      await loadMembers()
      await refreshWorkspaces()
    } catch (error) {
      setMemberError(error.message || 'Unable to update workspace access.')
    } finally {
      setBusy(false)
    }
  }

  async function removeMember(member) {
    if (!window.confirm(`Remove ${member.display_name} from this workspace?`)) return
    setBusy(true)
    setMemberError('')
    setMemberNotice('')
    try {
      const response = await apiFetch(`/api/workspaces/members/${member.user_id}`, { method: 'DELETE' })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data?.detail || `Request failed (${response.status}).`)
      }
      setMemberNotice(`${member.display_name} was removed from this workspace.`)
      await loadMembers()
      await refreshWorkspaces()
    } catch (error) {
      setMemberError(error.message || 'Unable to remove workspace member.')
    } finally {
      setBusy(false)
    }
  }

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
        {workspaces.length > 1 && (
          <label className="workspace-select">
            <span>Workspace</span>
            <select value={activeWorkspaceId} onChange={(event) => onWorkspaceChange(event.target.value)}>
              {workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
            </select>
          </label>
        )}
        {activeWorkspace?.role === 'admin' && (
          <button className="workspace-members-btn" onClick={() => { setShowMembers(true); setMemberNotice(''); loadMembers() }}>Manage access</button>
        )}
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
      {showMembers && (
        <div className="workspace-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setShowMembers(false) }}>
          <section className="workspace-modal" role="dialog" aria-modal="true" aria-labelledby="workspace-members-title">
            <header>
              <div><p>WORKSPACE ACCESS</p><h2 id="workspace-members-title">{activeWorkspace?.name || 'Workspace members'}</h2></div>
              <button aria-label="Close workspace access" onClick={() => setShowMembers(false)} disabled={busy}>×</button>
            </header>
            <form onSubmit={saveMember}>
              <label className="workspace-member-field">
                <span>Registered user email</span>
                <input type="email" maxLength={254} required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.com" />
              </label>
              <label className="workspace-member-field">
                <span>Role</span>
                <select value={role} onChange={(event) => setRole(event.target.value)}>
                  <option value="requester">Requester</option>
                  <option value="approver">Approver</option>
                  <option value="admin">Admin</option>
                </select>
              </label>
              <button className="workspace-members-btn" disabled={busy}>{busy ? 'Saving…' : 'Add or update member'}</button>
            </form>
            {memberError && <div className="workspace-modal-error" role="alert">{memberError}</div>}
            {memberNotice && <div className="workspace-modal-notice" role="status">{memberNotice}</div>}
            <div className="workspace-member-list">
              <h3>Current members</h3>
              {loadingMembers ? <p>Loading members…</p> : members.map((member) => (
                <div className="workspace-member-row" key={member.user_id}>
                  <span><b>{member.display_name}</b><small>{member.email}</small></span>
                  <span className="workspace-member-role">{member.role}</span>
                  {member.user_id !== activeWorkspace?.id && <button onClick={() => removeMember(member)} disabled={busy}>Remove</button>}
                </div>
              ))}
            </div>
            <p className="workspace-modal-note">Requesters create and submit drafts. Approvers can also submit drafts and review requests; self-approval is enabled. Administrators manage access and can submit and approve.</p>
          </section>
        </div>
      )}
    </header>
  )
}
