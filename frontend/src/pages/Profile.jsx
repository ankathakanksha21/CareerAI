import { useState } from 'react'
import { post } from '../api'
import { Avatar, ErrorRetry, PageHead, VISA_LABEL, fmtDate, plural, useAction } from '../ui'
import DetailsForm from '../components/DetailsForm'
import BackgroundInput from '../components/BackgroundInput'
import FoundFacts, { hasFacts, mergeFound } from '../components/FoundFacts'
import AchievementCard from '../components/AchievementCard'
import { Education, Skills, WorkHistory } from '../components/History'
import ContactForm, { AdditionalLines } from '../components/ContactForm'

export default function Profile({ s, refresh, go, notify, session }) {
  const [editing, setEditing] = useState(false)
  const [found, setFound] = useState(null) // jobs, courses and skills an import read, until the user confirms them
  const p = s.profile
  const star = useAction(async (id) => {
    await post('/api/ai/star', { achievement_id: id })
    await refresh()
    notify('STAR story added to Interview coach')
  })
  const built = async (r) => {
    setFound((was) => mergeFound(was, { facts: r.facts, source: r.source, notice: r.notice }))
    await refresh()
    notify(r.items.length ? `${plural(r.items.length, 'achievement')} added to your profile` : 'No new achievements in that')
  }

  return (
    <>
      <PageHead title="Profile" lede="Everything you have done, written in the language UK employers scan for. Your CVs, interview stories and practice are all built from this." />

      <section className="card">
        {editing ? (
          <DetailsForm profile={p} onCancel={() => setEditing(false)} onSaved={async () => { await refresh(); setEditing(false); notify('Details saved') }} />
        ) : (
          <>
            <div className="profile-head">
              <Avatar name={p.full_name} size="lg" />
              <div style={{ flex: 1 }}>
                <div className="row"><h2 style={{ fontSize: 19 }}>{p.full_name}</h2><span className="spacer" /><button className="btn ghost small" onClick={() => setEditing(true)}>Edit details</button></div>
                <p className="muted">{p.course}, {p.university}</p>
                {p.pitch
                  ? <p className="pitch">{p.pitch}</p>
                  : <p className="small muted" style={{ marginTop: 10 }}>Add your background below and a two-line pitch appears here.</p>}
              </div>
            </div>
            <dl className="kv" style={{ marginTop: 16 }}>
              <dt>Visa</dt><dd>{VISA_LABEL[p.visa_type]} visa, ends {fmtDate(p.visa_end_date, { day: 'numeric', month: 'long', year: 'numeric' })}</dd>
              <dt>Graduation</dt><dd>{fmtDate(p.graduation_date, { month: 'long', year: 'numeric' })}</dd>
              <dt>Locations</dt><dd>{p.locations.join(', ')}</dd>
            </dl>
          </>
        )}
      </section>

      <div className="section">
        <div className="section-head"><h2>Add to your profile</h2><p>Talk to the coach, upload a CV, paste text or add GitHub projects.</p></div>
        <BackgroundInput s={s} userId={session.user.id} onBuilt={built} />
        {found?.notice && <p className="small muted" role="status" style={{ marginTop: 12 }}>{found.notice}</p>}
        {hasFacts(found) && (
          <div style={{ marginTop: 16 }}>
            <FoundFacts found={found} onDismiss={() => setFound(null)}
              onSaved={async () => { setFound(null); await refresh(); notify('Added to your profile') }} />
          </div>
        )}
      </div>

      <WorkHistory s={s} refresh={refresh} notify={notify} />
      <Education s={s} refresh={refresh} notify={notify} />
      <Skills s={s} refresh={refresh} notify={notify} />

      <div className="section">
        <div className="section-head"><h2>For your CV</h2><p>Printed on every CV you build. Never sent to the AI.</p></div>
        <div className="card stack">
          <ContactForm profile={p} onSaved={async () => { await refresh(); notify('Contact details saved') }} />
          <AdditionalLines profile={p} onSaved={async () => { await refresh(); notify('Saved for your next CV') }} />
        </div>
      </div>

      <div className="section">
        <div className="section-head"><h2>Achievements ({s.achievements.length})</h2><p>Each one shows the UK version and the words it came from.</p></div>
        <ErrorRetry error={star.error} onRetry={star.retry} />
        {s.achievements.length === 0 && <p className="muted">No achievements yet. Talk to the coach, upload your CV or paste text above to build your profile.</p>}
        <div className="grid cols-3">
          {s.achievements.map((a) => (
            <AchievementCard key={a.id} a={a} s={s} refresh={refresh} notify={notify} onStar={star.run} starring={star.loading} />
          ))}
        </div>
        {s.achievements.length > 0 && s.role_families.length === 0 && (
          <div className="row" style={{ marginTop: 16 }}><button className="btn" onClick={() => go('pathways')}>Find roles that fit</button></div>
        )}
      </div>
    </>
  )
}
