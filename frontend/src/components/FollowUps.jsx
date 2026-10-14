import { patch, post } from '../api'
import { attempt, daysUntil, fmtDate } from '../ui'

const due = (iso) => (daysUntil(iso) === 0 ? 'Follow up today.' : `Follow-up due since ${fmtDate(iso, { day: 'numeric', month: 'long' })}.`)

// Applications whose follow-up date has come, and those at Applied with no change for three weeks
export default function FollowUps({ s, refresh, notify, onOpen }) {
  const items = s.follow_ups_due
  if (!items.length) return null
  const safely = attempt(notify)
  const followedUp = (f) => safely(async () => { await post(`/api/applications/${f.id}/followed-up`); await refresh(); notify('Next follow-up in a week') })
  const noReply = (f) => safely(async () => { await patch(`/api/applications/${f.id}`, { stage: 'no_response' }); await refresh(); notify(`${f.company} moved to No reply`) })

  return (
    <section className="card follow-ups">
      <h2>Follow-ups due</h2>
      <p className="sub">A short, polite message a week after applying keeps you in mind. Open one to draft it; nothing is sent for you.</p>
      <div className="list">
        {items.map((f) => (
          <div key={f.id} className="entry">
            <div className="who">
              <div className="strong">{f.role}, {f.company}</div>
              <div className="small muted">
                {f.due && due(f.follow_up_on)}
                {f.quiet_days && ` No change for ${f.quiet_days} days: if you have heard nothing, move it to No reply.`}
              </div>
            </div>
            <div className="acts">
              <button className="btn ghost small" onClick={() => onOpen(f.id)}>Open</button>
              {f.due && <button className="btn ghost small" onClick={() => followedUp(f)}>Mark as followed up</button>}
              {f.quiet_days && <button className="btn ghost small" onClick={() => noReply(f)}>Move to No reply</button>}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
