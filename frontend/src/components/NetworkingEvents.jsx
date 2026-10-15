import { useState } from 'react'
import { ExternalLink, Trash2 } from 'lucide-react'
import { del, patch, post, put } from '../api'
import { Empty, ErrorRetry, attempt, useAction } from '../ui'
import { dayBox, eventWhen, label, londonInput } from '../networking'
import PersonForm from './PersonForm'

function LinkList({ title, items }) {
  if (!items.length) return null
  return (
    <div>
      <h3>{title}</h3>
      <div className="list" style={{ marginTop: 6 }}>
        {items.map((l) => <div key={l.url}><a href={l.url} target="_blank" rel="noopener noreferrer">{l.label || l.name} <ExternalLink size={13} /></a>
          {l.about && <p className="small muted">{l.about}</p>}</div>)}
      </div>
    </div>
  )
}

// Where to look: Meetup and Eventbrite searches for the user's field and city, their university's events page, professional bodies
function WhereToLook({ s, links, error, retry, refresh, notify }) {
  const [page, setPage] = useState(s.profile.university_events_url || '')
  const save = useAction(async () => {
    const r = await put('/api/profile/events-url', { url: page })
    setPage(r.university_events_url || '')
    await refresh()
    notify(r.university_events_url ? 'Saved' : 'Removed')
    return r
  })
  return (
    <section className="card">
      <h2>Where to look</h2>
      <p className="sub">Searches built from your target roles and locations. Each opens on the other site; nothing is listed here for you.</p>
      <ErrorRetry error={error} onRetry={retry} />
      {links && (
        <div className="stack" style={{ marginTop: 10 }}>
          {links.meetup.length + links.eventbrite.length === 0 && (
            <p className="small">Pick target roles in Career pathways and add your locations in your profile to get searches for your field and city.</p>
          )}
          <LinkList title="Meetup" items={links.meetup} />
          <LinkList title="Eventbrite" items={links.eventbrite} />
          <div>
            <h3>Your university</h3>
            {s.profile.university_events_url && (
              <p><a href={s.profile.university_events_url} target="_blank" rel="noopener noreferrer">Your university's careers events <ExternalLink size={13} /></a></p>
            )}
            <form className="form-row" onSubmit={(e) => { e.preventDefault(); save.run() }} style={{ marginTop: 6 }}>
              <label className="field" style={{ flex: 1 }}>Careers events page
                <input type="text" maxLength={500} placeholder="careers.youruni.ac.uk/events" value={page} onChange={(e) => setPage(e.target.value)} />
              </label>
              <button className="btn ghost small" type="submit" disabled={save.loading}>Save</button>
            </form>
            <ErrorRetry error={save.error} />
          </div>
          <LinkList title="Professional bodies for your field" items={links.bodies} />
        </div>
      )}
    </section>
  )
}

