import { useState } from 'react'
import { BadgeCheck, BellRing, BookOpen, CircleCheck, Clock, ExternalLink, FileText, MessageSquare, Plus, RefreshCw, Target, Trash2, TriangleAlert, Users } from 'lucide-react'
import { del, patch, post } from '../api'
import { Chips, Empty, ErrorRetry, InfoTip, Meter, PageHead, attempt, fmtDate, isoDay, parseDay, pct, plural, today, useAction } from '../ui'
import { ENDED_PHRASE, LESSON_LINK, REJECTED, STAGE_LABEL, isDue } from '../tracker'
import ApplicationPanel from '../components/ApplicationPanel'
import FollowUps from '../components/FollowUps'
import RejectQuestions from '../components/RejectQuestions'

const COLUMNS = [
  { key: 'applied', label: 'Applied', stages: ['applied'] },
  { key: 'no_response', label: 'No reply', stages: ['no_response'] },
  { key: 'screening', label: 'Phone screen', stages: ['screening'] },
  { key: 'interview', label: 'Interview', stages: ['interview'] },
  { key: 'offer', label: 'Offer', stages: ['offer'] },
  { key: 'rejected', label: 'Rejected', stages: ['rejected', 'rejected_after_interview'] },
]
const RESPONDED = new Set(['screening', 'interview', 'rejected_after_interview', 'offer'])
// a rejection after a phone screen was still a reply
const replied = (a) => RESPONDED.has(a.stage) || (a.stage === 'rejected' && a.rejected_at_stage === 'screening')
// A finding's kind, shown as an icon whose name is the label (read out, and shown on hover)
const KIND = {
  cv: ['CV and tailoring', FileText], story: ['Storytelling', MessageSquare], network: ['Network', Users],
  timing: ['Timing', Clock], sponsor: ['Sponsorship', BadgeCheck], lessons: ['Lessons from rejections', BookOpen],
}
function Kind({ type }) {
  if (!KIND[type]) return null
  const [label, Icon] = KIND[type]
  return <span className="kind apps-kind" role="img" aria-label={label} title={label}><Icon size={16} aria-hidden="true" /></span>
}
// The four parts of the AI weekly review, in the order the model writes them
const REVIEW = [['working', 'Working', CircleCheck], ['problem', 'Biggest problem', TriangleAlert], ['one_change', 'One change', RefreshCw], ['signal', 'Success looks like', Target]]
const FAST_DAYS = 2

const monday = (iso) => {
  const d = parseDay(iso)
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  return isoDay(d)
}
const daysBetween = (from, to) => Math.round((parseDay(to) - parseDay(from)) / 86400000)

function WeeklyProgress({ s }) {
  const week = s.habits.this_week
  const goal = week.goal.applications
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
    if (w) { w.applied += 1; w.replies += replied(a) ? 1 : 0 }
  }
  const max = Math.max(goal, ...Object.values(byWeek).map((w) => w.applied))
  const fast = s.applications.filter((a) => monday(a.applied_on) === thisWeek && a.posted_on && daysBetween(a.posted_on, a.applied_on) <= FAST_DAYS).length

  return (
    <section className="card">
      <div className="row"><h2>Weekly progress</h2><span className="spacer" /><span className="small muted">Week of {fmtDate(thisWeek, { day: 'numeric', month: 'long' })}</span></div>
      <div className="grid cols-2" style={{ marginTop: 14, alignItems: 'end' }}>
        <div className="stack" style={{ gap: 14 }}>
          <div>
            <div className="row" style={{ alignItems: 'baseline' }}><span style={{ fontSize: 30, fontWeight: 750, color: 'var(--green)' }}>{week.applications}</span><span className="muted">of {goal} {goal === 1 ? 'application' : 'applications'} with a CV</span></div>
            <div style={{ marginTop: 6 }}><Meter value={(week.applications / goal) * 100} /></div>
          </div>
          <Chips tone="muted" items={[
            week.goal.practice > 0 && `${week.practice} of ${plural(week.goal.practice, 'mock interview')}`,
            week.without_cv > 0 && `${week.without_cv} without a CV, not counted`,
            `${fast} sent within 48 hours of posting`,
          ].filter(Boolean)} />
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
          <div className="legend" style={{ marginTop: 8 }}><span><i style={{ background: 'var(--green-line)' }} />Applied</span><span><i style={{ background: 'var(--green)' }} />Replied</span></div>
        </div>
      </div>
    </section>
  )
}

