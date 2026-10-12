import { useState } from 'react'
import { X } from 'lucide-react'
import { put } from '../api'

const MAX_LOCATIONS = 5

// The exact facts the app needs from every user. Typed rather than spoken, so dates and names are right.
export default function DetailsForm({ profile, onSaved, onCancel, submitLabel = 'Save' }) {
  const [form, setForm] = useState({
    full_name: profile.full_name || '',
    university: profile.university || '',
    course: profile.course || '',
    graduation: (profile.graduation_date || '').slice(0, 7),
    visa_type: profile.visa_type || '',
    visa_end_date: profile.visa_end_date || '',
    locations: profile.locations || [],
  })
  const [place, setPlace] = useState('')
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const addPlace = () => {
    const name = place.trim().replace(/,$/, '').trim()
    if (name && form.locations.length < MAX_LOCATIONS && !form.locations.some((x) => x.toLowerCase() === name.toLowerCase())) {
      setForm({ ...form, locations: [...form.locations, name] })
    }
    setPlace('')
  }
  const onPlaceKey = (e) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addPlace() }
  }

  const submit = async (ev) => {
    ev.preventDefault()
    const pending = place.trim()
    const locations = pending && form.locations.length < MAX_LOCATIONS ? [...form.locations, pending] : form.locations
    const e = {}
    if (!form.full_name.trim()) e.full_name = 'Enter your full name.'
    if (!form.university.trim()) e.university = 'Enter your university.'
    if (!form.course.trim()) e.course = 'Enter your course.'
    if (!form.graduation) e.graduation = 'Choose the month you graduate or graduated.'
    if (!form.visa_type) e.visa_type = 'Choose your visa type.'
    if (!form.visa_end_date) e.visa_end_date = 'Enter the date your visa ends.'
    if (locations.length === 0) e.locations = 'Add at least one location.'
    setErrors(e)
    if (Object.keys(e).length) return
    setBusy(true)
    try {
      const saved = await put('/api/profile', {
        full_name: form.full_name, university: form.university, course: form.course,
        graduation_date: `${form.graduation}-01`, visa_type: form.visa_type, visa_end_date: form.visa_end_date, locations,
      })
      setPlace('')
      await onSaved(saved)
    } catch (err) {
      setErrors({ form: err.message })
    } finally {
      setBusy(false)
    }
  }

  const err = (k) => errors[k] && <span className="error">{errors[k]}</span>
  return (
    <form className="stack" onSubmit={submit} noValidate>
      <label className="field">Full name<input type="text" value={form.full_name} onChange={set('full_name')} autoComplete="name" />{err('full_name')}</label>
      <div className="grid cols-2">
        <label className="field">University<input type="text" value={form.university} onChange={set('university')} />{err('university')}</label>
        <label className="field">Course<input type="text" value={form.course} onChange={set('course')} placeholder="e.g. MSc Business Analytics" />{err('course')}</label>
      </div>
      <div className="grid cols-2">
        <label className="field">Graduation month<input type="month" value={form.graduation} onChange={set('graduation')} />{err('graduation')}</label>
        <label className="field">Visa end date<input type="date" value={form.visa_end_date} onChange={set('visa_end_date')} />{err('visa_end_date')}</label>
      </div>
      <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ padding: 0, marginBottom: 6 }}>Visa type</legend>
        <div className="row">
          {[['student', 'Student visa'], ['graduate', 'Graduate visa']].map(([value, label]) => (
            <label key={value} className="check"><input type="radio" name="visa_type" checked={form.visa_type === value} onChange={() => setForm({ ...form, visa_type: value })} />{label}</label>
          ))}
        </div>
        {err('visa_type')}
      </fieldset>
      <div className="field">
        <label htmlFor="place">Preferred locations <span className="muted" style={{ fontWeight: 400 }}>(up to {MAX_LOCATIONS}; press Enter after each)</span></label>
        <div className="row">
          {form.locations.map((x) => (
            <span key={x} className="chip">{x}<button type="button" className="chip-x" aria-label={`Remove ${x}`} onClick={() => setForm({ ...form, locations: form.locations.filter((y) => y !== x) })}><X size={12} /></button></span>
          ))}
          {form.locations.length < MAX_LOCATIONS && (
            <input id="place" type="text" value={place} onChange={(e) => setPlace(e.target.value)} onKeyDown={onPlaceKey} onBlur={addPlace} placeholder="e.g. London, Remote" style={{ width: 180 }} />
          )}
        </div>
        {err('locations')}
      </div>
      {errors.form && <p className="error" role="alert">{errors.form}</p>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        {onCancel && <button type="button" className="btn ghost" onClick={onCancel}>Cancel</button>}
        <button className="btn large" type="submit" disabled={busy}>{busy ? 'Saving' : submitLabel}</button>
      </div>
    </form>
  )
}
