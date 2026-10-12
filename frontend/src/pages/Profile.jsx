import { useState } from 'react'
import { del, post } from '../api'
import { Avatar, ErrorRetry, PageHead, VISA_LABEL, attempt, fmtDate, useAction } from '../ui'
import DetailsForm from '../components/DetailsForm'
import BackgroundInput from '../components/BackgroundInput'

export default function Profile({ s, refresh, go, notify, session }) {
  const [editing, setEditing] = useState(false)
  const p = s.profile
  const star = useAction(async (id) => {
    await post('/api/ai/star', { achievement_id: id })
    await refresh()
    notify('STAR story added to Interview coach')
  })
  const remove = async (a) => {
    if (!window.confirm('Delete this achievement?')) return
    await attempt(notify)(async () => {
      await del(`/api/achievements/${a.id}`)
      await refresh()
      notify('Achievement deleted')
    })
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
        <div className="section-head"><h2>Add to your profile</h2><p>Talk to the coach, or paste a CV or notes.</p></div>
        <BackgroundInput s={s} userId={session.user.id} onBuilt={async (r) => { await refresh(); notify(`${r.items.length} added to your profile`) }} />
      </div>

      <div className="section">
        <div className="section-head"><h2>Achievements ({s.achievements.length})</h2><p>Each one shows what you said and the UK version.</p></div>
        <ErrorRetry error={star.error} onRetry={star.retry} />
        {s.achievements.length === 0 && <p className="muted">No achievements yet. Talk to the coach or paste your CV to build your profile.</p>}
        <div className="grid cols-3">
          {s.achievements.map((e) => (
            <article key={e.id} className="card evidence-card">
              <h3>{e.title}</h3>
              <p className="uk">{e.uk_version}</p>
              {e.raw && <p className="said">You said: "{e.raw}"</p>}
              {(e.outcome || e.scale) && (
                <dl className="kv">
                  {e.outcome && <><dt>Result</dt><dd>{e.outcome}</dd></>}
                  {e.scale && <><dt>Scale</dt><dd>{e.scale}</dd></>}
                </dl>
              )}
              <div className="row">{e.skills.map((k) => <span key={k} className="chip">{k}</span>)}</div>
              {e.context_note && <p className="context">{e.context_note}</p>}
              <div className="row">
                <button className="linkish small" onClick={() => remove(e)}>Delete</button>
                <span className="spacer" />
                <button className="btn ghost small" disabled={star.loading} onClick={() => star.run(e.id)}>Make a STAR story</button>
              </div>
            </article>
          ))}
        </div>
        {s.achievements.length > 0 && s.role_families.length === 0 && (
          <div className="row" style={{ marginTop: 16 }}><button className="btn" onClick={() => go('pathways')}>Find roles that fit</button></div>
        )}
      </div>
    </>
  )
}
