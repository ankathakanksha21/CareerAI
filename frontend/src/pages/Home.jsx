import { Check } from 'lucide-react'
import { InfoTip, Meter, PageHead, ShowMore, VISA_LABEL, daysUntil, fmtDate, plural } from '../ui'
import FollowUps from '../components/FollowUps'
import Milestones from '../components/Milestones'
import Plan from '../components/Plan'
import ThisWeek from '../components/ThisWeek'
import ComingUp from '../components/ComingUp'
import PeerCard from '../components/PeerCard'

function VisaCard({ profile }) {
  const days = daysUntil(profile.visa_end_date)
  const visa = VISA_LABEL[profile.visa_type]
  return (
    <section className="card">
      {days > 0 && <div className="countdown"><span className="num">{days}</span><span>{days === 1 ? 'day' : 'days'} left on your {visa} visa</span></div>}
      {days === 0 && <div className="countdown"><span>Your {visa} visa ends today</span></div>}
      {days < 0 && <p className="strong">Your visa end date has passed. If it changed, update your profile.</p>}
      <p className="small muted" style={{ marginTop: 6 }}>{fmtDate(profile.visa_end_date, { day: 'numeric', month: 'long', year: 'numeric' })}</p>
    </section>
  )
}

// Each step's reason is behind its (i). The next step to take shows its reason, unless the Next step card
// above is already showing that step and its reason (stepInNext)
function GettingStarted({ s, go, stepInNext }) {
  const done = s.next_steps.filter((x) => x.done).length
  if (done === s.next_steps.length) return null
  const first = s.next_steps.find((x) => !x.done)
  return (
    <section className="card">
      <div className="row"><h2>Getting started</h2><span className="spacer" /><span className="small muted"><span aria-hidden="true">{done}/{s.next_steps.length}</span><span className="sr-only">{done} of {s.next_steps.length} done</span></span></div>
      <div style={{ margin: '10px 0 16px' }}><Meter value={(done / s.next_steps.length) * 100} /></div>
      <div className="list">
        {s.next_steps.map((t) => {
          const shown = t === first && !stepInNext
          return (
            <div key={t.id} className={`task ${t.done ? 'done' : ''}`}>
              <span className={`tickbox ${t.done ? 'on' : ''}`} aria-label={t.done ? 'Done' : 'Not done yet'}>{t.done && <Check size={13} strokeWidth={3} />}</span>
              <div>
                <div className="t">{t.text}{!shown && <> <InfoTip label={`Why: ${t.text}`}>{t.why}</InfoTip></>}</div>
                {shown && <div className="why">{t.why}</div>}
              </div>
              {!t.done && <button className="btn ghost small" onClick={() => go(t.page)}>Open</button>}
            </div>
          )
        })}
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
  // the wording matches the plan's own new-jobs task (backend habits.py), so the two never drift
  const next = fresh > 0
    ? { text: `${plural(fresh, 'new matching job')} from the last 48 hours`, why: 'Most applications arrive in the first few days.', label: 'See jobs', page: 'jobs' }
    : finding
      ? { text: finding.action, why: finding.evidence, label: finding.link?.label, page: finding.link?.page, tab: finding.link?.tab }
      : step && { text: step.text, why: step.why, label: 'Open', page: step.page }
  const stepInNext = !(fresh > 0) && !finding
  // the plan does not draw a second time what is already on this page: the task the Next step card shows,
  // and the follow-ups task while the Follow-ups due card lists them
  const shownElsewhere = new Set([fresh > 0 ? 'new-jobs' : finding && `finding-${finding.id}`, s.follow_ups_due.length > 0 && 'follow-ups'].filter(Boolean))
  // findings that are neither the next best step nor a task on the plan, such as one with no page to fix it on
  const planned = new Set(s.plan.map((t) => t.id))
  const others = (fresh > 0 ? s.stats.findings : s.stats.findings.slice(1)).filter((x) => !planned.has(`finding-${x.id}`))

  return (
    <>
      <PageHead title={`This week, ${s.profile.first_name}`} />
      <Milestones s={s} />

      {next && (
        <section className="card tint next-step">
          <div>
            <p className="kicker">Next step</p>
            <h2>{next.text}</h2>
            <p>{next.why}</p>
          </div>
          {next.page && <button className="btn" onClick={() => go(next.page, next.tab)}>{next.label}</button>}
        </section>
      )}

      <div className="grid split" style={{ marginTop: 16 }}>
        <div className="stack">
          <ThisWeek s={s} refresh={refresh} notify={notify} />
          <Plan s={s} go={go} skip={shownElsewhere} />
          <FollowUps s={s} refresh={refresh} notify={notify} onOpen={(id) => go('applications', null, { appId: id })} />
          <GettingStarted s={s} go={go} stepInNext={stepInNext} />
          {others.length > 0 && (
            <section className="card">
              <div className="row"><h2>Also worth fixing</h2><span className="spacer" /><button className="linkish small" onClick={() => go('applications')}>Applications</button></div>
              <div className="list" style={{ marginTop: 12 }}>
                {others.map((x) => (
                  <ShowMore key={x.id} label={x.title} buttonClassName="linkish home-finding-btn">
                    <p className="small muted">{x.evidence}</p>
                  </ShowMore>
                ))}
              </div>
            </section>
          )}
        </div>

        <div className="stack">
          <PeerCard s={s} go={go} />
          <ComingUp s={s} go={go} />
          <VisaCard profile={s.profile} />
          <section className="card">
            <div className="row"><h2>Your search</h2><span className="spacer" /><button className="linkish small" onClick={() => go('applications')}>Applications</button></div>
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
