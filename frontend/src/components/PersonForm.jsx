import { useState } from 'react'
import { patch, post } from '../api'
import { ErrorRetry } from '../ui'

// Add someone, or change what is recorded about them. Only what the app needs: no email address or phone number
export default function PersonForm({ s, person, preset = {}, onSaved, onCancel }) {
  const start = person || { name: '', role: '', company: '', relationship: 'none', link: '', notes: '', event_id: null, ...preset }
  const [form, setForm] = useState({ ...start, link: start.link || '', event_id: start.event_id || '' })
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const events = s.networking_events

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    const body = {
      name: form.name, role: form.role, company: form.company, relationship: form.relationship, link: form.link || null, notes: form.notes,
      event_id: form.relationship === 'event' && form.event_id ? form.event_id : null,
      ...(person ? { status: form.status } : {}),
    }
    try {
      onSaved(person ? await patch(`/api/contacts/${person.id}`, body) : await post('/api/contacts', body))
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="stack" onSubmit={submit} style={{ marginTop: 12 }}>
      <div className="grid cols-2">
        <label className="field">Name<input type="text" required maxLength={120} value={form.name} onChange={set('name')} /></label>
        <label className="field">How you know them
          <select value={form.relationship} onChange={set('relationship')}>
            {s.options.relationships.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <label className="field">Role<input type="text" maxLength={120} placeholder="Data Analyst" value={form.role} onChange={set('role')} /></label>
        <label className="field">Company<input type="text" maxLength={160} value={form.company} onChange={set('company')} /></label>
      </div>
      {form.relationship === 'event' && events.length > 0 && (
        <label className="field">Where you met
          <select value={form.event_id} onChange={set('event_id')}>
            <option value="">Not one of my saved events</option>
            {events.map((ev) => <option key={ev.id} value={ev.id}>{ev.name}</option>)}
          </select>
        </label>
      )}
      <label className="field">Profile link<input type="text" maxLength={500} placeholder="linkedin.com/in/their-name" value={form.link} onChange={set('link')} /></label>
      <label className="field">Notes<textarea rows={3} maxLength={4000} value={form.notes} onChange={set('notes')} /></label>
      {person && (
        <label className="field">Stage
          <select value={form.status} onChange={set('status')}>
            {s.options.contact_statuses.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
      )}
      <p className="small muted">No email or phone number needed. Drafts mention only how you know them.</p>
      <div className="row">
        <button className="btn" type="submit" disabled={saving}>{person ? 'Save' : 'Add'}</button>
        <button className="btn ghost" type="button" onClick={onCancel}>Cancel</button>
      </div>
      <ErrorRetry error={error} />
    </form>
  )
}
