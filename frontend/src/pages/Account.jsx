import { useState } from 'react'
import { del } from '../api'
import { getSupabase } from '../supabase'
import { PageHead } from '../ui'

export default function Account({ s, signOut }) {
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const u = s.usage

  const remove = async () => {
    setBusy(true)
    setError(null)
    try {
      await del('/api/account')
      const sb = await getSupabase()
      await sb.auth.signOut({ scope: 'local' }) // the login no longer exists, so only clear this browser
      window.location.hash = ''
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  return (
    <>
      <PageHead title="Account" />
      <div className="stack" style={{ maxWidth: 620 }}>
        <section className="card">
          <h2>{s.profile.full_name}</h2>
          <p className="muted">{s.profile.email}</p>
          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn ghost" onClick={signOut}>Sign out</button>
            <a className="linkish small" href="#privacy">Privacy notice</a>
          </div>
        </section>

        <section className="card">
          <h2>Today's usage</h2>
          <p className="sub">Limits reset at midnight, UK time.</p>
          <dl className="kv">
            <dt>AI actions</dt><dd>{u.ai.used} of {u.ai.limit}</dd>
            <dt>Voice sessions</dt><dd>{u.voice.used} of {u.voice.limit}</dd>
          </dl>
        </section>

        <section className="card danger-zone">
          <h2>Delete my account</h2>
          <p className="sub">This permanently removes your login and everything in it: profile, achievements, CVs, stories, applications and journal. It cannot be undone.</p>
          <label className="field">Type DELETE to confirm
            <input type="text" value={typed} onChange={(e) => setTyped(e.target.value)} style={{ width: 200 }} autoComplete="off" />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn danger" disabled={typed !== 'DELETE' || busy} onClick={remove}>{busy ? 'Deleting' : 'Delete my account'}</button>
          </div>
        </section>
      </div>
    </>
  )
}
