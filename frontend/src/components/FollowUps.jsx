import { BellRing, Check } from 'lucide-react'
import { patch, post } from '../api'
import { InfoTip, attempt, daysUntil, fmtDate } from '../ui'

const due = (iso) => (daysUntil(iso) === 0 ? 'Due today' : `Due since ${fmtDate(iso, { day: 'numeric', month: 'long' })}`)

// Applications whose follow-up date has come, and those at Applied with no change for three weeks
export default function FollowUps({ s, refresh, notify, onOpen }) {
  const items = s.follow_ups_due
  if (!items.length) return null
  const safely = attempt(notify)
  const followedUp = (f) => safely(async () => { await post(`/api/applications/${f.id}/followed-up`); await refresh(); notify('Next follow-up in a week') })
  const noReply = (f) => safely(async () => { await patch(`/api/applications/${f.id}`, { stage: 'no_response' }); await refresh(); notify(`${f.company} moved to No reply`) })

  return (
    <section className="card follow-ups">
      <div className="row" style={{ gap: 6 }}>
        <h2>Follow-ups due</h2>
        <InfoTip label="Why follow up">A short, polite message a week after applying keeps you in mind.</InfoTip>
      </div>
      <p className="sub">Open one to draft a message. Nothing is sent for you.</p>
      <div className="list">
        {items.map((f) => (
          <div key={f.id} className="entry">
            <div className="who">
              <div className="strong">{f.role}, {f.company}</div>
              <div className="row small muted" style={{ gap: 6, marginTop: 2 }}>
                {f.due && <span className="chip warn"><BellRing size={12} aria-hidden="true" />{due(f.follow_up_on)}</span>}
                {f.quiet_days && <span>No change for {f.quiet_days} days. Heard nothing?</span>}
              </div>
            </div>
            <div className="acts">
              <button className="btn ghost small" onClick={() => onOpen(f.id)}>Open</button>
              {f.due && <button className="btn ghost small" title="Mark as followed up" onClick={() => followedUp(f)}><Check size={14} aria-hidden="true" />I followed up</button>}
              {f.quiet_days && <button className="btn ghost small" onClick={() => noReply(f)}>Move to No reply</button>}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
