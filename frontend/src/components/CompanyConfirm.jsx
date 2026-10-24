import { useEffect, useId, useRef, useState } from 'react'
import { post } from '../api'
import { ErrorRetry, InfoTip, useAction } from '../ui'

const year = (iso) => (iso ? iso.slice(0, 4) : '')

// Step one of a pack: the user confirms which company it is, then the company is researched and the pack written
export default function CompanyConfirm({ target, onBuilt, onCancel }) {
  const [name, setName] = useState(target.company)
  const [choice, setChoice] = useState('') // a Companies House number, "none" or "not_uk"
  const [website, setWebsite] = useState('')
  const [company, setCompany] = useState(null) // the research once done, so a failed pack is retried without researching again
  const siteId = useId()
  const search = useAction(async (n) => {
    const r = await post('/api/companies/search', { name: n })
    setChoice(r.matches.length ? '' : 'none')
    return r
  })
  const research = useAction(() => post('/api/companies/research', {
    name, website, not_uk: choice === 'not_uk', company_number: ['none', 'not_uk'].includes(choice) ? null : choice,
  }))
  const build = useAction((c) => post('/api/ai/prep', {
    company_id: c.company_id, ...(target.job_id ? { job_id: target.job_id } : { application_id: target.application_id }),
  }))
  const opened = useRef(false)
  useEffect(() => {
    if (opened.current) return // the app runs effects twice in development
    opened.current = true
    search.run(target.company)
  }, [search, target.company])

  const changed = (set) => (value) => { set(value); setCompany(null) }
  const working = research.loading || build.loading
  const start = async () => {
    const c = company || await research.run()
    if (!c) return
    setCompany(c)
    const pack = await build.run(c)
    if (pack) onBuilt(pack)
  }
  const matches = search.result?.matches || []

  return (
    <section className="card stack">
      <div>
        <h2>Which company is it?</h2>
        <p className="sub">For {target.role}. Pick the right one on the official register.</p>
      </div>
      <div className="row">
        <input type="text" value={name} maxLength={160} onChange={(e) => changed(setName)(e.target.value)} aria-label="Company name" style={{ flex: 1 }} />
        <button className="btn ghost small" disabled={search.loading || !name.trim() || working} onClick={() => search.run(name.trim())}>{search.loading ? 'Searching' : 'Search again'}</button>
      </div>
      {search.error && <p className="small muted" role="status">{search.error.message} Pick "None of these" to carry on.</p>}
      <fieldset className="stack" style={{ gap: 6, border: 0, padding: 0, margin: 0 }} disabled={working}>
        <legend className="small strong" style={{ marginBottom: 6 }}>Companies House</legend>
        {matches.map((m) => (
          <label key={m.number} className="check">
            <input type="radio" name="company" checked={choice === m.number} onChange={() => changed(setChoice)(m.number)} />
            <span><span className="strong">{m.name}</span><span className="small muted"> {[m.town, m.status, m.incorporated_on && `since ${year(m.incorporated_on)}`].filter(Boolean).join(', ')}</span></span>
          </label>
        ))}
        {search.result && !matches.length && <p className="small muted">No match on Companies House.</p>}
        <label className="check"><input type="radio" name="company" checked={choice === 'none'} onChange={() => changed(setChoice)('none')} />None of these</label>
        <label className="check"><input type="radio" name="company" checked={choice === 'not_uk'} onChange={() => changed(setChoice)('not_uk')} />Not a UK company</label>
      </fieldset>
      {/* a div, not a wrapping label, so the label names only the input and not the (i) beside it */}
      <div className="companyconfirm-field">
        <span className="companyconfirm-label">
          <label htmlFor={siteId}>Their website (optional)</label>
          <InfoTip label="What we read from their website">We read their home page and up to five pages such as About, Careers and News.</InfoTip>
        </span>
        <input id={siteId} type="text" value={website} maxLength={300} placeholder="acme.co.uk" disabled={working} onChange={(e) => changed(setWebsite)(e.target.value)} />
      </div>
      {['none', 'not_uk'].includes(choice) && <p className="small muted">The pack still works without the register.</p>}
      <div className="row">
        <button className="btn" disabled={!choice || !name.trim() || working} onClick={start}>Build my pack</button>
        <button className="btn ghost" disabled={working} onClick={onCancel}>Cancel</button>
        <span className="small muted">{research.loading ? `Researching ${name}: website, Companies House, news. About 30 seconds.`
          : build.loading ? 'Writing your pack. About 30 seconds.' : 'One company search and one AI action.'}</span>
      </div>
      <ErrorRetry error={research.error} onRetry={start} />
      <ErrorRetry error={build.error} onRetry={start} />
    </section>
  )
}
