import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Empty, PageHead } from '../ui'
import ContactCard from '../components/ContactCard'
import FindPeople from '../components/FindPeople'
import NetworkingEvents from '../components/NetworkingEvents'
import NetworkingGuide from '../components/NetworkingGuide'
import PersonForm from '../components/PersonForm'

const TABS = [['people', 'People'], ['events', 'Events'], ['guide', 'Guide']]

// The search links depend only on these, so they are fetched again only when one changes
const linkInputs = (s) => JSON.stringify([s.profile.university, s.profile.locations, s.profile.university_events_url,
  s.role_families.filter((f) => f.targeted).map((f) => f.name), s.saved_jobs.map((j) => j.company)])

function People({ s, refresh, notify, go, links, linksError, retryLinks }) {
  const [adding, setAdding] = useState(false)
  const [show, setShow] = useState('all')
  const count = (status) => s.contacts.filter((c) => c.status === status).length
  const current = show === 'all' || count(show) ? show : 'all' // a status nobody is at any more shows everyone
  const shown = s.contacts.filter((c) => current === 'all' || c.status === current)
  return (
    <div className="grid split">
      <div className="stack">
        <div className="row">
          {s.contacts.length > 0 && (
            <div className="filters" style={{ margin: 0, flex: 1 }}>
              <button className={`filter ${current === 'all' ? 'active' : ''}`} onClick={() => setShow('all')}>All <span className="filter-count">{s.contacts.length}</span></button>
              {s.options.contact_statuses.filter(([k]) => count(k)).map(([k, l]) => (
                <button key={k} className={`filter ${current === k ? 'active' : ''}`} onClick={() => setShow(k)}>{l} <span className="filter-count">{count(k)}</span></button>
              ))}
            </div>
          )}
          {!adding && s.contacts.length > 0 && <button className="btn small" onClick={() => setAdding(true)}>Add someone</button>}
        </div>
        {adding && (
          <section className="card">
            <h2>Add someone</h2>
            <PersonForm s={s} onSaved={async (c) => { setAdding(false); setShow('all'); await refresh(); notify(`${c.name} added`) }} onCancel={() => setAdding(false)} />
          </section>
        )}
        {s.contacts.length === 0 && !adding && (
          <Empty title="Nobody here yet" body="Start with one person: an alumnus at a company you like, a tutor, or someone you met at an event."
            action="Add someone" onAction={() => setAdding(true)} />
        )}
        {shown.map((c) => <ContactCard key={c.id} s={s} c={c} refresh={refresh} notify={notify} go={go} />)}
      </div>
      <div className="stack">
        <FindPeople links={links} error={linksError} retry={retryLinks} go={go} />
      </div>
    </div>
  )
}

export default function Networking({ s, tab, go, refresh, notify }) {
  const active = TABS.find(([k]) => k === tab) ? tab : 'people'
  const [links, setLinks] = useState(null)
  const [linksError, setLinksError] = useState(null)
  const inputs = linkInputs(s)
  const loadLinks = useCallback(() => api('/api/networking/links').then((r) => { setLinks(r); setLinksError(null) }).catch(setLinksError), [])
  useEffect(() => { loadLinks() }, [inputs, loadLinks])

  const shared = { s, refresh, notify, go, links, linksError, retryLinks: loadLinks }
  return (
    <>
      <PageHead title="Networking" lede="Many UK roles are filled through people you know. Ask for advice, not a job, and track every conversation. Nothing is ever sent for you." />
      <div className="tabs" role="tablist">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={active === k} className={`tab ${active === k ? 'active' : ''}`} onClick={() => go('networking', k === 'people' ? null : k)}>{label}</button>
        ))}
      </div>
      {active === 'people' && <People {...shared} />}
      {active === 'events' && <NetworkingEvents s={s} links={links} error={linksError} retry={loadLinks} refresh={refresh} notify={notify} />}
      {active === 'guide' && <NetworkingGuide s={s} />}
    </>
  )
}
