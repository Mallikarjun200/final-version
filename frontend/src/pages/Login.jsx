import { useState } from 'react'
import './Login.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

function responseMessage(data, fallback) {
  if (typeof data?.detail === 'string') return data.detail
  if (Array.isArray(data?.detail)) return data.detail.map((item) => item.msg).filter(Boolean).join(' ')
  return fallback
}

export default function Login({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE}/api/auth/${mode === 'register' ? 'register' : 'login'}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mode === 'register'
          ? { email, display_name: displayName, password }
          : { email, password }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(responseMessage(data, `Request failed (${response.status}).`))
      onAuthenticated(data.user)
    } catch (requestError) {
      setError(requestError.message || 'Unable to sign in. Check your connection and try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="login-brand"><span className="login-mark">S</span><span>STACKLY <small>OneERP</small></span></div>
        <div className="login-intro">
          <p className="login-eyebrow">FINANCE WORKSPACE</p>
          <h1>{mode === 'register' ? 'Create your account' : 'Welcome back'}</h1>
          <p>{mode === 'register' ? 'Register to access your private FICO workspace.' : 'Sign in to continue to your FICO workspace.'}</p>
        </div>
        {error && <div className="login-error" role="alert">{error}</div>}
        <form className="login-form" onSubmit={submit}>
          {mode === 'register' && (
            <label>
              <span>Full name</span>
              <input autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required maxLength={100} />
            </label>
          )}
          <label>
            <span>Email address</span>
            <input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required maxLength={254} />
          </label>
          <label>
            <span>Password</span>
            <input
              type="password"
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={mode === 'register' ? 10 : 1}
              maxLength={128}
            />
            {mode === 'register' && <small>Use at least 10 characters.</small>}
          </label>
          <button className="login-submit" type="submit" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'register' ? 'Create account' : 'Sign in'}
          </button>
        </form>
        <p className="login-switch">
          {mode === 'register' ? 'Already registered?' : 'New to Stackly OneERP?'}
          {' '}
          <button onClick={() => { setMode(mode === 'register' ? 'login' : 'register'); setError('') }}>
            {mode === 'register' ? 'Sign in' : 'Create an account'}
          </button>
        </p>
        <p className="login-note">Your account and module records are stored in the application database.</p>
      </section>
    </main>
  )
}
