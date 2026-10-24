import { useState } from 'react'
import { X } from 'lucide-react'
import { put } from '../api'

const MAX_LOCATIONS = 5
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const THIS_YEAR = new Date().getFullYear()
const YEARS = Array.from({ length: 13 }, (_, i) => THIS_YEAR - 6 + i) // graduated up to 6 years ago, or graduating within 6

// The exact facts the app needs from every user. Typed rather than spoken, so dates and names are right.
export default function DetailsForm({ profile, onSaved, onCancel, submitLabel = 'Save' }) {
  const [form, setForm] = useState({
    full_name: profile.full_name || '',
    university: profile.university || '',
    course: profile.course || '',
    grad_month: (profile.graduation_date || '').slice(5, 7),
    grad_year: (profile.graduation_date || '').slice(0, 4),
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
    if (!form.grad_month || !form.grad_year) e.graduation = 'Choose your graduation month and year.'
    if (!form.visa_type) e.visa_type = 'Choose your visa type.'
    if (!form.visa_end_date) e.visa_end_date = 'Enter the date your visa ends.'
    if (locations.length === 0) e.locations = 'Add at least one location.'
    setErrors(e)
    if (Object.keys(e).length) return
    setBusy(true)
    try {
      const saved = await put('/api/profile', {
        full_name: form.full_name, university: form.university, course: form.course,
        graduation_date: `${form.grad_year}-${form.grad_month}-01`, visa_type: form.visa_type, visa_end_date: form.visa_end_date, locations,
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
      <div className="grid cols-2">
        <label className="field">Full name<input type="text" value={form.full_name} onChange={set('full_name')} autoComplete="name" />{err('full_name')}</label>
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend style={{ padding: 0, marginBottom: 4 }}>Graduation</legend>
          <div className="row" style={{ gap: 8 }}>
            <select value={form.grad_month} onChange={set('grad_month')} aria-label="Graduation month">
              <option value="">Month</option>
              {MONTHS.map((m, i) => <option key={m} value={String(i + 1).padStart(2, '0')}>{m}</option>)}
            </select>
            <select value={form.grad_year} onChange={set('grad_year')} aria-label="Graduation year">
              <option value="">Year</option>
              {(form.grad_year && !YEARS.includes(+form.grad_year) ? [+form.grad_year, ...YEARS] : YEARS).map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          {err('graduation')}
        </fieldset>
      </div>
      <div className="grid cols-2">
        <label className="field">University<input type="text" value={form.university} onChange={set('university')} />{err('university')}</label>
        <label className="field">Course<input type="text" value={form.course} onChange={set('course')} placeholder="e.g. MSc Business Analytics" />{err('course')}</label>
      </div>
      <div className="grid cols-2">
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend style={{ padding: 0, marginBottom: 6 }}>Visa type</legend>
          <div className="row">
            {[['student', 'Student'], ['graduate', 'Graduate']].map(([value, label]) => (
              <label key={value} className="check"><input type="radio" name="visa_type" checked={form.visa_type === value} onChange={() => setForm({ ...form, visa_type: value })} />{label}</label>
            ))}
          </div>
          {err('visa_type')}
        </fieldset>
        <label className="field">Visa end date<input type="date" value={form.visa_end_date} onChange={set('visa_end_date')} />{err('visa_end_date')}</label>
      </div>
      <div className="field">
        <div className="row">
          <label htmlFor="place">Preferred locations</label>
          <span className="spacer" />
          <span className="small muted">{form.locations.length}/{MAX_LOCATIONS}<span className="sr-only"> added</span></span>
        </div>
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
