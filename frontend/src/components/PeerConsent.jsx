import { useEffect, useState } from 'react'
import { post } from '../api'
import { ErrorRetry } from '../ui'
import { Who } from './PeerGroup'

const SEEN = ['Your first name', 'Your university and course', 'Your target roles', 'How many of your weekly targets you met, and your streak',
  'The one line you write each week', 'A LinkedIn or WhatsApp link, only if you choose to share one',
  'Whether you have done nothing that counts (an application logged with its CV, a mock interview, a message or a check-in) for three weeks']
const NEVER = ['Your email address', 'Your surname, as long as your full name starts with your given name (see below)',
  'Your visa type or dates', 'Your applications or the employers you apply to',
  'Your CVs, achievements or stories', 'Your journal and interview transcripts']

// Exactly how the group will see the user. The first name is the first word of their full name, so a name
// written surname-first shows the surname: they can see that here and put it right in Profile
function AppearsAs({ a }) {
  return (
    <div className="sub-block stack">
      <h3>Your group will see you as</h3>
      <div className="peer"><Who m={a} /></div>
      <p className="small muted">Your first name is the first word of your full name. If that word is your surname, or not the name you go by, put your given name first in Profile (Edit details).</p>
    </div>
  )
}

// What switching Peers on means, in two columns, then the two confirmations and the field to match on
export default function PeerConsent({ s, refresh, notify, onCancel }) {
  const { options } = s.peers
  const [field, setField] = useState(s.peers.field || '')
  const [suggested, setSuggested] = useState(false)
  const [over18, setOver18] = useState(false)
  const [conduct, setConduct] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  // one suggestion from the target roles when the screen opens; without it the user picks by hand
  useEffect(() => {
    if (!s.config.llm || s.peers.field) return
    let live = true
    post('/api/ai/peers/field').then((r) => { if (live && r.field) { setField((f) => f || r.field); setSuggested(true) } }).catch(() => {})
    return () => { live = false }
  }, [s.config.llm, s.peers.field])

  const join = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await post('/api/peers/join', { over_18: over18, conduct, field })
      await refresh()
      notify('Buddy groups are on')
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="card stack" onSubmit={join}>
      <h2>Join a buddy group</h2>
      <div className="grid cols-2">
        <div>
          <h3>Your group will see</h3>
          <ul className="dots small">{SEEN.map((x) => <li key={x}>{x}</li>)}</ul>
        </div>
        <div>
          <h3>Your group will never see</h3>
          <ul className="dots small">{NEVER.map((x) => <li key={x}>{x}</li>)}</ul>
        </div>
      </div>
      <p className="small muted">Before everyone in a group has said yes, they see only your first name, university, course and target roles. A WhatsApp link shows your phone number to your group. You can leave, block or report at any time.</p>
      {s.peers.appears_as && <AppearsAs a={s.peers.appears_as} />}
      <div>
        <h3>Code of conduct</h3>
        <ol className="small">{options.conduct.map((x) => <li key={x}>{x}</li>)}</ol>
      </div>
      <label className="field">Your field
        <select required value={field} onChange={(e) => { setField(e.target.value); setSuggested(false) }}>
          <option value="">Choose your field</option>
          {options.fields.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        {suggested && <span className="small muted">Suggested from your target roles. Change it if it is wrong.</span>}
      </label>
      <label className="check"><input type="checkbox" checked={over18} onChange={(e) => setOver18(e.target.checked)} />I am 18 or over</label>
      <label className="check"><input type="checkbox" checked={conduct} onChange={(e) => setConduct(e.target.checked)} />I agree to the code of conduct</label>
      <div className="row">
        <button className="btn" type="submit" disabled={saving || !over18 || !conduct || !field}>Join</button>
        <button className="btn ghost" type="button" onClick={onCancel}>Cancel</button>
      </div>
      <ErrorRetry error={error} />
    </form>
  )
}
