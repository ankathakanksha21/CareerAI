import { useId, useState } from 'react'
import { ChevronUp } from 'lucide-react'
import { del } from '../api'
import { getSupabase } from '../supabase'
import { Meter, PageHead } from '../ui'

// One daily limit: its name, how close it is, and the count
function Usage({ label, used, limit }) {
  return (
    <div className="account-usage">
      <span>{label}</span>
      <Meter value={limit ? (used / limit) * 100 : 0} />
      <span><span aria-hidden="true">{used}/{limit}</span><span className="sr-only">{used} of {limit}</span></span>
    </div>
  )
}

export default function Account({ s, signOut }) {
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(false) // the delete section is closed until asked for
  const panel = useId()
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
          <p className="sub">Resets at midnight, UK time.</p>
          <div className="stack" style={{ gap: 8 }}>
            <Usage label="AI actions" used={u.ai.used} limit={u.ai.limit} />
            <Usage label="Voice calls" used={u.voice.used} limit={u.voice.limit} />
          </div>
        </section>

        {/* The toggle is the section's heading: a red outline button while closed, a plain heading once open */}
        <section className={deleting ? 'card danger-zone' : ''}>
          <h2 className="account-delete-head">
            <button type="button" className={deleting ? 'account-delete-toggle' : 'btn danger-outline'} aria-expanded={deleting} aria-controls={panel} onClick={() => setDeleting(!deleting)}>
              Delete my account{deleting && <ChevronUp size={17} aria-hidden="true" />}
            </button>
          </h2>
          <div id={panel} hidden={!deleting}>
            <p className="sub">Permanently deletes your login and everything you have saved. This cannot be undone.</p>
            <label className="field">Type DELETE to confirm
              <input type="text" value={typed} onChange={(e) => setTyped(e.target.value)} style={{ width: 200 }} autoComplete="off" />
            </label>
            {error && <p className="error" role="alert">{error}</p>}
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn danger" disabled={typed !== 'DELETE' || busy} onClick={remove}>{busy ? 'Deleting' : 'Delete my account'}</button>
            </div>
          </div>
        </section>
      </div>
    </>
  )
}
