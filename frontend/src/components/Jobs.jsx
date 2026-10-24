import { useId, useLayoutEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { post } from '../api'

const MIN_DESCRIPTION = 30

// A job's advert text cut to two lines, with More to read the rest. More shows only when something is cut.
// Screen readers always get the whole text
export function JobText({ text, className = 'small' }) {
  const [open, setOpen] = useState(false)
  const [cut, setCut] = useState(false)
  const box = useRef(null)
  const id = useId()
  useLayoutEffect(() => {
    const el = box.current
    if (!el || open) return
    const watch = new ResizeObserver(() => setCut(el.scrollHeight > el.clientHeight + 1)) // runs once on start, then on every resize
    watch.observe(el)
    return () => watch.disconnect()
  }, [text, open])
  return (
    <div className="jobtext">
      <p id={id} ref={box} className={`${className} ${open ? '' : 'jobtext-clamp'}`}>{text}</p>
      {(cut || open) && (
        <button type="button" className="linkish small showmore-btn" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
          {open ? 'Less' : 'More'}<ChevronDown size={15} aria-hidden="true" className={open ? 'flip' : ''} />
        </button>
      )}
    </div>
  )
}

export function JobPicker({ jobs, value, onChange, allowNone = false }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Job">
      {allowNone && <option value="">General practice</option>}
      {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}, {j.company}</option>)}
    </select>
  )
}

// Add a job by pasting it. Real listings arrive in a later step; pasting stays useful after that too.
export function AddJob({ onAdded, onCancel }) {
  const [form, setForm] = useState({ title: '', company: '', description: '', url: '', location: '' })
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (ev) => {
    ev.preventDefault()
    const e = {}
    if (!form.title.trim()) e.title = 'Enter the job title.'
    if (!form.company.trim()) e.company = 'Enter the company.'
    if (form.description.trim().length < MIN_DESCRIPTION) e.description = 'Paste the full job description.'
    setErrors(e)
    if (Object.keys(e).length) return
    setBusy(true)
    try {
      const job = await post('/api/jobs', { title: form.title, company: form.company, description: form.description, url: form.url || null, location: form.location || null })
      await onAdded(job)
    } catch (err) {
      setErrors({ form: err.message })
    } finally {
      setBusy(false)
    }
  }

  const err = (k) => errors[k] && <span className="error">{errors[k]}</span>
  return (
    <form className="card stack" onSubmit={submit} noValidate>
      <h2>Add a job</h2>
      <div className="grid cols-2">
        <label className="field">Job title<input type="text" value={form.title} onChange={set('title')} autoFocus />{err('title')}</label>
        <label className="field">Company<input type="text" value={form.company} onChange={set('company')} />{err('company')}</label>
      </div>
      <label className="field">Job description
        <textarea rows={7} value={form.description} onChange={set('description')} placeholder="Paste the full advert" />
        {err('description')}
      </label>
      <div className="grid cols-2">
        <label className="field">Link <span className="muted" style={{ fontWeight: 400 }}>(optional)</span><input type="text" value={form.url} onChange={set('url')} /></label>
        <label className="field">Location <span className="muted" style={{ fontWeight: 400 }}>(optional)</span><input type="text" value={form.location} onChange={set('location')} /></label>
      </div>
      {errors.form && <p className="error" role="alert">{errors.form}</p>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        {onCancel && <button type="button" className="btn ghost" onClick={onCancel}>Cancel</button>}
        <button className="btn" type="submit" disabled={busy}>{busy ? 'Saving' : 'Save job'}</button>
      </div>
    </form>
  )
}
