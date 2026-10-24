import { useState } from 'react'
import { Pencil, Trash2, X } from 'lucide-react'
import { del, patch, post, put } from '../api'
import { attempt, period } from '../ui'

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const THIS_YEAR = new Date().getFullYear()
const YEARS = Array.from({ length: 52 }, (_, i) => THIS_YEAR + 6 - i) // a course ending within six years, back to a long career
const MAX_SKILLS = 60
const MAX_LANGUAGES = 10

const JOB_FIELDS = [
  { key: 'employer', label: 'Employer', type: 'text', max: 160 },
  { key: 'job_title', label: 'Job title', type: 'text', max: 160 },
  { key: 'location', label: 'Town or city', type: 'text', max: 120 },
  { key: 'country', label: 'Country', type: 'text', max: 80 },
  { key: 'start_month', label: 'Started', type: 'month' },
  { key: 'end_month', label: 'Ended', type: 'month', offWhen: 'is_current' },
  { key: 'is_current', label: 'I still work here', type: 'check' },
  { key: 'employer_context', label: 'What the employer does, for a UK reader', type: 'text', max: 300, wide: true, placeholder: 'e.g. A logistics company with 40 depots across India' },
]
const COURSE_FIELDS = [
  { key: 'institution', label: 'University, college or school', type: 'text', max: 160 },
  { key: 'qualification', label: 'Qualification', type: 'text', max: 120, placeholder: 'e.g. MSc, BTech, A levels' },
  { key: 'subject', label: 'Subject', type: 'text', max: 160 },
  { key: 'country', label: 'Country', type: 'text', max: 80 },
  { key: 'start_month', label: 'Start', type: 'month' },
  { key: 'end_month', label: 'End', type: 'month' },
  { key: 'grade', label: 'Grade', type: 'text', max: 80, wide: true, placeholder: 'e.g. 2:1, Merit, CGPA 8.4/10' },
]
const SET_IN_DETAILS = ['institution', 'qualification', 'end_month'] // the current course takes these from "Your details"

// A month and a year. value is '' or "YYYY-MM-01"; onChange gets the same once both are chosen, '' otherwise
function MonthPicker({ label, value, onChange, disabled }) {
  const [month, setMonth] = useState(value ? value.slice(5, 7) : '')
  const [year, setYear] = useState(value ? value.slice(0, 4) : '')
  const set = (m, y) => { setMonth(m); setYear(y); onChange(m && y ? `${y}-${m}-01` : '') }
  const years = year && !YEARS.includes(+year) ? [+year, ...YEARS] : YEARS
  return (
    <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend style={{ padding: 0, marginBottom: 4 }}>{label}</legend>
      <div className="month">
        <select value={disabled ? '' : month} disabled={disabled} onChange={(e) => set(e.target.value, year)} aria-label={`${label}: month`}>
          <option value="">Month</option>
          {MONTHS.map((m, i) => <option key={m} value={String(i + 1).padStart(2, '0')}>{m}</option>)}
        </select>
        <select value={disabled ? '' : year} disabled={disabled} onChange={(e) => set(month, e.target.value)} aria-label={`${label}: year`}>
          <option value="">Year</option>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>
    </fieldset>
  )
}

