import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Bookmark, BookmarkCheck, Check, ChevronDown, ExternalLink } from 'lucide-react'
import { api, post, put } from '../api'
import { Chips, Empty, ErrorRetry, FIT_LABEL, PageHead, daysUntil, fmtDate, money } from '../ui'
import { SalaryFacts, SourcesLine, SponsorLine, VisaLine } from '../components/Visa'
import { JobText } from '../components/Jobs'

const MIN_MATCH = 40 // below this the server labels an advert "not a match"

const salaryText = (m) => {
  const low = m.salary_min ?? m.salary_max
  const high = m.salary_max ?? m.salary_min
  if (!low) return 'Salary not stated'
  if (!m.salary_annual) return 'Rate, not annual salary'
  return `${low === high ? money(low) : `${money(low)} to ${money(high)}`} a year`
}

// One need on the fit box, marked the way the needs on a role family card are: a tick for shown, a hollow mark for a gap
function Need({ shown, children }) {
  return (
    <li className="need">
      <span className={`mark ${shown ? 'yes' : 'no'}`} aria-hidden="true">{shown ? <Check size={13} strokeWidth={3} /> : ''}</span>
      <div><span className="sr-only">{shown ? 'You show: ' : 'Gap: '}</span>{children}</div>
    </li>
  )
}

// What the user shows and lacks for one advert. The box opens from Why beside the fit on the card
function Fit({ m, id, open }) {
  if (!m.scored_at) return null
  if (m.fit_percent == null) return <p className="small muted">This advert says too little to judge your fit.</p>
  if (!open) return null
  return (
    <div className="fitbox" id={id}>
      <div>
        {m.shown.length === 0 && <p className="small muted">Nothing in your profile matches yet.</p>}
        <ul className="plain stack small" style={{ gap: 6 }}>{m.shown.map((x) => <Need key={x.need} shown>{x.need} <span className="muted">from "{x.achievement}"</span></Need>)}</ul>
      </div>
      <div>
        {m.gaps.length === 0 && <p className="small muted">No gaps found.</p>}
        <ul className="plain stack small" style={{ gap: 6 }}>{m.gaps.map((g) => <Need key={g}>{g}</Need>)}</ul>
      </div>
      {m.fit_from_summary && <p className="small muted" style={{ gridColumn: '1 / -1' }}>Fit based on a short summary of the advert.</p>}
    </div>
  )
}

function JobCard({ m, visa, newDays, tracked, pending, on }) {
  const [why, setWhy] = useState(false)
  const fitId = useId()
  const busy = pending === m.id
  const posted = -daysUntil(m.posted_on) // days ago
  const annual = m.salary_annual && (m.salary_min ?? m.salary_max)
  const course = m.posted_by === 'training' // sells a course: nothing to tailor a CV for or track
  return (
    <article className="card jobcard">
      <div className="row" style={{ alignItems: 'baseline' }}>
        <h3>{m.title}</h3>
        {m.status === 'new' && <span className="chip good">New</span>}
        {posted <= newDays && <span className="chip warn">Posted in the last 48 hours</span>}
        <span className="spacer" />
        {m.fit_percent != null && (
          <span className="jobcard-fit">
            <span className={`fit ${m.fit_label}`}>{FIT_LABEL[m.fit_label]}, {m.fit_percent}%{m.fit_from_summary ? ', from a summary' : ''}</span>
            {m.scored_at && (
              <button type="button" className="linkish small showmore-btn" aria-expanded={why} aria-controls={why ? fitId : undefined} onClick={() => setWhy(!why)}>
                Why<ChevronDown size={15} aria-hidden="true" className={why ? 'flip' : ''} />
              </button>
            )}
          </span>
        )}
      </div>
      <p className="small muted">
        {[`${m.employer}${m.location ? `, ${m.location}` : ''}`, `Posted ${fmtDate(m.posted_on)}`, salaryText(m)].join(' · ')}{' · '}
        <a href={m.url} target="_blank" rel="noopener noreferrer">View on Reed <ExternalLink size={12} style={{ verticalAlign: '-1px' }} /></a>
      </p>
      {!m.scored_at && m.snippet && <JobText text={`${m.snippet}${m.snippet.length >= 300 ? '...' : ''}`} />}
      <Fit m={m} id={fitId} open={why} />
      <SponsorLine status={m.sponsor_status} name={m.sponsor_name} links={visa.links} postedBy={m.posted_by} />
      {annual && !course && (
        <details className="small">
          <summary>Skilled Worker salary figures</summary>
          <SalaryFacts visa={visa} advertised={{ min: m.salary_min ?? m.salary_max, max: m.salary_max ?? m.salary_min }} />
        </details>
      )}
      <div className="row job-actions">
        {!course && (
          <>
            <button className="btn ghost small" disabled={busy || m.status === 'saved'} onClick={() => on.save(m)}>
              {m.status === 'saved' ? <><BookmarkCheck size={14} aria-hidden="true" />Saved</> : <><Bookmark size={14} aria-hidden="true" />Save</>}
            </button>
            <button className="btn ghost small" disabled={busy} onClick={() => on.tailor(m)}>Tailor CV</button>
            <button className="btn ghost small" disabled={busy} onClick={() => on.practise(m)}>Practise interview</button>
            <button className="btn ghost small" disabled={busy || tracked} onClick={() => on.track(m)}>{tracked ? 'In Applications' : 'Add to tracker'}</button>
          </>
        )}
        <span className="spacer" />
        <button className="linkish small" disabled={busy} onClick={() => on.hide(m)}>Not for me</button>
      </div>
    </article>
  )
}

