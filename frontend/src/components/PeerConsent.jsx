import { useEffect, useState } from 'react'
import { Check, ShieldCheck, X } from 'lucide-react'
import { post } from '../api'
import { ErrorRetry } from '../ui'
import { Who } from './PeerGroup'

// What a proposal shows (Who), then what the group sees once everyone has said yes (peerdb's FULL view)
const SEEN_SUGGESTED = ['First name', 'University and course', 'Target roles']
const SEEN_JOINED = ['How many weekly targets you met, and your streak', 'The one line you write each week',
  'A LinkedIn or WhatsApp link, if you share one (WhatsApp shows your phone number)',
  'Whether you have gone three weeks without an application logged with its CV, a mock interview, a message or a check-in']
const NEVER = ['Email address', 'Surname, as long as your full name starts with your given name (see below)',
  'Visa type or dates', 'Applications or the employers you apply to',
  'CVs, achievements or stories', 'Journal and interview transcripts']

// A list with a tick or a cross before each item. The heading above says which, so the icons are not read out
function Marked({ items, icon: Icon, tone }) {
  return (
    <ul className="peerconsent-list small">
      {items.map((x) => <li key={x}><Icon size={14} strokeWidth={2.5} aria-hidden="true" className={`peerconsent-${tone}`} /><span>{x}</span></li>)}
    </ul>
  )
}

// A rule of the code of conduct: its first sentence as the headline, the rest beside it, every word kept
function Rule({ text }) {
  const end = text.indexOf('. ')
  if (end < 0) return <li><strong>{text}</strong></li>
  return <li><strong>{text.slice(0, end + 1)}</strong> {text.slice(end + 2)}</li>
}

// Exactly how the group will see the user. The first name is the first word of their full name, so a name
// written surname-first shows the surname: they can see that here and put it right in Profile
function AppearsAs({ a }) {
  return (
    <div className="sub-block stack">
      <h3>Your group will see you as</h3>
      <div className="peer"><Who m={a} /></div>
      <p className="small muted">Your first name is the first word of your full name. Wrong? Put your given name first in Profile (Edit details).</p>
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
          <h4 className="peerconsent-when">As soon as you are suggested</h4>
          <Marked items={SEEN_SUGGESTED} icon={Check} tone="yes" />
          <h4 className="peerconsent-when">Once everyone says yes</h4>
          <Marked items={SEEN_JOINED} icon={Check} tone="yes" />
        </div>
        <div>
          <h3>Your group will never see</h3>
          <Marked items={NEVER} icon={X} tone="no" />
        </div>
      </div>
      <p className="small muted peerconsent-safe"><ShieldCheck size={15} aria-hidden="true" />You can leave, block or report at any time.</p>
      {s.peers.appears_as && <AppearsAs a={s.peers.appears_as} />}
      <div>
        <h3>Code of conduct</h3>
        <ol className="small peerconsent-rules">{options.conduct.map((x) => <Rule key={x} text={x} />)}</ol>
      </div>
      <label className="field">Your field
        <select required value={field} onChange={(e) => { setField(e.target.value); setSuggested(false) }}>
          <option value="">Choose your field</option>
          {options.fields.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        {suggested && <span className="small muted">Suggested from your target roles.</span>}
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
