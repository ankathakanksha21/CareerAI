import { useState } from 'react'
import { put } from '../api'
import { ErrorRetry, Meter, fmtDate, plural } from '../ui'

function Goal({ have, want, label }) {
  return (
    <div>
      <div className="row" style={{ alignItems: 'baseline', gap: 6 }}><span className="goal-num">{have}</span><span className="muted">of {want} {label}</span></div>
      <div style={{ marginTop: 6 }}><Meter value={(have / want) * 100} /></div>
    </div>
  )
}

function GoalsForm({ goal, refresh, notify, close }) {
  const [form, setForm] = useState({ applications: goal.applications, practice: goal.practice })
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault()
    try {
      const saved = await put('/api/profile/goals', { applications: Number(form.applications), practice: Number(form.practice) })
      await refresh()
      notify(`Goals saved. They apply from ${fmtDate(saved.starts_on, { weekday: 'long', day: 'numeric', month: 'long' })}.`)
      close()
    } catch (err) {
      setError(err)
    }
  }
  return (
    <form className="stack" onSubmit={submit} style={{ marginTop: 14 }}>
      <div className="form-row">
        <label className="field">Applications with a CV a week<input type="number" min={1} max={30} value={form.applications} onChange={set('applications')} style={{ width: 90 }} /></label>
        <label className="field">Mock interviews a week<input type="number" min={0} max={14} value={form.practice} onChange={set('practice')} style={{ width: 90 }} /></label>
        <button className="btn" type="submit">Save goals</button>
        <button className="btn ghost" type="button" onClick={close}>Cancel</button>
      </div>
      <p className="small muted">The first goals you set apply this week. After that, a change applies from the next Monday, so a week is always judged by the goal it started with.</p>
      <ErrorRetry error={error} />
    </form>
  )
}

// This week against the user's own goals, and the streak of weeks in which they met them
export default function ThisWeek({ s, refresh, notify }) {
  const [editing, setEditing] = useState(false)
  const h = s.habits
  const w = h.this_week
  return (
    <section className="card">
      <div className="row"><h2>This week</h2><span className="spacer" />{!editing && <button className="linkish small" onClick={() => setEditing(true)}>Edit goals</button>}</div>
      <div className="grid cols-2" style={{ marginTop: 12 }}>
        <Goal have={w.applications} want={w.goal.applications} label={w.goal.applications === 1 ? 'application with a CV' : 'applications with a CV'} />
        {w.goal.practice > 0 && <Goal have={w.practice} want={w.goal.practice} label={w.goal.practice === 1 ? 'mock interview' : 'mock interviews'} />}
      </div>
      {w.without_cv > 0 && <p className="small muted" style={{ marginTop: 8 }}>{plural(w.without_cv, 'more application')} without a CV recorded {w.without_cv === 1 ? 'does' : 'do'} not count. Open {w.without_cv === 1 ? 'it' : 'them'} in Applications to add the CV you sent.</p>}
      <div className="stats4 streak" style={{ marginTop: 14 }}>
        <div><b>{h.streak}</b><span>{h.streak === 1 ? 'week' : 'weeks'} in a row at your goal</span></div>
        <div><b>{h.best_streak}</b><span>best streak</span></div>
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>
        {w.met ? 'Goal met this week. ' : 'A week counts once both goals are met; a quiet day never breaks the streak. '}
        {w.next_goal && `From Monday: ${plural(w.next_goal.applications, 'application')} and ${plural(w.next_goal.practice, 'mock interview')} a week.`}
      </p>
      {editing && <GoalsForm goal={w.next_goal || w.goal} refresh={refresh} notify={notify} close={() => setEditing(false)} />}
    </section>
  )
}
