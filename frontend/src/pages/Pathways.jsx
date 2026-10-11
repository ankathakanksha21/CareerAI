import { post } from '../api'
import { Empty, ErrorRetry, FamilyCard, PageHead, VISA_LABEL, fmtDate, useAction } from '../ui'

export default function Pathways({ s, refresh, go }) {
  const suggest = useAction(async () => { await post('/api/ai/families'); await refresh() })
  const toggle = async (f) => { await post(`/api/families/${f.id}/target`, { targeted: !f.targeted }); refresh() }
  const p = s.profile
  const hasFamilies = s.role_families.length > 0

  return (
    <>
      <PageHead title="Career pathways" lede="Role families that fit your profile: direct fits, near fits and a stretch. Pick 3 to 5 to target; each shows what UK employers expect and what you already evidence.">
        {hasFamilies && <button className="btn ghost" disabled={suggest.loading} onClick={() => suggest.run()}>{suggest.loading ? 'Reading your profile' : 'Re-check fit from my profile'}</button>}
      </PageHead>
      <ErrorRetry error={suggest.error} onRetry={suggest.retry} />

      {s.achievements.length === 0 && (
        <Empty title="Build your profile first" body="Role families are worked out from your achievements." action="Go to Profile" onAction={() => go('profile')} />
      )}
      {s.achievements.length > 0 && !hasFamilies && (
        <Empty title="See which roles fit you" body="We compare your achievements with what UK employers ask for." action={suggest.loading ? 'Reading your profile' : 'Find roles that fit my profile'} onAction={() => !suggest.loading && suggest.run()} />
      )}
      {hasFamilies && <div className="grid cols-3">{s.role_families.map((f) => <FamilyCard key={f.id} f={f} onToggle={toggle} />)}</div>}

      <div className="grid cols-3 section">
        <section className="card">
          <h2>Your dates</h2>
          <div className="list" style={{ marginTop: 12 }}>
            <div className="date-row"><span className="d">{fmtDate(p.graduation_date, { month: 'short', year: 'numeric' })}</span><span>Graduation</span></div>
            <div className="date-row"><span className="d">{fmtDate(p.visa_end_date, { day: 'numeric', month: 'short', year: 'numeric' })}</span><span>Your {VISA_LABEL[p.visa_type]} visa ends</span></div>
          </div>
        </section>
        <section className="card">
          <h2>How the UK market works</h2>
          <div className="list" style={{ marginTop: 12 }}>
            {s.content.uk_market.map((g) => <div key={g.title}><h3>{g.title}</h3><p className="small" style={{ marginTop: 2 }}>{g.body}</p></div>)}
          </div>
        </section>
        <section className="card">
          <h2>Where to look</h2>
          <div className="list" style={{ marginTop: 12 }}>
            {s.content.where_to_look.map((g) => <div key={g.name}><h3>{g.name}</h3><p className="small" style={{ marginTop: 2 }}>{g.tip}</p></div>)}
          </div>
        </section>
      </div>
    </>
  )
}
