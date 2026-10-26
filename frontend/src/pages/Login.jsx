import { useState } from 'react'
import './Login.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

function responseMessage(data, fallback) {
  if (typeof data?.detail === 'string') return data.detail
  if (Array.isArray(data?.detail)) return data.detail.map((item) => item.msg).filter(Boolean).join(' ')
  return fallback
}

export default function Login({ onAuthenticated }) {
  const [mode, setMode] = useState(() => new URLSearchParams(window.location.search).has('reset_token') ? 'reset' : 'login')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [resetToken] = useState(() => new URLSearchParams(window.location.search).get('reset_token') || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const endpoint = mode === 'register'
        ? 'register'
        : mode === 'forgot'
          ? 'forgot-password'
          : mode === 'reset'
            ? 'reset-password'
            : 'login'
      const body = mode === 'register'
        ? { email, display_name: displayName, password }
        : mode === 'reset'
          ? { token: resetToken, password }
          : mode === 'forgot'
            ? { email }
            : { email, password }
      const response = await fetch(`${API_BASE}/api/auth/${endpoint}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(responseMessage(data, `Request failed (${response.status}).`))
      if (mode === 'forgot') {
        setNotice(data.message)
      } else if (mode === 'reset') {
        window.history.replaceState({}, '', window.location.pathname)
        setPassword('')
        setMode('login')
        setNotice(data.message)
      } else {
        onAuthenticated(data.user)
      }
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
          <h1>{mode === 'register' ? 'Create your account' : mode === 'forgot' ? 'Forgot password?' : mode === 'reset' ? 'Choose a new password' : 'Welcome back'}</h1>
          <p>{mode === 'register'
            ? 'Register to access your private FICO workspace.'
            : mode === 'forgot'
              ? 'Enter your account email and we’ll send a secure reset link.'
              : mode === 'reset'
                ? 'Choose a new password for your Stackly OneERP account.'
                : 'Sign in to continue to your FICO workspace.'}</p>
        </div>
        {error && <div className="login-error" role="alert">{error}</div>}
        {notice && <div className="login-notice" role="status">{notice}</div>}
        <form className="login-form" onSubmit={submit}>
          {mode === 'register' && (
            <label>
              <span>Full name</span>
              <input autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required maxLength={100} />
            </label>
          )}
          {mode !== 'reset' && (
            <label>
              <span>Email address</span>
              <input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required maxLength={254} />
            </label>
          )}
          {mode !== 'forgot' && (
            <label>
              <span>{mode === 'reset' ? 'New password' : 'Password'}</span>
              <input
                type="password"
                autoComplete={mode === 'register' || mode === 'reset' ? 'new-password' : 'current-password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={mode === 'register' || mode === 'reset' ? 10 : 1}
                maxLength={128}
              />
              {(mode === 'register' || mode === 'reset') && <small>Use at least 10 characters.</small>}
            </label>
          )}
          {mode === 'login' && (
            <button className="login-forgot" type="button" onClick={() => { setMode('forgot'); setError(''); setNotice('') }}>
              Forgot password?
            </button>
          )}
          <button className="login-submit" type="submit" disabled={busy}>
            {busy
              ? 'Please wait…'
              : mode === 'register'
                ? 'Create account'
                : mode === 'forgot'
                  ? 'Send reset link'
                  : mode === 'reset'
                    ? 'Reset password'
                    : 'Sign in'}
          </button>
        </form>
        <p className="login-switch">
          {mode === 'register'
            ? <>Already registered? <button type="button" onClick={() => { setMode('login'); setError(''); setNotice('') }}>Sign in</button></>
            : mode === 'login'
              ? <>New to Stackly OneERP? <button type="button" onClick={() => { setMode('register'); setError(''); setNotice('') }}>Create an account</button></>
              : <button type="button" onClick={() => { setMode('login'); setError(''); setNotice('') }}>Back to sign in</button>}
        </p>
        <p className="login-note">Your account and module records are stored in the application database.</p>
      </section>
    </main>
  )
}