// The add and edit form for one job or course. `locked` fields are shown but cannot be changed here
function EntryForm({ fields, initial, locked = [], lockedNote, onSave, onCancel }) {
  const [form, setForm] = useState(() => Object.fromEntries(fields.map((f) => [f.key, initial?.[f.key] ?? (f.type === 'check' ? false : '')])))
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (key, value) => setForm((was) => ({ ...was, [key]: value }))

  const submit = async (ev) => {
    ev.preventDefault()
    const name = fields[0]
    if (!form[name.key].trim()) return setError(`Enter the ${name.label.toLowerCase()}.`)
    const body = {}
    for (const f of fields) {
      if (!locked.includes(f.key)) body[f.key] = f.type === 'month' ? form[f.key] || null : form[f.key]
    }
    if (body.is_current) body.end_month = null
    const end = 'end_month' in body ? body.end_month : initial?.end_month
    if (body.start_month && end && end < body.start_month) return setError('The end month cannot be before the start month.')
    setBusy(true)
    setError(null)
    try {
      await onSave(body)
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="grid cols-2">
        {fields.map((f) => {
          const off = locked.includes(f.key) || (f.offWhen && form[f.offWhen])
          if (f.type === 'month') return <MonthPicker key={f.key} label={f.label} value={form[f.key]} disabled={off} onChange={(v) => set(f.key, v)} />
          if (f.type === 'check') return <label key={f.key} className="check" style={{ alignSelf: 'end', paddingBottom: 8 }}><input type="checkbox" checked={form[f.key]} onChange={(e) => set(f.key, e.target.checked)} />{f.label}</label>
          return (
            <label key={f.key} className="field" style={f.wide ? { gridColumn: '1 / -1' } : undefined}>{f.label}
              <input type="text" value={form[f.key]} maxLength={f.max} disabled={off} placeholder={f.placeholder} onChange={(e) => set(f.key, e.target.value)} />
            </label>
          )
        })}
      </div>
      {lockedNote && <p className="small muted">{lockedNote}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button type="button" className="btn ghost" onClick={onCancel}>Cancel</button>
        <button className="btn" type="submit" disabled={busy}>{busy ? 'Saving' : 'Save'}</button>
      </div>
    </form>
  )
}

// One list of jobs or courses, with add, edit and delete
function Entries({ title, hint, noun, addLabel, emptyText, items, path, fields, line, place, refresh, notify }) {
  const [editing, setEditing] = useState(null) // an entry's id, "new", or nothing
  const save = (entry) => async (body) => {
    if (entry) await patch(`${path}/${entry.id}`, body)
    else await post(path, body)
    await refresh()
    setEditing(null)
    notify(`${noun} saved`)
  }
  const remove = async (entry) => {
    if (!window.confirm(`Delete this ${noun.toLowerCase()}? Achievements linked to it are kept.`)) return
    await attempt(notify)(async () => {
      await del(`${path}/${entry.id}`)
      await refresh()
      notify(`${noun} deleted`)
    })
  }

  return (
    <div className="section">
      <div className="section-head">
        <h2>{title} ({items.length})</h2>
        {hint && <p>{hint}</p>}
        <span className="spacer" />
        {editing !== 'new' && <button className="btn ghost small" onClick={() => setEditing('new')}>{addLabel}</button>}
      </div>
      <div className={`card ${editing ? 'editing' : ''}`}>
        {items.length === 0 && editing !== 'new' && <p className="muted">{emptyText}</p>}
        <div className="list">
          {items.map((e) => (editing === e.id ? (
            <EntryForm key={e.id} fields={fields} initial={e} onSave={save(e)} onCancel={() => setEditing(null)}
              locked={e.from_details ? SET_IN_DETAILS : []}
              lockedNote={e.from_details && 'Your current course: change its university, name or end month in Edit details at the top of the page.'} />
          ) : (
            <div key={e.id} className="entry">
              <div className="who">
                <div className="strong">{line(e)}</div>
                <div className="small muted">
                  {[period(e), place(e)].filter(Boolean).join(' · ')}
                  {!period(e) && <>{place(e) && ' · '}<button className="linkish" onClick={() => setEditing(e.id)}>Add dates</button></>}
                </div>
                {e.employer_context && <div className="small muted">{e.employer_context}</div>}
              </div>
              <div className="acts">
                <button className="icon-btn calm" aria-label={`Edit ${line(e)}`} title={`Edit ${line(e)}`} onClick={() => setEditing(e.id)}><Pencil size={16} aria-hidden="true" /></button>
                {e.from_details
                  ? <span className="small muted">From your details</span>
                  : <button className="icon-btn" aria-label={`Delete ${line(e)}`} title={`Delete ${line(e)}`} onClick={() => remove(e)}><Trash2 size={16} aria-hidden="true" /></button>}
              </div>
            </div>
          )))}
          {editing === 'new' && <EntryForm fields={fields} onSave={save(null)} onCancel={() => setEditing(null)} />}
        </div>
      </div>
    </div>
  )
}

const both = (...parts) => parts.filter(Boolean).join(', ')

export function WorkHistory({ s, refresh, notify }) {
  return (
    <Entries title="Work history" hint="Include internships and placements." noun="Job" addLabel="Add a job"
      emptyText="No jobs yet. Add one, or upload your CV above."
      items={s.work_history} path="/api/work-history" fields={JOB_FIELDS} refresh={refresh} notify={notify}
      line={(e) => both(e.job_title, e.employer)} place={(e) => both(e.location, e.country)} />
  )
}

export function Education({ s, refresh, notify }) {
  return (
    <Entries title="Education" noun="Course" addLabel="Add a course"
      emptyText="No courses yet. Add one, or upload your CV above."
      items={s.education} path="/api/education" fields={COURSE_FIELDS} refresh={refresh} notify={notify}
      line={(e) => both(`${e.qualification} ${e.subject}`.trim(), e.institution)} place={(e) => both(e.country, e.grade)} />
  )
}

// Skills as tags and spoken languages with a level. Each change is saved as it is made
export function Skills({ s, refresh, notify }) {
  const { skills, languages } = s.profile
  const [skill, setSkill] = useState('')
  const [language, setLanguage] = useState('')
  const [level, setLevel] = useState('')
  const save = (nextSkills, nextLanguages) => attempt(notify)(async () => {
    await put('/api/profile/skills', { skills: nextSkills, languages: nextLanguages })
    await refresh()
  })
  const known = (name) => skills.some((x) => x.toLowerCase() === name.toLowerCase())
  const addSkill = () => {
    const names = [...new Set(skill.split(',').map((x) => x.trim()).filter((x) => x && !known(x)))].slice(0, MAX_SKILLS - skills.length)
    setSkill('')
    if (names.length) save([...skills, ...names], languages)
  }
  const addLanguage = (ev) => {
    ev.preventDefault()
    const name = language.trim()
    if (!name || languages.some((x) => x.language.toLowerCase() === name.toLowerCase())) return
    setLanguage('')
    setLevel('')
    save(skills, [...languages, { language: name, level }])
  }

  return (
    <div className="section">
      <div className="section-head"><h2>Skills and languages</h2></div>
      <div className="card stack">
        <div className="field">
          <label htmlFor="skill">Skills</label>
          <div className="row">
            {skills.map((x) => (
              <span key={x} className="chip">{x}<button type="button" className="chip-x" aria-label={`Remove ${x}`} onClick={() => save(skills.filter((y) => y !== x), languages)}><X size={12} /></button></span>
            ))}
            {skills.length < MAX_SKILLS && (
              <input id="skill" type="text" value={skill} maxLength={60} style={{ width: 200 }} placeholder={skills.length ? 'Add a skill, then Enter' : 'e.g. SQL, Excel, Power BI'}
                onChange={(e) => setSkill(e.target.value)} onBlur={addSkill}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addSkill() } }} />
            )}
          </div>
          {skills.length === 0 && <span className="small muted" style={{ fontWeight: 400 }}>No skills yet. Type one, or upload your CV above.</span>}
        </div>
        <div className="field">
          <span>Languages</span>
          <div className="row">
            {languages.map((x) => (
              <span key={x.language} className="chip">{x.level ? `${x.language} (${x.level})` : x.language}
                <button type="button" className="chip-x" aria-label={`Remove ${x.language}`} onClick={() => save(skills, languages.filter((y) => y !== x))}><X size={12} /></button>
              </span>
            ))}
          </div>
          {languages.length < MAX_LANGUAGES && (
            <form className="form-row" onSubmit={addLanguage}>
              <input type="text" value={language} maxLength={40} style={{ width: 200 }} placeholder="e.g. Hindi" aria-label="Language" onChange={(e) => setLanguage(e.target.value)} />
              <select value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Level">
                <option value="">Level</option>
                {s.options.language_levels.map((x) => <option key={x} value={x}>{x}</option>)}
              </select>
              <button className="btn ghost small" type="submit" disabled={!language.trim()}>Add language</button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
