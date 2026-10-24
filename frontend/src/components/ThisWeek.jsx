import { useState } from 'react'
import { Check } from 'lucide-react'
import { put } from '../api'
import { ErrorRetry, InfoTip, Meter, fmtDate, plural } from '../ui'

function Goal({ have, want, label }) {
  return (
    <div>
      <div className="row" style={{ alignItems: 'baseline', gap: 6 }}><span className="goal-num">{have}</span><span className="muted">of {want} {label}</span></div>
      <div style={{ marginTop: 6 }}><Meter value={(have / want) * 100} /></div>
    </div>
  )
}

function GoalsForm({ goal, refresh, notify, close }) {
  const [form, setForm] = useState({ applications: goal.applications, practice: goal.practice, outreach: goal.outreach })
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault()
    try {
      const saved = await put('/api/profile/goals', { applications: Number(form.applications), practice: Number(form.practice), outreach: Number(form.outreach) })
      await refresh()
      notify(`Goals saved. They apply from ${fmtDate(saved.starts_on, { weekday: 'long', day: 'numeric', month: 'long' })}.`)
      close()
    } catch (err) {
      setError(err)
    }
  }
  return (
    <form className="stack" onSubmit={submit} style={{ marginTop: 14 }}>
      {/* the legend says "a week" once, and screen readers hear it with every field */}
      <fieldset className="thisweek-goals">
        <legend>Per week</legend>
        <div className="form-row">
          <label className="field">Applications with a CV<input type="number" min={1} max={30} value={form.applications} onChange={set('applications')} style={{ width: 90 }} /></label>
          <label className="field">Mock interviews<input type="number" min={0} max={14} value={form.practice} onChange={set('practice')} style={{ width: 90 }} /></label>
          <label className="field">Messages to people<input type="number" min={0} max={20} value={form.outreach} onChange={set('outreach')} style={{ width: 90 }} /></label>
          <button className="btn" type="submit">Save goals</button>
          <button className="btn ghost" type="button" onClick={close}>Cancel</button>
        </div>
      </fieldset>
      <p className="small muted">
        Changes apply from next Monday (your first goals apply this week).{' '}
        <InfoTip label="More about goals">A week is always judged by the goals it started with. A message counts once you mark it as sent in Networking. 0 turns a target off.</InfoTip>
      </p>
      <ErrorRetry error={error} />
    </form>
  )
}

const nextGoalLine = (g) => `Goals from Monday: ${plural(g.applications, 'application')}, ${plural(g.practice, 'mock interview')}, ${plural(g.outreach, 'message')}.`

// This week against the user's own goals, and the streak of weeks in which they met them
export default function ThisWeek({ s, refresh, notify }) {
  const [editing, setEditing] = useState(false)
  const h = s.habits
  const w = h.this_week
  const invite = !w.outreach_chosen && w.goal.outreach === 0 && !w.next_goal?.outreach
  return (
    <section className="card">
      <div className="row">
        <h2>This week</h2>
        {w.met && <span className="chip good"><Check size={12} strokeWidth={3} aria-hidden="true" />Goal met<span className="sr-only"> this week</span></span>}
        <span className="spacer" />
        {!editing && <button className="linkish small" onClick={() => setEditing(true)}>Edit goals</button>}
      </div>
      <div className="grid cols-3 goals" style={{ marginTop: 12 }}>
        <Goal have={w.applications} want={w.goal.applications} label={w.goal.applications === 1 ? 'application with a CV' : 'applications with a CV'} />
        {w.goal.practice > 0 && <Goal have={w.practice} want={w.goal.practice} label={w.goal.practice === 1 ? 'mock interview' : 'mock interviews'} />}
        {w.goal.outreach > 0 && <Goal have={w.outreach} want={w.goal.outreach} label={w.goal.outreach === 1 ? 'message to a contact' : 'messages to contacts'} />}
      </div>
      {w.without_cv > 0 && <p className="small muted" style={{ marginTop: 8 }}>{plural(w.without_cv, 'more application')} without a CV {w.without_cv === 1 ? 'does' : 'do'} not count. In Applications, add the CV you sent.</p>}
      {invite && !editing && (
        <p className="small invite" style={{ marginTop: 10 }}>
          Add a weekly goal for messages to people in your field? <button className="linkish small" onClick={() => setEditing(true)}>Set a target</button>
        </p>
      )}
      <div className="stats4 streak thisweek-streak" style={{ marginTop: 14 }}>
        <div>
          <b>{h.streak}</b><span>week streak</span>{' '}
          <InfoTip label="How the streak works">A week counts once every goal is met. A quiet day never breaks the streak.</InfoTip>
        </div>
        <div><b>{h.best_streak}</b><span>best streak</span></div>
      </div>
      {w.next_goal && <p className="small muted" style={{ marginTop: 8 }}>{nextGoalLine(w.next_goal)}</p>}
      {editing && <GoalsForm goal={w.next_goal || w.goal} refresh={refresh} notify={notify} close={() => setEditing(false)} />}
    </section>
  )
}
