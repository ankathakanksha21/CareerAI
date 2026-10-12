import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { del, patch, post } from '../api'
import { Empty, ErrorRetry, Meter, PageHead, fmtDate, isoDay, parseDay, pct, today, useAction } from '../ui'

const STAGE_LABEL = { applied: 'Applied', no_response: 'No reply', rejected: 'Rejected at CV', screening: 'Phone screen', interview: 'Interview', rejected_after_interview: 'Rejected after interview', offer: 'Offer' }
const COLUMNS = [
  { key: 'applied', label: 'Applied', stages: ['applied'] },
  { key: 'no_response', label: 'No reply', stages: ['no_response'] },
  { key: 'screening', label: 'Phone screen', stages: ['screening'] },
  { key: 'interview', label: 'Interview', stages: ['interview'] },
  { key: 'offer', label: 'Offer', stages: ['offer'] },
  { key: 'rejected', label: 'Rejected', stages: ['rejected', 'rejected_after_interview'] },
]
const RESPONDED = new Set(['screening', 'interview', 'rejected_after_interview', 'offer'])
const KIND = { cv: 'CV and tailoring', story: 'Storytelling', network: 'Network', timing: 'Timing' }
const WEEKLY_GOAL = 5
const FAST_DAYS = 2

const monday = (iso) => {
  const d = parseDay(iso)
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  return isoDay(d)
}
const daysBetween = (from, to) => Math.round((parseDay(to) - parseDay(from)) / 86400000)

function WeeklyProgress({ s }) {
  const thisWeek = monday(isoDay(today()))
  const weeks = []
  for (let i = 6; i >= 0; i--) {
    const d = parseDay(thisWeek)
    d.setDate(d.getDate() - 7 * i)
    weeks.push(isoDay(d))
  }
  const byWeek = Object.fromEntries(weeks.map((w) => [w, { applied: 0, replies: 0 }]))
  for (const a of s.applications) {
    const w = byWeek[monday(a.applied_on)]
    if (w) { w.applied += 1; w.replies += RESPONDED.has(a.stage) ? 1 : 0 }
  }
  const max = Math.max(WEEKLY_GOAL, ...Object.values(byWeek).map((w) => w.applied))
  const now = byWeek[thisWeek]
  const fast = s.applications.filter((a) => monday(a.applied_on) === thisWeek && a.posted_on && daysBetween(a.posted_on, a.applied_on) <= FAST_DAYS).length

  return (
    <section className="card">
      <div className="row"><h2>Weekly progress</h2><span className="spacer" /><span className="small muted">Week of {fmtDate(thisWeek, { day: 'numeric', month: 'long' })}</span></div>
      <div className="grid cols-2" style={{ marginTop: 14, alignItems: 'end' }}>
        <div className="stack" style={{ gap: 14 }}>
          <div>
            <div className="row" style={{ alignItems: 'baseline' }}><span style={{ fontSize: 30, fontWeight: 750, color: 'var(--green)' }}>{now.applied}</span><span className="muted">of {WEEKLY_GOAL} applications this week</span></div>
            <div style={{ marginTop: 6 }}><Meter value={(now.applied / WEEKLY_GOAL) * 100} /></div>
          </div>
          <p className="small muted">{fast} sent within 48 hours of the job being posted.</p>
        </div>
        <div>
          <div className="week-bars" aria-label="Applications per week">
            {weeks.map((w) => {
              const v = byWeek[w]
              return (
                <div key={w} className={`wb ${w === thisWeek ? 'current' : ''}`} title={`${v.applied} applied, ${v.replies} replied`}>
                  <span>{v.applied}</span>
                  <span className="bar" style={{ height: `${(v.applied / max) * 90}px` }}>
                    <span className="resp" style={{ height: `${(v.replies / max) * 90}px` }} />
                  </span>
                  <span>{fmtDate(w)}</span>
                </div>
              )
            })}
          </div>
          <div className="legend" style={{ marginTop: 8 }}><span><i style={{ background: 'var(--green-line)' }} />Applied</span><span><i style={{ background: 'var(--green)' }} />Got a reply</span></div>
        </div>
      </div>
    </section>
  )
}

