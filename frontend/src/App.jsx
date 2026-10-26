import { useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Topbar from './components/Topbar.jsx'
import FicoDashboard from './pages/FicoDashboard.jsx'
import ComingSoon from './pages/ComingSoon.jsx'
import TrialBalance from './pages/TrialBalance.jsx'
import FiscalYearModule from './FiscalYearModule.jsx'
import { ficoNav } from './data/ficoData.js'
import './styles/shell.css'

function App() {
  const [page, setPage] = useState('home')
  const [search, setSearch] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)

  const navigate = (id) => {
    setPage(id)
    setSearch('')
    window.scrollTo({ top: 0 })
  }

  let content
  if (page === 'home') {
    content = <FicoDashboard onNavigate={navigate} search={search} />
  } else if (page === 'fiscal-year') {
    content = <FiscalYearModule embedded />
  } else if (page === 'trial-balance') {
    content = <TrialBalance search={search} onResetSearch={() => setSearch('')} />
  } else {
    const title = ficoNav.find((n) => n.id === page)?.label ?? 'Module'
    content = <ComingSoon title={title} onBack={() => navigate('home')} />
  }

  return (
    <div className="app-shell">
      <Sidebar page={page} onNavigate={navigate} open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="app-main">
        <Topbar search={search} onSearch={setSearch} onMenu={() => setMenuOpen(true)} />
        <main className="app-content">{content}</main>
      </div>
    </div>
  )
}

export default App
