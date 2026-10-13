import { useState } from 'react'
import { del, patch, post } from '../api'
import { ErrorRetry, QUOTE_LABEL, Quote, attempt, useAction } from '../ui'

const both = (...parts) => parts.filter(Boolean).join(', ')
const jobName = (e) => both(e.job_title, e.employer)
const courseName = (e) => both(`${e.qualification} ${e.subject}`.trim(), e.institution)

// Where an achievement happened, as one value for a list: "w:<job id>", "e:<course id>" or ""
const placeOf = (a) => (a.work_history_id ? `w:${a.work_history_id}` : a.education_id ? `e:${a.education_id}` : '')
const linkFor = (place) => ({ work_history_id: place.startsWith('w:') ? place.slice(2) : null, education_id: place.startsWith('e:') ? place.slice(2) : null })

function EditForm({ a, s, onSave, onCancel }) {
  const [form, setForm] = useState({ title: a.title, uk_version: a.uk_version, outcome: a.outcome, scale: a.scale,
    skills: a.skills.join(', '), context_note: a.context_note, place: placeOf(a) })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (ev) => {
    ev.preventDefault()
    if (!form.title.trim() || !form.uk_version.trim()) return setError('An achievement needs a title and its CV bullet.')
    setBusy(true)
    setError(null)
    try {
      await onSave({ title: form.title, uk_version: form.uk_version, outcome: form.outcome, scale: form.scale, context_note: form.context_note,
        skills: [...new Set(form.skills.split(',').map((x) => x.trim()).filter(Boolean))].slice(0, 20), ...linkFor(form.place) })
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      <label className="field">Title<input type="text" value={form.title} maxLength={160} onChange={set('title')} /></label>
      <label className="field">CV bullet<textarea rows={3} value={form.uk_version} maxLength={600} onChange={set('uk_version')} /></label>
      {a.raw && <p className="small muted">{QUOTE_LABEL[a.source]}: "{a.raw}". The quote is kept as it is, as the record of where this came from.</p>}
      <label className="field">Result<input type="text" value={form.outcome} maxLength={300} onChange={set('outcome')} placeholder="e.g. Late deliveries fell by 8%" /></label>
      <label className="field">Scale<input type="text" value={form.scale} maxLength={200} onChange={set('scale')} placeholder="e.g. 15 depot managers" /></label>
      <label className="field">Skills, separated by commas<input type="text" value={form.skills} onChange={set('skills')} /></label>
      <label className="field">Where did this happen?
        <select value={form.place} onChange={set('place')}>
          <option value="">Not linked to a job or course</option>
          {s.work_history.length > 0 && <optgroup label="Work history">{s.work_history.map((e) => <option key={e.id} value={`w:${e.id}`}>{jobName(e)}</option>)}</optgroup>}
          {s.education.length > 0 && <optgroup label="Education">{s.education.map((e) => <option key={e.id} value={`e:${e.id}`}>{courseName(e)}</option>)}</optgroup>}
        </select>
      </label>
      <label className="field">Note for UK recruiters<textarea rows={2} value={form.context_note} maxLength={600} onChange={set('context_note')} /></label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button type="button" className="btn ghost small" onClick={onCancel}>Cancel</button>
        <button className="btn small" type="submit" disabled={busy}>{busy ? 'Saving' : 'Save'}</button>
      </div>
    </form>
  )
}

/*
  One achievement on the Profile page: the UK bullet, the words it came from, where it happened.
  Everything but the quote can be edited by hand. "Improve with AI" rewrites the bullet from the
  achievement's own facts and a one-line note, saves it, and offers to undo.
*/
export default function AchievementCard({ a, s, refresh, notify, onStar, starring }) {
  const [mode, setMode] = useState(null) // "edit", "improve" or nothing
  const [note, setNote] = useState('')
  const [undo, setUndo] = useState(null) // the bullet, result and scale an improvement replaced
  const job = s.work_history.find((e) => e.id === a.work_history_id)
  const course = s.education.find((e) => e.id === a.education_id)
  const where = job ? jobName(job) : course ? courseName(course) : ''
  // a result that is only the "Add a number: what to measure" marker is a prompt, not a result
  const marker = /^add a number/i.test(a.outcome)
  const result = marker ? '' : a.outcome

  const save = async (body) => {
    await patch(`/api/achievements/${a.id}`, body)
    await refresh()
    setMode(null)
    notify('Achievement saved')
  }
  const improve = useAction(async (text) => {
    const r = await post(`/api/ai/achievements/${a.id}/improve`, { note: text })
    await refresh()
    setUndo(r.previous)
    setMode(null)
    setNote('')
  })
  const undoIt = () => attempt(notify)(async () => {
    await patch(`/api/achievements/${a.id}`, undo)
    await refresh()
    setUndo(null)
    notify('Put back as it was')
  })
  const remove = async () => {
    if (!window.confirm('Delete this achievement?')) return
    await attempt(notify)(async () => {
      await del(`/api/achievements/${a.id}`)
      await refresh()
      notify('Achievement deleted')
    })
  }

  if (mode === 'edit') return <article className="card evidence-card editing"><EditForm a={a} s={s} onSave={save} onCancel={() => setMode(null)} /></article>

  return (
    <article className="card evidence-card">
      <div>
        <h3>{a.title}</h3>
        {where && <p className="small muted">{where}</p>}
      </div>
      <p className="uk">{a.uk_version}</p>
      <Quote a={a} />
      {a.source_url && <a className="small linkish" href={a.source_url} target="_blank" rel="noopener noreferrer">View the repository</a>}
      {(result || a.scale) && (
        <dl className="kv">
          {result && <><dt>Result</dt><dd>{result}</dd></>}
          {a.scale && <><dt>Scale</dt><dd>{a.scale}</dd></>}
        </dl>
      )}
      <div className="row">{a.skills.map((k) => <span key={k} className="chip">{k}</span>)}</div>
      {a.context_note && <p className="context">{a.context_note}</p>}
      {undo && <p className="small" role="status">Rewritten. <button className="linkish" onClick={undoIt}>Undo</button></p>}

      {mode === 'improve' ? (
        <form className="stack" onSubmit={(e) => { e.preventDefault(); improve.run(note) }}>
          <label className="field">{a.needs_number ? 'What is the number? One line is enough' : 'What should it say better? One line is enough'}
            <input type="text" value={note} maxLength={300} autoFocus onChange={(e) => setNote(e.target.value)}
              placeholder={a.needs_number ? 'e.g. 15 managers used it and late deliveries fell 8%' : 'e.g. mention that I led the team of four'} />
          </label>
          <p className="small muted">The AI uses only what is on this card and what you type here.</p>
          <ErrorRetry error={improve.error} onRetry={improve.retry} />
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="btn ghost small" onClick={() => setMode(null)}>Cancel</button>
            <button className="btn small" type="submit" disabled={improve.loading}>{improve.loading ? 'Rewriting' : 'Rewrite the bullet'}</button>
          </div>
        </form>
      ) : (
        <>
          {a.needs_number && (
            <button className="chip warn chip-btn" style={{ justifySelf: 'start', whiteSpace: 'normal', textAlign: 'left' }} onClick={() => setMode('improve')}>
              {marker && a.outcome.length > 14 ? a.outcome : 'Add a number'}
            </button>
          )}
          <div className="row">
            <button className="linkish small" onClick={() => setMode('edit')}>Edit</button>
            <button className="linkish small" onClick={remove}>Delete</button>
            <span className="spacer" />
            <button className="btn ghost small" onClick={() => setMode('improve')}>Improve with AI</button>
            <button className="btn ghost small" disabled={starring} onClick={() => onStar(a.id)}>Make a STAR story</button>
          </div>
        </>
      )}
    </article>
  )
}