// While the saved adverts load: grey cards in the shape of job cards. Screen readers hear Loading
function Skeleton() {
  return (
    <div className="stack jobs-skeleton" role="status">
      <span className="sr-only">Loading</span>
      {[0, 1, 2].map((i) => (
        <div key={i} className="card jobcard" aria-hidden="true">
          <span className="jobs-skeleton-line" style={{ width: '45%', height: 16 }} />
          <span className="jobs-skeleton-line" style={{ width: '70%' }} />
          <span className="jobs-skeleton-line" style={{ width: '90%' }} />
        </div>
      ))}
    </div>
  )
}

export default function Jobs({ s, refresh, go, notify }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [working, setWorking] = useState(null) // 'search' or 'score' while a refresh runs
  const [last, setLast] = useState(null) // what the latest refresh reported
  const [pending, setPending] = useState(null) // the match whose button was just pressed
  const [filters, setFilters] = useState({ family: '', location: '', sponsors: false })
  const opened = useRef(false)

  const targeted = s.role_families.filter((f) => f.targeted)
  const canSearch = targeted.length > 0 && s.achievements.length > 0

  const load = useCallback(async () => {
    const d = await api('/api/jobs')
    setData(d)
    return d
  }, [])

  const check = useCallback(async (kind = 'search') => {
    setWorking(kind)
    setError(null)
    try {
      setLast(await post('/api/jobs/refresh'))
      await load()
      await refresh()
    } catch (e) {
      setError(e)
      load().catch(() => {}) // adverts already stored are still worth showing
    } finally {
      setWorking(null)
    }
  }, [load, refresh])

  useEffect(() => {
    if (opened.current) return // the app runs effects twice in development
    opened.current = true
    load().then((d) => {
      if (d.due && d.configured && canSearch) return check('search')
      // the "New" markers already on screen stay; the count on the menu clears
      if (d.matches.some((m) => m.status === 'new')) return post('/api/jobs/seen').then(refresh)
    }).catch(setError)
  }, [load, check, refresh, canSearch])

  const act = async (m, fn) => {
    setPending(m.id)
    try {
      await fn()
    } catch (e) {
      notify(e.message || 'That did not work. Try again.')
      load().catch(() => {})
    } finally {
      setPending(null)
    }
  }
  const patchMatch = (id, change) => setData((d) => ({ ...d, matches: d.matches.map((x) => (x.id === id ? { ...x, ...change } : x)) }))
  const saved = async (m) => {
    const job = await post(`/api/jobs/${m.id}/save`)
    patchMatch(m.id, { status: 'saved' })
    await refresh()
    return job
  }
  const on = {
    save: (m) => act(m, async () => { await saved(m); notify('Job saved') }),
    tailor: (m) => act(m, async () => { const job = await saved(m); go('resume', null, { jobId: job.id }) }),
    practise: (m) => act(m, async () => { const job = await saved(m); go('interview', null, { jobId: job.id }) }),
    track: (m) => act(m, async () => {
      await post(`/api/jobs/${m.id}/track`)
      patchMatch(m.id, { status: 'saved' })
      await refresh()
      notify(`Added ${m.title} at ${m.employer} to Applications`)
    }),
    hide: (m) => act(m, async () => {
      setData((d) => ({ ...d, matches: d.matches.filter((x) => x.id !== m.id) }))
      await post(`/api/jobs/${m.id}/hide`)
      refresh()
    }),
  }
  const setSenior = async (value) => {
    try {
      await put('/api/jobs/preferences', { include_senior: value })
      setData((d) => ({ ...d, include_senior: value }))
    } catch (e) {
      notify(e.message)
    }
  }

  const head = (
    <PageHead title="Jobs" lede="Live adverts for your target roles.">
      {data && canSearch && data.configured && (
        <button className="btn ghost" disabled={!!working} onClick={() => check('search')}>{working === 'search' ? 'Searching Reed' : 'Check for new jobs'}</button>
      )}
    </PageHead>
  )

  if (s.achievements.length === 0) {
    return <>{head}<Empty title="Add your achievements first" action="Go to Profile" onAction={() => go('profile')} /></>
  }
  if (targeted.length === 0) {
    return <>{head}<Empty title="Pick your target roles" action="Go to Pathways" onAction={() => go('pathways')} /></>
  }
  if (!data) {
    return <>{head}{error ? <ErrorRetry error={error} onRetry={() => { setError(null); load().catch(setError) }} /> : <Skeleton />}</>
  }
  if (!data.configured && data.matches.length === 0) {
    return <>{head}<Empty title="Job search is not set up yet" body="You can still paste an advert." action="Add a job" onAction={() => go('resume')} /></>
  }

  const tracked = new Set(s.applications.map((a) => s.saved_jobs.find((j) => j.id === a.saved_job_id)?.listing_id).filter(Boolean))
  const wanted = (m) => (!filters.family || m.role_family_id === filters.family)
    && (!filters.location || m.search_location === filters.location)
    && (!filters.sponsors || m.sponsor_status === 'listed' || m.sponsor_status === 'possible')
    && (data.include_senior || !m.senior)
  const courses = data.matches.filter((m) => m.posted_by === 'training' && wanted(m)) // adverts that sell a course, kept apart
  const real = data.matches.filter((m) => m.posted_by !== 'training')
  const shown = real.filter(wanted)
  const seniorHidden = data.include_senior ? 0 : real.filter((m) => m.senior).length
  const matches = shown.filter((m) => m.fit_percent != null && m.fit_percent >= MIN_MATCH)
  const unchecked = shown.filter((m) => !m.scored_at)
  const notMatch = shown.filter((m) => m.scored_at && (m.fit_percent == null || m.fit_percent < MIN_MATCH))
  const locations = [...new Set(data.matches.map((m) => m.search_location).filter(Boolean))]
  const card = (m) => <JobCard key={m.id} m={m} visa={data.visa} newDays={data.new_days} tracked={tracked.has(m.listing_id)} pending={pending} on={on} />

  return (
    <>
      {head}
      <section className="card tint tight"><VisaLine profile={s.profile} links={data.visa.links} /></section>

      <div className="row job-filters">
        <label className="field">Role
          <select value={filters.family} onChange={(e) => setFilters({ ...filters, family: e.target.value })}>
            <option value="">All target roles</option>
            {targeted.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </label>
        <label className="field">Location
          <select value={filters.location} onChange={(e) => setFilters({ ...filters, location: e.target.value })}>
            <option value="">All your locations</option>
            {locations.map((l) => <option key={l} value={l}>{l.replace(/\b\w/g, (c) => c.toUpperCase())}</option>)}
          </select>
        </label>
        <label className="check"><input type="checkbox" checked={filters.sponsors} onChange={(e) => setFilters({ ...filters, sponsors: e.target.checked })} />Sponsors only</label>
        <label className="check"><input type="checkbox" checked={data.include_senior} onChange={(e) => setSenior(e.target.checked)} />Include senior roles</label>
      </div>
      <SourcesLine register={data.register} visa={data.visa} />

      {working === 'search' && <p className="note jobs-working" role="status"><span className="spinner" aria-hidden="true" />Searching Reed, can take half a minute</p>}
      {working === 'score' && <p className="note jobs-working" role="status"><span className="spinner" aria-hidden="true" />Checking fit</p>}
      {!working && last?.notice && <p className="note" role="status">{last.notice}</p>}
      {!working && last?.remaining > 0 && (
        <p className="small"><button className="linkish" onClick={() => check('search')}>Run {last.remaining} more {last.remaining === 1 ? 'search' : 'searches'}</button></p>
      )}
      <ErrorRetry error={error} onRetry={() => check('search')} />

      {data.matches.length === 0 && !working && !error && (
        <Empty title="No jobs found yet" body={`No matches posted in the last ${data.fresh_days} days. Try again tomorrow, or add a location on your Profile.`}
          action="Check again" onAction={() => check('search')} />
      )}

      {data.matches.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <Chips tone="muted" items={[
            matches.length !== real.length ? `${matches.length} of ${real.length} match` : `${matches.length} ${matches.length === 1 ? 'match' : 'matches'}`,
            'Newest first',
            ...(seniorHidden > 0 ? [`${seniorHidden} senior hidden`] : []),
          ]} />
        </div>
      )}
      <div className="stack" style={{ marginTop: 10 }}>{matches.map(card)}</div>
      {real.length > 0 && matches.length === 0 && unchecked.length === 0 && !working && (
        <p className="muted" style={{ marginTop: 10 }}>No matches with these filters. See "Not a match" below, or change the filters.</p>
      )}

      {unchecked.length > 0 && (
        <section className="section">
          <div className="section-head">
            <h2>Not checked yet ({unchecked.length})</h2>
            <button className="btn ghost small" disabled={!!working} onClick={() => check('score')}>
              {working === 'score' ? 'Checking' : `Check fit for the next ${Math.min(unchecked.length, data.score_per_refresh)}`}
            </button>
          </div>
          <div className="stack">{unchecked.map(card)}</div>
        </section>
      )}

      {notMatch.length > 0 && (
        <details className="section">
          <summary className="strong">Not a match, under {MIN_MATCH}% fit ({notMatch.length})</summary>
          <div className="stack" style={{ marginTop: 10 }}>{notMatch.map(card)}</div>
        </details>
      )}

      {courses.length > 0 && (
        <details className="section">
          <summary className="strong">Training programmes, not jobs ({courses.length})</summary>
          <p className="small muted" style={{ margin: '6px 0 10px' }}>
            Not scored or counted. Check any cost before signing up.
          </p>
          <div className="stack">{courses.map(card)}</div>
        </details>
      )}
    </>
  )
}
