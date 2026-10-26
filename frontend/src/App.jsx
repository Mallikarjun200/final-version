import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Topbar from './components/Topbar.jsx'
import FicoModuleNav from './components/FicoModuleNav.jsx'
import FicoDashboard from './pages/FicoDashboard.jsx'
import ComingSoon from './pages/ComingSoon.jsx'
import Login from './pages/Login.jsx'
import LedgerReport from './pages/LedgerReport.jsx'
import FiscalPeriodManager from './pages/FiscalPeriodManager.jsx'
import ModuleWorkbench from './pages/ModuleWorkbench.jsx'
import FiscalYearModule from './FiscalYearModule.jsx'
import ModuleInsights from './pages/ModuleInsights.jsx'
import { ficoNav } from './data/ficoData.js'
import './styles/shell.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

function App() {
  const [page, setPage] = useState('home')
  const [search, setSearch] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [user, setUser] = useState(null)
  const [authState, setAuthState] = useState('loading')
  const [authError, setAuthError] = useState('')
  const [logoutError, setLogoutError] = useState('')
  const [workspaces, setWorkspaces] = useState([])
  const [activeWorkspaceId, setActiveWorkspaceId] = useState('')
  const [workspaceReady, setWorkspaceReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/auth/me`, { credentials: 'include' })
      .then(async (response) => {
        if (response.status === 401) return null
        const data = await response.json()
        if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status}).`)
        return data
      })
      .then((currentUser) => {
        if (cancelled) return
        setUser(currentUser)
        setAuthState(currentUser ? 'authenticated' : 'unauthenticated')
      })
      .catch((error) => {
        if (cancelled) return
        setAuthError(error.message || 'Unable to connect to the server.')
        setAuthState('error')
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (authState !== 'authenticated') return undefined
    let cancelled = false
    fetch(`${API_BASE}/api/workspaces`, { credentials: 'include' })
      .then(async (response) => {
        const data = await response.json()
        if (!response.ok) throw new Error(data?.detail || `Workspace request failed (${response.status}).`)
        return data
      })
      .then((items) => {
        if (cancelled) return
        if (!items.length) throw new Error('No FICO workspace is assigned to this account.')
        const storedId = window.localStorage.getItem('stackly-workspace-id')
        const selected = items.find((item) => String(item.id) === storedId) || items[0]
        window.localStorage.setItem('stackly-workspace-id', String(selected.id))
        setWorkspaces(items)
        setActiveWorkspaceId(String(selected.id))
        setWorkspaceReady(true)
      })
      .catch((error) => {
        if (cancelled) return
        setAuthError(error.message || 'Unable to load your workspaces.')
        setAuthState('error')
      })
    return () => { cancelled = true }
  }, [authState])

  async function logout() {
    setLogoutError('')
    try {
      const response = await fetch(`${API_BASE}/api/auth/logout`, { method: 'POST', credentials: 'include' })
      if (!response.ok) throw new Error(`Sign out failed (${response.status}).`)
      setUser(null)
      setPage('home')
      setSearch('')
      window.localStorage.removeItem('stackly-workspace-id')
      setWorkspaces([])
      setActiveWorkspaceId('')
      setWorkspaceReady(false)
      setAuthState('unauthenticated')
    } catch (error) {
      setLogoutError(error.message || 'Unable to sign out.')
    }
  }

  if (authState === 'loading') {
    return <main className="auth-loading">Loading your workspace…</main>
  }
  if (authState === 'error') {
    return <main className="auth-loading"><p role="alert">{authError}</p><button onClick={() => window.location.reload()}>Retry</button></main>
  }
  if (authState === 'unauthenticated') {
    return <Login onAuthenticated={(currentUser) => { setUser(currentUser); setAuthState('authenticated') }} />
  }
  if (!workspaceReady) {
    return <main className="auth-loading">Loading your FICO workspace…</main>
  }

  const navigate = (id) => {
    setPage(id)
    setSearch('')
    window.scrollTo({ top: 0 })
  }
  const activeWorkspace = workspaces.find((workspace) => String(workspace.id) === activeWorkspaceId)

  let content
  if (page === 'home') {
    content = <FicoDashboard onNavigate={navigate} search={search} />
  } else if (page === 'fiscal-year') {
    content = <FiscalYearModule embedded role={activeWorkspace?.role} />
  } else if (page === 'trial-balance') {
    content = <LedgerReport mode="trial-balance" search={search} />
  } else if (page === 'general-ledger') {
    content = <LedgerReport mode="general-ledger" search={search} />
  } else if (page === 'fiscal-period') {
    content = <FiscalPeriodManager onNavigate={navigate} role={activeWorkspace?.role} />
  } else if (page === 'financial-reports') {
    content = <ModuleInsights moduleId="financial-reports" />
  } else if (ficoNav.some((item) => item.id === page)) {
    content = <ModuleWorkbench key={page} moduleId={page} search={search} onNavigate={navigate} role={activeWorkspace?.role} />
  } else {
    const title = ficoNav.find((n) => n.id === page)?.label ?? 'Module'
    content = <ComingSoon title={title} onBack={() => navigate('home')} />
  }

  return (
    <div className="app-shell">
      <Sidebar page={page} onNavigate={navigate} open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="app-main">
        <Topbar
          search={search}
          onSearch={setSearch}
          onMenu={() => setMenuOpen(true)}
          user={user}
          workspaces={workspaces}
          activeWorkspaceId={activeWorkspaceId}
          onWorkspaceChange={(workspaceId) => {
            window.localStorage.setItem('stackly-workspace-id', String(workspaceId))
            setActiveWorkspaceId(String(workspaceId))
          }}
          onWorkspacesChange={(items) => setWorkspaces(items)}
          onLogout={logout}
          logoutError={logoutError}
        />
        <main className="app-content" key={activeWorkspaceId}>
          {page !== 'home' && <FicoModuleNav page={page} onNavigate={navigate} />}
          {content}
        </main>
      </div>
    </div>
  )
}

export default App
