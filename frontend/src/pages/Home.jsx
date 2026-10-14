import { Check } from 'lucide-react'
import { Meter, PageHead, VISA_LABEL, daysUntil, fmtDate, plural } from '../ui'
import FollowUps from '../components/FollowUps'
import Milestones from '../components/Milestones'
import Plan from '../components/Plan'
import ThisWeek from '../components/ThisWeek'

function VisaCard({ profile }) {
  const days = daysUntil(profile.visa_end_date)
  const visa = VISA_LABEL[profile.visa_type]
  return (
    <section className="card">
      {days > 0 && <div className="countdown"><span className="num">{days}</span><span>{days === 1 ? 'day' : 'days'} until your {visa} visa ends</span></div>}
      {days === 0 && <div className="countdown"><span>Your {visa} visa ends today</span></div>}
      {days < 0 && <p className="strong">Your visa end date has passed. Update it in your profile if it has changed.</p>}
      <p className="small muted" style={{ marginTop: 6 }}>{fmtDate(profile.visa_end_date, { day: 'numeric', month: 'long', year: 'numeric' })}</p>
    </section>
  )
}

function GettingStarted({ s, go }) {
  const done = s.next_steps.filter((x) => x.done).length
  if (done === s.next_steps.length) return null
  return (
    <section className="card">
      <div className="row"><h2>Getting started</h2><span className="spacer" /><span className="small muted">{done} of {s.next_steps.length} done</span></div>
      <div style={{ margin: '10px 0 16px' }}><Meter value={(done / s.next_steps.length) * 100} /></div>
      <div className="list">
        {s.next_steps.map((t) => (
          <div key={t.id} className={`task ${t.done ? 'done' : ''}`}>
            <span className={`tickbox ${t.done ? 'on' : ''}`} aria-label={t.done ? 'Done' : 'Not done yet'}>{t.done && <Check size={13} strokeWidth={3} />}</span>
            <div><div className="t">{t.text}</div><div className="why">{t.why}</div></div>
            {!t.done && <button className="btn ghost small" onClick={() => go(t.page)}>Open</button>}
          </div>
        ))}
      </div>
    </section>
  )
}

export default function Home({ s, go, refresh, notify }) {
  const finding = s.stats.findings[0]
  const step = s.next_steps.find((x) => !x.done)
  const f = s.stats.funnel
  const fresh = s.jobs.fresh
  // jobs just posted come first, since they go stale; then what the tracker found; then the next getting-started step
  const next = fresh > 0
    ? { text: `${plural(fresh, 'new matching job')} posted in the last 48 hours`, why: 'Roles get most of their applications in the first few days.', label: 'See jobs', page: 'jobs' }
    : finding
      ? { text: finding.action, why: finding.evidence, label: finding.link?.label, page: finding.link?.page }
      : step && { text: step.text, why: step.why, label: 'Open', page: step.page }

  return (
    <>
      <PageHead title={`This week, ${s.profile.first_name}`} lede="What to do next in your search, and why." />
      <Milestones s={s} />

      {next && (
        <section className="card tint next-step">
          <div>
            <p className="kicker">Your next best step</p>
            <h2>{next.text}</h2>
            <p>Why: {next.why}</p>
          </div>
          {next.page && <button className="btn" onClick={() => go(next.page)}>{next.label}</button>}
        </section>
      )}

      <div className="grid split" style={{ marginTop: 16 }}>
        <div className="stack">
          <ThisWeek s={s} refresh={refresh} notify={notify} />
          <Plan s={s} go={go} />
          <FollowUps s={s} refresh={refresh} notify={notify} onOpen={(id) => go('applications', null, { appId: id })} />
          <GettingStarted s={s} go={go} />
        </div>

        <div className="stack">
          <VisaCard profile={s.profile} />
          <section className="card">
            <div className="row"><h2>Your search so far</h2><span className="spacer" /><button className="linkish small" onClick={() => go('applications')}>Applications</button></div>
            <div className="stats4" style={{ marginTop: 12 }}>
              <div><b>{f.applied}</b><span>applied</span></div>
              <div><b>{f.responses}</b><span>replies</span></div>
              <div><b>{f.interviews}</b><span>interviews</span></div>
              <div><b>{f.offers}</b><span>offers</span></div>
            </div>
          </section>
        </div>
      </div>
    </>
  )
}
