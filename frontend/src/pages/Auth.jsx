import { useState } from 'react'
import { getSupabase } from '../supabase'
import { Brand, Spinner } from '../ui'

const MIN_PASSWORD = 8
// Title and subtitle of each view; the password rule is shown under the password field instead
const TITLES = {
  signup: ['Create your account', 'You can delete your account and data at any time.'],
  signin: ['Welcome back', ''],
  forgot: ['Reset your password', 'We will email you a reset link.'],
  newpassword: ['Set a new password', ''],
}

// Supabase's wording for the common failures, in plainer terms
const friendly = (msg) => ({
  'Invalid login credentials': 'Email or password is incorrect.',
  'User already registered': 'An account with that email already exists. Sign in instead.',
  'Email not confirmed': 'Confirm your email first, using the link we sent you.',
}[msg] || msg)

export default function Auth({ mode, go, onDone }) {
  const view = TITLES[mode] ? mode : 'signin'
  const [form, setForm] = useState({ name: '', email: '', password: '', agree: false })
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const needs = { name: view === 'signup', email: view !== 'newpassword', password: view !== 'forgot' }

  const validate = () => {
    const e = {}
    if (needs.name && !form.name.trim()) e.name = 'Enter your full name.'
    if (needs.email && !/^\S+@\S+\.\S+$/.test(form.email.trim())) e.email = 'Enter a valid email address.'
    if (needs.password && (view === 'signin' ? !form.password : form.password.length < MIN_PASSWORD)) {
      e.password = view === 'signin' ? 'Enter your password.' : `Use at least ${MIN_PASSWORD} characters.`
    }
    if (view === 'signup' && !form.agree) e.agree = 'Agree to the privacy notice to continue.'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const submit = async (ev) => {
    ev.preventDefault()
    setNotice(null)
    if (!validate()) return
    setBusy(true)
    try {
      const sb = await getSupabase()
      const email = form.email.trim()
      if (view === 'signup') {
        const { data, error } = await sb.auth.signUp({ email, password: form.password, options: { data: { full_name: form.name.trim() } } })
        if (error) throw error
        if (!data.session) setNotice('Check your email to confirm your account, then sign in.')
      } else if (view === 'signin') {
        const { error } = await sb.auth.signInWithPassword({ email, password: form.password })
        if (error) throw error
      } else if (view === 'forgot') {
        await sb.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/?reset=1` })
        setNotice('If an account exists for that email, a reset link is on its way.')
      } else {
        const { error } = await sb.auth.updateUser({ password: form.password })
        if (error) throw error
        onDone?.()
      }
    } catch (e) {
      setErrors({ form: friendly(e.message) })
    } finally {
      setBusy(false)
    }
  }

  const [title, sub] = TITLES[view]
  const label = { signup: 'Create account', signin: 'Sign in', forgot: 'Send reset link', newpassword: 'Save new password' }[view]
  return (
    <main className="ob-body auth-card">
      <div className="ob-title">
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 18 }}><Brand onClick={() => go('landing')} /></div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      <form className="card stack" onSubmit={submit} noValidate>
        {needs.name && (
          <label className="field">Full name
            <input type="text" value={form.name} onChange={set('name')} autoComplete="name" autoFocus />
            {errors.name && <span className="error">{errors.name}</span>}
          </label>
        )}
        {needs.email && (
          <label className="field">Email
            <input type="email" value={form.email} onChange={set('email')} autoComplete="email" autoFocus={!needs.name} />
            {errors.email && <span className="error">{errors.email}</span>}
          </label>
        )}
        {needs.password && (
          <label className="field">{view === 'newpassword' ? 'New password' : 'Password'}
            <input type="password" value={form.password} onChange={set('password')} autoComplete={view === 'signin' ? 'current-password' : 'new-password'} />
            {view !== 'signin' && <span className="auth-hint">At least {MIN_PASSWORD} characters</span>}
            {errors.password && <span className="error">{errors.password}</span>}
          </label>
        )}
        {view === 'signin' && <button type="button" className="linkish small auth-forgot" onClick={() => go('auth', 'forgot')}>Forgot password?</button>}
        {view === 'signup' && (
          <div>
            <label className="check">
              <input type="checkbox" checked={form.agree} onChange={set('agree')} />
              <span>I agree to the <a href="#privacy" target="_blank" rel="noreferrer">privacy notice</a></span>
            </label>
            {errors.agree && <div className="error">{errors.agree}</div>}
          </div>
        )}
        {errors.form && <p className="error" role="alert">{errors.form}</p>}
        {notice && <p className="note" role="status">{notice}</p>}
        <button className="btn large" type="submit" disabled={busy}>{busy && <Spinner label="One moment" />}{label}</button>
      </form>
      <div className="row small" style={{ justifyContent: 'center', marginTop: 16, gap: 18 }}>
        {view === 'signin' && <button className="linkish" onClick={() => go('auth', 'signup')}>Create an account</button>}
        {view === 'signup' && <button className="linkish" onClick={() => go('auth', 'signin')}>Sign in</button>}
        {view === 'forgot' && <button className="linkish" onClick={() => go('auth', 'signin')}>Back to sign in</button>}
      </div>
    </main>
  )
}