function EventForm({ s, event, onSaved, onCancel }) {
  const [form, setForm] = useState(event
    ? { ...event, starts_at: londonInput(event.starts_at), link: event.link || '' }
    : { name: '', starts_at: '', place: '', online: false, link: '', type: 'meetup', status: 'interested', notes: '' })
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const submit = async (e) => {
    e.preventDefault()
    const body = { name: form.name, starts_at: form.starts_at, place: form.place, online: form.online, link: form.link || null,
      type: form.type, status: form.status, notes: form.notes }
    try {
      onSaved(event ? await patch(`/api/networking-events/${event.id}`, body) : await post('/api/networking-events', body))
    } catch (err) {
      setError(err)
    }
  }
  return (
    <form className="stack" onSubmit={submit} style={{ marginTop: 12 }}>
      <label className="field">Event<input type="text" required maxLength={200} value={form.name} onChange={set('name')} /></label>
      <div className="grid cols-2">
        <label className="field">Date and time (UK)<input type="datetime-local" required value={form.starts_at} onChange={set('starts_at')} /></label>
        <label className="field">Kind of event
          <select value={form.type} onChange={set('type')}>{s.options.event_types.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        </label>
        <label className="field">Place<input type="text" maxLength={200} placeholder="Venue and town" value={form.place} onChange={set('place')} /></label>
        <label className="field">You are
          <select value={form.status} onChange={set('status')}>{s.options.event_statuses.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        </label>
      </div>
      <label className="check"><input type="checkbox" checked={form.online} onChange={set('online')} />Online</label>
      <label className="field">Link<input type="text" maxLength={500} placeholder="The event's page" value={form.link} onChange={set('link')} /></label>
      <div className="row">
        <button className="btn" type="submit">{event ? 'Save' : 'Save event'}</button>
        <button className="btn ghost" type="button" onClick={onCancel}>Cancel</button>
      </div>
      <ErrorRetry error={error} />
    </form>
  )
}

function SavedEvent({ s, ev, refresh, notify }) {
  const [open, setOpen] = useState(null) // 'edit' | 'met' | null
  const safely = attempt(notify)
  const prepare = useAction(async () => { const r = await post(`/api/ai/networking-events/${ev.id}/prepare`); await refresh(); return r })
  const status = (value) => safely(async () => { await patch(`/api/networking-events/${ev.id}`, { status: value }); await refresh() })
  const remove = () => {
    if (!window.confirm(`Delete ${ev.name}? People you met there stay in your contacts.`)) return
    safely(async () => { await del(`/api/networking-events/${ev.id}`); await refresh(); notify('Event deleted') })
  }
  const box = dayBox(ev.on_day)
  const met = s.contacts.filter((c) => c.event_id === ev.id)
  const p = ev.prep

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="event">
        <div className="datebox"><b>{box.day}</b><span>{box.month}</span></div>
        <div style={{ minWidth: 0 }}>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}><span className="strong">{ev.name}</span><span className="chip">{label(s, 'event_types', ev.type)}</span></div>
          <div className="small muted">{eventWhen(ev.starts_at)}{ev.online ? ', online' : ev.place ? `, ${ev.place}` : ''}</div>
          {ev.link && <a className="small" href={ev.link} target="_blank" rel="noopener noreferrer">Event page <ExternalLink size={12} /></a>}
        </div>
        <div className="row" style={{ gap: 4 }}>
          <select aria-label="You are" value={ev.status} onChange={(e) => status(e.target.value)}>
            {s.options.event_statuses.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <button className="icon-btn" aria-label={`Delete ${ev.name}`} onClick={remove}><Trash2 size={16} /></button>
        </div>
      </div>

      <div className="row" style={{ flexWrap: 'wrap' }}>
        {ev.status !== 'attended' && (
          <button className="btn ghost small" disabled={prepare.loading} onClick={() => prepare.run()}>
            {prepare.loading ? 'Preparing' : p ? 'Prepare again' : 'Prepare'}
          </button>
        )}
        {ev.status === 'attended' && <button className="btn small" onClick={() => setOpen(open === 'met' ? null : 'met')}>Who did you meet?</button>}
        <button className="btn ghost small" onClick={() => setOpen(open === 'edit' ? null : 'edit')}>Edit</button>
        {ev.status !== 'attended' && !p && <span className="small muted">One AI action: an introduction, openers and a goal.</span>}
      </div>
      <ErrorRetry error={prepare.error} onRetry={prepare.retry} />

      {p && ev.status !== 'attended' && (
        <div className="sub-block">
          <h4>Your 30-second introduction</h4>
          <p className="draft">{p.introduction}</p>
          <h4>Ways to start a conversation</h4>
          <ul className="small">{p.openers.map((o) => <li key={o}>{o}</li>)}</ul>
          <p className="small"><span className="strong">Your goal: </span>{p.goal}</p>
        </div>
      )}

      {met.length > 0 && <p className="small">Met here: {met.map((c) => c.name).join(', ')}. Message each within 48 hours.</p>}
      {open === 'met' && (
        <PersonForm s={s} preset={{ relationship: 'event', event_id: ev.id }}
          onSaved={async (c) => { setOpen(null); await refresh(); notify(`${c.name} added. Send a message within 48 hours.`) }}
          onCancel={() => setOpen(null)} />
      )}
      {open === 'edit' && <EventForm s={s} event={ev} onSaved={async () => { setOpen(null); await refresh(); notify('Saved') }} onCancel={() => setOpen(null)} />}
    </div>
  )
}

// The Events tab: where to look, then the user's own saved events, soonest first
export default function NetworkingEvents({ s, links, error, retry, refresh, notify }) {
  const [adding, setAdding] = useState(false)
  const events = s.networking_events
  return (
    <div className="grid split">
      <div className="stack">
        <section className="card">
          <div className="row"><h2>My events</h2><span className="spacer" />{!adding && events.length > 0 && <button className="btn small" onClick={() => setAdding(true)}>Save an event</button>}</div>
          {adding && <EventForm s={s} onSaved={async () => { setAdding(false); await refresh(); notify('Event saved') }} onCancel={() => setAdding(false)} />}
          {events.length === 0 && !adding && (
            <Empty title="No events saved yet" body="Find a meetup, careers fair or webinar through the searches here, then save it to prepare for it and track who you meet."
              action="Save an event" onAction={() => setAdding(true)} />
          )}
          {events.length > 0 && <div className="list" style={{ marginTop: 12 }}>{events.map((ev) => <SavedEvent key={ev.id} s={s} ev={ev} refresh={refresh} notify={notify} />)}</div>}
        </section>
      </div>
      <WhereToLook s={s} links={links} error={error} retry={retry} refresh={refresh} notify={notify} />
    </div>
  )
}
