import { dayBox, eventWhen } from '../networking'

// The next saved events the user is interested in or going to. One today stays until midnight
export default function ComingUp({ s, go }) {
  if (!s.coming_up.length) return null
  return (
    <section className="card">
      <div className="row"><h2>Coming up</h2><span className="spacer" /><button className="linkish small" onClick={() => go('networking', 'events')}>Events</button></div>
      <div className="list" style={{ marginTop: 12 }}>
        {s.coming_up.map((ev) => {
          const box = dayBox(ev.on_day)
          return (
            <div key={ev.id} className="meet">
              <div className="datebox" style={{ width: 52 }}><b>{box.day}</b><span>{box.month}</span></div>
              <div>
                <div className="strong">{ev.name}</div>
                <div className="small muted">{eventWhen(ev.starts_at)}{ev.online ? ', online' : ev.place ? `, ${ev.place}` : ''}</div>
                <button className="linkish small" onClick={() => go('networking', 'events')}>{ev.prep ? 'Read your preparation' : 'Prepare'}</button>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
