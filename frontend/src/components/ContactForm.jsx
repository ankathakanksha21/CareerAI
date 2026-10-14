import { useState } from 'react'
import { put } from '../api'

const MAX_LINES = 12

// The contact line of every CV. All three are optional: the name and the email come from the account
export default function ContactForm({ profile, onSaved, submitLabel = 'Save', children }) {
  const [form, setForm] = useState({ phone: profile.phone || '', city: profile.city || '', linkedin_url: profile.linkedin_url || '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
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
        <label className="field">Town or city<input type="text" value={form.city} maxLength={80} onChange={set('city')} autoComplete="address-level2" placeholder="e.g. Leeds" /></label>
        <label className="field">LinkedIn address<input type="text" value={form.linkedin_url} maxLength={200} onChange={set('linkedin_url')} placeholder="linkedin.com/in/your-name" /></label>
      </div>
      <p className="small muted">A UK CV gives a town or city, never a full postal address, and no photo, date of birth or nationality. Your name and email come from your account.</p>
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

  const submit = async (ev) => {
    ev.preventDefault()
    const lines = text.split('\n').map((x) => x.trim()).filter(Boolean)
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
      <label className="field">Certifications, awards and volunteering <span className="muted" style={{ fontWeight: 400 }}>(one per line, up to {MAX_LINES})</span>
        <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={'e.g. AWS Certified Cloud Practitioner (2025)\nVolunteer maths tutor, 2 hours a week since 2024'} />
      </label>
      <p className="small muted">These print under "Additional information" on every CV you build from now on. You can hide a line on any one CV.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" type="submit" disabled={busy}>{busy ? 'Saving' : 'Save'}</button></div>
    </form>
  )
}
