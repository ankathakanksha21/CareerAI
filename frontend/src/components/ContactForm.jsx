import { useId, useState } from 'react'
import { put } from '../api'
import { InfoTip } from '../ui'

const MAX_LINES = 12
const nonEmpty = (text) => text.split('\n').map((x) => x.trim()).filter(Boolean)

// The contact line of every CV. All three are optional: the name and the email come from the account
export default function ContactForm({ profile, onSaved, submitLabel = 'Save', children }) {
  const [form, setForm] = useState({ phone: profile.phone || '', city: profile.city || '', linkedin_url: profile.linkedin_url || '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const cityId = useId()
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (ev) => {
    ev.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onSaved(await put('/api/profile/contact', form))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="grid cols-3">
        <label className="field">Phone<input type="text" value={form.phone} maxLength={40} onChange={set('phone')} autoComplete="tel" placeholder="e.g. 07700 900123" /></label>
        <div className="field contact-field">
          <span className="contact-label">
            <label htmlFor={cityId}>Town or city</label>
            <InfoTip label="What a UK CV includes">UK CVs give a town or city only: no full address, photo, date of birth or nationality.</InfoTip>
          </span>
          <input id={cityId} type="text" value={form.city} maxLength={80} onChange={set('city')} autoComplete="address-level2" placeholder="e.g. Leeds" />
        </div>
        <label className="field">LinkedIn<input type="text" value={form.linkedin_url} maxLength={200} onChange={set('linkedin_url')} placeholder="linkedin.com/in/your-name" /></label>
      </div>
      <p className="small muted">Name and email come from your account.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        {children}
        <button className="btn" type="submit" disabled={busy}>{busy ? 'Saving' : submitLabel}</button>
      </div>
    </form>
  )
}

// Certifications, awards and volunteering: one line each, printed under "Additional information" on every new CV
export function AdditionalLines({ profile, onSaved }) {
  const [text, setText] = useState((profile.additional || []).join('\n'))
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const id = useId()
  const lineCount = nonEmpty(text).length // counted the way the save counts them

  const submit = async (ev) => {
    ev.preventDefault()
    const lines = nonEmpty(text)
    if (lines.length > MAX_LINES) return setError(`Keep to ${MAX_LINES} lines.`)
    if (lines.some((x) => x.length > 200)) return setError('Keep each line under 200 characters.')
    setBusy(true)
    setError(null)
    try {
      const saved = await put('/api/profile/additional', { lines })
      setText(saved.additional.join('\n'))
      await onSaved(saved)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="field contact-field">
        <span className="contact-label">
          <label htmlFor={id}>Certifications, awards and volunteering <span className="muted" style={{ fontWeight: 400 }}>(one per line)</span></label>
          <span className="spacer" />
          <span className="small muted" style={{ fontWeight: 400 }}>{lineCount}/{MAX_LINES}<span className="sr-only"> lines</span></span>
        </span>
        <textarea id={id} rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={'e.g. AWS Certified Cloud Practitioner (2025)\nVolunteer maths tutor, 2 hours a week since 2024'} />
      </div>
      <p className="small muted">Printed under "Additional information" on new CVs. You can hide a line on any one CV.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" type="submit" disabled={busy}>{busy ? 'Saving' : 'Save'}</button></div>
    </form>
  )
}