function Board({ s, refresh, notify, open, reject }) {
  const [over, setOver] = useState(null)
  const fam = Object.fromEntries(s.role_families.map((f) => [f.id, f.name]))
  const cvs = Object.fromEntries(s.cv_versions.map((c) => [c.id, c.name]))
  const safely = attempt(notify)
  // a move to a rejected stage, or between the two, asks where it ended first, so the answer and the
  // stage always agree; nothing changes until that is answered
  const setStage = (a, stage) => (REJECTED.has(stage)
    ? reject(a, stage)
    : safely(async () => { await patch(`/api/applications/${a.id}`, { stage }); await refresh() }))
  const remove = (a) => {
    if (!window.confirm(`Delete the application to ${a.company}? Its history and lesson go with it.`)) return
    safely(async () => { await del(`/api/applications/${a.id}`); await refresh(); notify('Application deleted') })
  }
  const drop = (e, col) => {
    e.preventDefault()
    setOver(null)
    const app = s.applications.find((a) => a.id === e.dataTransfer.getData('text/plain'))
    if (!app || col.stages.includes(app.stage)) return
    if (col.key === 'rejected') reject(app) // the Rejected column holds both stages: the answer decides which
    else setStage(app, col.stages[0])
  }
  const keep = (e) => e.stopPropagation() // a control inside a card does not open the card

  return (
    <div className="board">
      {COLUMNS.map((col) => {
        const cards = s.applications.filter((a) => col.stages.includes(a.stage))
        return (
          <div key={col.key} className={`col ${over === col.key ? 'over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setOver(col.key) }} onDragLeave={() => setOver(null)} onDrop={(e) => drop(e, col)}>
            <div className="col-head">{col.label}<span className="n">{cards.length}</span></div>
            {cards.map((a) => (
              <article key={a.id} className="app-card" draggable onDragStart={(e) => e.dataTransfer.setData('text/plain', a.id)}
                onClick={() => open(a.id)} onKeyDown={(e) => { if (e.key === 'Enter' && e.target === e.currentTarget) open(a.id) }}
                tabIndex={0} aria-label={`${a.role} at ${a.company}: open every detail`}>
                <div className="top">
                  <span className="logo">{a.company[0].toUpperCase()}</span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="role">{a.role}</div>
                    <div className="co">{a.company}</div>
                  </div>
                  <button className="icon-btn" aria-label={`Delete application to ${a.company}`} onClick={(e) => { keep(e); remove(a) }}><Trash2 size={14} /></button>
                </div>
                {(fam[a.role_family_id] || isDue(s, a)) && (
                  <div className="foot">
                    {isDue(s, a) && <span className="chip warn"><BellRing size={12} />Follow up</span>}
                    {fam[a.role_family_id] && <span className="chip">{fam[a.role_family_id]}</span>}
                  </div>
                )}
                <div className="foot">
                  {cvs[a.cv_version_id] ? `${cvs[a.cv_version_id]} CV, via ${a.source}` : <><span className="chip warn">No CV</span><span>via {a.source}</span></>}
                </div>
                {(a.job_url || a.sponsor_licence != null) && (
                  <div className="foot">
                    {a.sponsor_licence != null && <span className={`chip ${a.sponsor_licence ? 'good' : ''}`}>{a.sponsor_licence ? 'On the sponsor register' : 'Not found on the register'}</span>}
                    {a.job_url && <a className="small" href={a.job_url} target="_blank" rel="noopener noreferrer" onClick={keep}>Advert <ExternalLink size={12} aria-hidden="true" style={{ verticalAlign: '-1px' }} /></a>}
                  </div>
                )}
                <div className="foot">
                  <span>{fmtDate(a.applied_on)}</span>
                  <span className="spacer" />
                  <select value={a.stage} onClick={keep} onChange={(e) => setStage(a, e.target.value)} aria-label={`Stage for ${a.company}`}>
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
      {!form.cv_version_id && <p className="small muted" style={{ marginTop: 8 }}>Without a CV it is still logged, but does not count towards your weekly goal.</p>}
      <ErrorRetry error={error} />
    </form>
  )
}

// One chart of reply rates. The grid's caption "Reply rate by" is said in each title for screen readers
function Bars({ title, rows }) {
  const max = Math.max(...rows.map((r) => r.response_rate), 0.01)
  return (
    <section className="card">
      <h3><span className="sr-only">Reply rate by </span>{title}</h3>
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

// The latest lesson from each rejection, newest first
function Learned({ s, go, open }) {
  const rejected = s.applications.filter((a) => REJECTED.has(a.stage))
  if (!rejected.length) return null
  const lessons = rejected.filter((a) => a.lesson).sort((x, y) => (y.lesson.made_on || '').localeCompare(x.lesson.made_on || '')).slice(0, 5)
  return (
    <section className="card section">
      <h2>What you have learned</h2>
      <p className="sub">
        One change from each rejection, newest first.{' '}
        <InfoTip label="When a lesson repeats">When three point to the same thing, it appears under What to fix.</InfoTip>
      </p>
      {lessons.length === 0 && <p className="muted">No lessons yet. Open a rejected card and say where it ended.</p>}
      <div className="list">
        {lessons.map((a) => (
          <div key={a.id} className="finding">
            <div>
              <span className="kind">{a.role}, {a.company}{a.rejected_at_stage && `: ended ${ENDED_PHRASE[a.rejected_at_stage]}`}</span>
              <p className="act">{a.lesson.one_change}</p>
              <p className="ev">{a.lesson.likely_reason} <button className="linkish small" onClick={() => open(a.id)}>Open</button></p>
            </div>
            <button className="btn ghost small" onClick={() => go(a.lesson.page)}>{LESSON_LINK[a.lesson.page]}</button>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function Applications({ s, refresh, go, focus, notify }) {
  const [adding, setAdding] = useState(false)
  const [openId, setOpenId] = useState(focus.appId || null)
  const [rejecting, setRejecting] = useState(null) // {app, from}: the questions asked before a card becomes Rejected
  const st = s.stats
  const review = useAction(() => post('/api/ai/diagnosis'))
  const r = review.result
  const empty = s.applications.length === 0
  const opened = s.applications.find((a) => a.id === openId)
  const reject = (a, target = null) => setRejecting({ app: a, from: a.stage, target })

  return (
    <>
      {/* with no cards yet there is nothing to drag, so the empty page has no lede */}
      <PageHead title="Applications" lede={empty ? null : 'Drag a card when you hear back; click it for every detail.'}>
        {!empty && <button className="btn" onClick={() => setAdding(true)}><Plus size={16} />Add application</button>}
      </PageHead>
      {adding && <AddApplication s={s} refresh={refresh} notify={notify} close={() => setAdding(false)} />}

      {empty ? (
        !adding && (
          <>
            <Empty title="Log your first application" body="With a few logged, you will see which roles, CVs and sources get replies." action="Add application" onAction={() => setAdding(true)} />
            <p className="small muted" style={{ textAlign: 'center', marginTop: 10 }}>Or <button className="linkish small" onClick={() => go('jobs')}>see matching jobs</button></p>
          </>
        )
      ) : (
        <>
          <WeeklyProgress s={s} />
          {s.follow_ups_due.length > 0 && <div className="section"><FollowUps s={s} refresh={refresh} notify={notify} onOpen={setOpenId} /></div>}
          <div className="section"><Board s={s} refresh={refresh} notify={notify} open={setOpenId} reject={reject} /></div>

          <section className="card section">
            <div className="row" style={{ marginBottom: 14 }}>
              <div className="row" style={{ gap: 6 }}>
                <h2>What to fix</h2>
                <InfoTip label="About What to fix">Patterns in your applications, each pointing to the part of the app that fixes it.</InfoTip>
              </div>
              <span className="spacer" />
              <button className="btn ghost" disabled={review.loading} onClick={() => review.run()}>{review.loading ? 'Reviewing your week' : 'Weekly review with AI'}</button>
            </div>
            <ErrorRetry error={review.error} onRetry={review.retry} />
            {r && (
              <div className="card tint" style={{ marginBottom: 14 }}>
                <h3>{r.headline}</h3>
                <div className="grid cols-2" style={{ marginTop: 10, gap: 10 }}>
                  {REVIEW.map(([key, label, Icon]) => (
                    <p key={key} className="small apps-review-part"><Icon size={14} aria-hidden="true" /><span><span className="strong">{label}: </span>{r[key]}</span></p>
                  ))}
                </div>
              </div>
            )}
            {st.findings.length === 0 && <p className="muted">Nothing to fix yet. Findings appear once there is a pattern.</p>}
            <div className="list">
              {st.findings.map((f) => (
                <div key={f.id} className="finding">
                  <div>
                    <div className="apps-finding-head"><Kind type={f.type} /><h3>{f.title}</h3></div>
                    <p className="ev">{f.evidence}</p>
                    <p className="act">{f.action}</p>
                  </div>
                  {f.link && <button className="btn ghost small" onClick={() => go(f.link.page, f.link.tab)}>{f.link.label}</button>}
                </div>
              ))}
            </div>
          </section>

          <Learned s={s} go={go} open={setOpenId} />

          <div className="section-head section"><h2>Insights</h2></div>
          <div className="stats4">
            <div><b>{st.funnel.applied}</b><span>applied</span></div>
            <div><b>{pct(st.funnel.response_rate)}</b><span>reply rate</span></div>
            <div><b>{st.funnel.interviews}</b><span>interviews</span></div>
            <div><b>{st.funnel.offers}</b><span>offers</span></div>
          </div>
          <p className="small muted apps-caption" aria-hidden="true">Reply rate by</p>
          <div className="grid cols-2">
            <Bars title="Role family" rows={st.by_family} />
            <Bars title="CV version" rows={st.by_cv} />
            <Bars title="Source" rows={st.by_source} />
            {st.timing.timed > 0 && <Bars title={`Speed (you average ${st.timing.avg_days} days after posting)`} rows={[st.timing.fast, st.timing.slow]} />}
          </div>
        </>
      )}

      {opened && !rejecting && <ApplicationPanel key={opened.id} app={opened} s={s} refresh={refresh} go={go} notify={notify} close={() => setOpenId(null)} onReject={reject} />}
      {rejecting && <RejectQuestions app={rejecting.app} from={rejecting.from} target={rejecting.target} refresh={refresh} go={go} close={() => setRejecting(null)} />}
    </>
  )
}
