import { Check } from 'lucide-react'

// Home: the buddy group at a glance, a tick for everyone who has met all their targets this week, and nudges received
export default function PeerCard({ s, go }) {
  const p = s.peers
  if (p.status === 'proposed') {
    return (
      <section className="card tint">
        <h2>We found a buddy for you</h2>
        <p className="small">Say yes or not this time on Peers.</p>
        <button className="btn small" style={{ marginTop: 10 }} onClick={() => go('peers')}>Open</button>
      </section>
    )
  }
  if (p.status !== 'group') return null
  const people = [{ key: 'me', name: 'You', met: p.group.me.progress.met === p.group.me.progress.of },
    ...p.group.members.map((m) => ({ key: m.member, name: m.first_name, met: m.progress.met === m.progress.of }))]
  return (
    <section className="card">
      <div className="row"><h2>Your buddy group</h2><span className="spacer" /><button className="linkish small" onClick={() => go('peers')}>Peers</button></div>
      <div className="list" style={{ marginTop: 10 }}>
        {people.map((x) => (
          <div key={x.key} className="buddy">
            <span className={`state ${x.met ? 'met' : ''}`} aria-label={x.met ? 'All targets met this week' : 'Not all targets met yet'}>{x.met && <Check size={12} strokeWidth={3} />}</span>
            <span>{x.name}</span>
          </div>
        ))}
      </div>
      {p.nudges.map((n) => <p key={n.first_name} className="small" style={{ marginTop: 8 }}>{n.text}</p>)}
    </section>
  )
}
