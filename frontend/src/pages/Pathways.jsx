import { useState } from 'react'
import { post } from '../api'
import { Empty, ErrorRetry, FamilyCard, PageHead, ShowMore, VISA_LABEL, attempt, fmtDate, useAction } from '../ui'
import { RegisterLine, SalaryFacts, SponsorLine } from '../components/Visa'

// Check an offer or an advert against the published facts: the salary figures and the sponsor register
function OfferCheck() {
  const [salary, setSalary] = useState('')
  const [employer, setEmployer] = useState('')
  const [missing, setMissing] = useState(false)
  const check = useAction(() => post('/api/visa-facts', { salary: salary ? Number(salary) : null, employer: employer.trim() || null }))
  const submit = (e) => {
    e.preventDefault()
    const empty = !salary && !employer.trim()
    setMissing(empty)
    if (!empty) check.run()
  }
  const f = check.result
  return (
    <section className="card section">
      <h2>Check an offer</h2>
      <p className="sub">A salary beside the Skilled Worker visa figures, and an employer looked up on the sponsor register.</p>
      <form className="form-row" onSubmit={submit} noValidate>
        <label className="field">Salary a year (£)<input type="number" min="0" step="500" value={salary} onChange={(e) => setSalary(e.target.value)} style={{ width: 170 }} /></label>
        <label className="field">Employer<input type="text" value={employer} onChange={(e) => setEmployer(e.target.value)} style={{ width: 240 }} maxLength={160} /></label>
        <button className="btn" type="submit" disabled={check.loading}>{check.loading ? 'Checking' : 'Check'}</button>
      </form>
      {missing && <p className="error" role="alert" style={{ marginTop: 8 }}>Enter a salary, an employer, or both.</p>}
      <ErrorRetry error={check.error} onRetry={check.retry} />
      {f && (
        <div className="stack" style={{ marginTop: 14 }}>
          {f.sponsor && <SponsorLine status={f.sponsor.status} name={f.sponsor.name} links={f.links} />}
          <SalaryFacts visa={f} advertised={f.advertised} />
          {f.sponsor && <RegisterLine register={f.register} />}
        </div>
      )}
    </section>
  )
}

export default function Pathways({ s, refresh, go, notify }) {
  const suggest = useAction(async () => { await post('/api/ai/families'); await refresh() })
  const toggle = (f) => attempt(notify)(async () => { await post(`/api/families/${f.id}/target`, { targeted: !f.targeted }); await refresh() })
  const p = s.profile
  const hasFamilies = s.role_families.length > 0

  return (
    <>
      <PageHead title="Pathways" lede="Pick 3 to 5 roles to target.">
        {hasFamilies && <button className="btn ghost" disabled={suggest.loading} onClick={() => suggest.run()}>{suggest.loading ? 'Checking' : 'Re-check fit'}</button>}
      </PageHead>
      <ErrorRetry error={suggest.error} onRetry={suggest.retry} />

      {s.achievements.length === 0 && (
        <Empty title="Add your achievements first" action="Go to Profile" onAction={() => go('profile')} />
      )}
      {s.achievements.length > 0 && !hasFamilies && (
        <Empty title="See which roles fit you" action={suggest.loading ? 'Checking' : 'Find my roles'} onAction={() => !suggest.loading && suggest.run()} />
      )}
      {hasFamilies && (
        <div className="grid cols-3">
          {s.role_families.map((f) => <FamilyCard key={f.id} f={f} onToggle={toggle} market={s.market[f.id]} onJobs={() => go('jobs')} />)}
        </div>
      )}

      <OfferCheck />

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
            {s.content.uk_market.map((g) => (
              <ShowMore key={g.title} label={g.title} openLabel={g.title} heading="h3" buttonClassName="pathways-topic">
                <p className="small" style={{ marginTop: 2 }}>{g.body}</p>
              </ShowMore>
            ))}
          </div>
        </section>
        <section className="card">
          <h2>Where to look</h2>
          <div className="list" style={{ marginTop: 12 }}>
            {s.content.where_to_look.map((g) => (
              <ShowMore key={g.name} label={g.name} openLabel={g.name} heading="h3" buttonClassName="pathways-topic">
                <p className="small" style={{ marginTop: 2 }}>{g.tip}</p>
              </ShowMore>
            ))}
          </div>
        </section>
      </div>
    </>
  )
}