function Board({ s, refresh, notify }) {
  const [over, setOver] = useState(null)
  const fam = Object.fromEntries(s.role_families.map((f) => [f.id, f.name]))
  const cvs = Object.fromEntries(s.cv_versions.map((c) => [c.id, c.name]))
  const setStage = async (id, stage) => { await patch(`/api/applications/${id}`, { stage }); refresh() }
  const remove = async (a) => {
    if (!window.confirm(`Delete the application to ${a.company}?`)) return
    await del(`/api/applications/${a.id}`)
    await refresh()
    notify('Application deleted')
  }
  const drop = (e, col) => {
    e.preventDefault()
    setOver(null)
    const id = e.dataTransfer.getData('text/plain')
    const app = s.applications.find((a) => a.id === id)
    if (app && !col.stages.includes(app.stage)) setStage(id, col.stages[0])
  }

  return (
    <div className="board">
      {COLUMNS.map((col) => {
        const cards = s.applications.filter((a) => col.stages.includes(a.stage))
        return (
          <div key={col.key} className={`col ${over === col.key ? 'over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setOver(col.key) }} onDragLeave={() => setOver(null)} onDrop={(e) => drop(e, col)}>
            <div className="col-head">{col.label}<span className="n">{cards.length}</span></div>
            {cards.map((a) => (
              <article key={a.id} className="app-card" draggable onDragStart={(e) => e.dataTransfer.setData('text/plain', a.id)}>
                <div className="top">
                  <span className="logo">{a.company[0].toUpperCase()}</span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="role">{a.role}</div>
                    <div className="co">{a.company}</div>
                  </div>
                  <button className="icon-btn" aria-label={`Delete application to ${a.company}`} onClick={() => remove(a)}><Trash2 size={14} /></button>
                </div>
                {fam[a.role_family_id] && <div className="foot"><span className="chip">{fam[a.role_family_id]}</span></div>}
                <div className="foot">{cvs[a.cv_version_id] ? `${cvs[a.cv_version_id]} CV, ` : ''}via {a.source}</div>
                <div className="foot">
                  <span>{fmtDate(a.applied_on)}</span>
                  <span className="spacer" />
                  <select value={a.stage} onChange={(e) => setStage(a.id, e.target.value)} aria-label={`Stage for ${a.company}`}>
                    {s.options.stages.map((k) => <option key={k} value={k}>{STAGE_LABEL[k]}</option>)}
                  </select>
                </div>
              </article>
            ))}
          </div>
        )
      })}
    </div>
  )
}

function AddApplication({ s, refresh, notify, close }) {
  const [form, setForm] = useState({ company: '', role: '', role_family_id: '', cv_version_id: '', source: 'Company site', applied_on: isoDay(today()), posted_on: '' })
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault()
    if (!form.company.trim() || !form.role.trim()) return setError(new Error('Enter the company and the role.'))
    try {
      await post('/api/applications', { ...form, role_family_id: form.role_family_id || null, cv_version_id: form.cv_version_id || null, posted_on: form.posted_on || null })
      await refresh()
      notify(`Added ${form.role} at ${form.company}`)
      close()
    } catch (err) {
      setError(err)
    }
  }
  return (
    <form className="card" onSubmit={submit} style={{ marginBottom: 16 }} noValidate>
      <div className="form-row">
        <label className="field">Company<input type="text" value={form.company} onChange={set('company')} style={{ width: 160 }} autoFocus /></label>
        <label className="field">Role<input type="text" value={form.role} onChange={set('role')} style={{ width: 160 }} /></label>
        <label className="field">Role family<select value={form.role_family_id} onChange={set('role_family_id')}><option value="">None</option>{s.role_families.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select></label>
        <label className="field">CV version<select value={form.cv_version_id} onChange={set('cv_version_id')}><option value="">None</option>{s.cv_versions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label className="field">Where you applied<select value={form.source} onChange={set('source')}>{s.options.sources.map((x) => <option key={x}>{x}</option>)}</select></label>
        <label className="field">Date applied<input type="date" value={form.applied_on} onChange={set('applied_on')} /></label>
        <label className="field">Date posted <span className="muted" style={{ fontWeight: 400 }}>(optional)</span><input type="date" value={form.posted_on} onChange={set('posted_on')} /></label>
        <button className="btn" type="submit">Add</button>
        <button className="btn ghost" type="button" onClick={close}>Cancel</button>
      </div>
      <ErrorRetry error={error} />
    </form>
  )
}

function Bars({ title, rows }) {
  const max = Math.max(...rows.map((r) => r.response_rate), 0.01)
  return (
    <section className="card">
      <h3>{title}</h3>
      <div style={{ marginTop: 10 }}>
        {rows.map((r) => (
          <div key={r.key ?? r.label} className="hbar">
            <span title={r.label} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</span>
            <span className="track"><span className={r.responses === 0 ? 'zero' : ''} style={{ width: `${(r.response_rate / max) * 100}%` }} /></span>
            <span><b>{pct(r.response_rate)}</b> <span className="muted">{r.responses}/{r.applied}</span></span>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function Applications({ s, refresh, go, notify }) {
  const [adding, setAdding] = useState(false)
  const st = s.stats
  const review = useAction(() => post('/api/ai/diagnosis'))
  const r = review.result
  const empty = s.applications.length === 0

  return (
    <>
      <PageHead title="Applications" lede="Every application with its role family, CV version, source and stage. Drag a card when you hear back; the tracker uses this to tell you what to fix.">
        {!empty && <button className="btn" onClick={() => setAdding(true)}><Plus size={16} />Add application</button>}
      </PageHead>
      {adding && <AddApplication s={s} refresh={refresh} notify={notify} close={() => setAdding(false)} />}

      {empty ? (
        !adding && <Empty title="Log your first application" body="Add each application as you send it. Once there are a few, the tracker shows which roles, CVs and sources get replies." action="Add application" onAction={() => setAdding(true)} />
      ) : (
        <>
          <WeeklyProgress s={s} />
          <div className="section"><Board s={s} refresh={refresh} notify={notify} /></div>

          <section className="card section">
            <div className="row">
              <h2>What to fix</h2>
              <span className="spacer" />
              <button className="btn ghost" disabled={review.loading} onClick={() => review.run()}>{review.loading ? 'Reviewing your week' : 'Weekly review with AI'}</button>
            </div>
            <p className="sub">Patterns in your applications, each pointing to the part of the app that fixes it.</p>
            <ErrorRetry error={review.error} onRetry={review.retry} />
            {r && (
              <div className="card tint" style={{ marginBottom: 14 }}>
                <h3>{r.headline}</h3>
                <div className="grid cols-2" style={{ marginTop: 10, gap: 10 }}>
                  <p className="small"><span className="strong">Working: </span>{r.working}</p>
                  <p className="small"><span className="strong">Biggest problem: </span>{r.problem}</p>
                  <p className="small"><span className="strong">One change for the next batch: </span>{r.one_change}</p>
                  <p className="small"><span className="strong">How you will know it worked: </span>{r.signal}</p>
                </div>
              </div>
            )}
            {st.findings.length === 0 && <p className="muted">Nothing to fix yet. Findings appear once there are enough applications to see a pattern.</p>}
            <div className="list">
              {st.findings.map((f) => (
                <div key={f.id} className="finding">
                  <div>
                    <span className="kind">{KIND[f.type]}</span>
                    <h3>{f.title}</h3>
                    <p className="ev">{f.evidence}</p>
                    <p className="act">{f.action}</p>
                  </div>
                  {f.link && <button className="btn ghost small" onClick={() => go(f.link.page)}>{f.link.label}</button>}
                </div>
              ))}
            </div>
          </section>

          <div className="section-head section"><h2>Insights</h2><p>{st.funnel.applied} applications, {pct(st.funnel.response_rate)} reply rate, {st.funnel.interviews} interviews, {st.funnel.offers} offers.</p></div>
          <div className="grid cols-2">
            <Bars title="Reply rate by role family" rows={st.by_family} />
            <Bars title="Reply rate by CV version" rows={st.by_cv} />
            <Bars title="Reply rate by source" rows={st.by_source} />
            {st.timing.timed > 0 && <Bars title={`Speed: you apply ${st.timing.avg_days} days after posting on average`} rows={[st.timing.fast, st.timing.slow]} />}
          </div>
        </>
      )}
    </>
  )
}
