import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { del, post } from '../api'
import { ErrorRetry, InfoTip, PageHead, ShowMore, attempt, plural, useAction } from '../ui'
import { AddJob, JobText } from '../components/Jobs'
import ContactForm from '../components/ContactForm'
import CvEditor from '../components/CvEditor'
import OldCv from '../components/OldCv'
import { unlinked } from '../cv'

const BASE = '' // the picker's first choice: a CV for no particular job

export default function Resume({ s, focus, refresh, go, notify }) {
  const recent = s.cv_versions[0]
  const asked = focus.cvId && s.cv_versions.find((c) => c.id === focus.cvId) // opened from an application
  const [target, setTarget] = useState(asked ? asked.saved_job_id || BASE : focus.jobId || (recent ? recent.saved_job_id || BASE : s.saved_jobs[0]?.id || BASE))
  const [openId, setOpenId] = useState(asked ? asked.id : null) // a version the user picked or just made; otherwise the newest for the target
  const [fresh, setFresh] = useState(null)      // the version as the editor last saved it, ahead of the next full refresh
  const [session, setSession] = useState(0)     // a new number starts the editor afresh on another CV
  const [adding, setAdding] = useState(false)
  const [asking, setAsking] = useState(false)   // asking for contact details before the first CV
  const p = s.profile
  const job = s.saved_jobs.find((j) => j.id === target) || null
  const versions = s.cv_versions.filter((c) => (job ? c.saved_job_id === job.id : c.kind === 'base'))
  const known = (id) => (fresh?.id === id ? fresh : s.cv_versions.find((c) => c.id === id))
  const open = (openId && known(openId)) || versions[0] || null
  const loose = unlinked(s.achievements).length
  const noContact = !p.phone && !p.city && !p.linkedin_url && !s.cv_versions.some((c) => c.format_version === 2)

  const show = (id, nextTarget = target) => { setTarget(nextTarget); setOpenId(id); setFresh(null); setSession((n) => n + 1) }
  const build = useAction(async (jobId) => {
    setAsking(false)
    const cv = await post('/api/ai/cv', jobId ? { job_id: jobId } : {})
    show(cv.id, jobId || BASE)
    setFresh(cv)
    await refresh()
    notify(`${cv.name} is ready`)
  })
  const start = () => (noContact ? setAsking(true) : build.run(job?.id || null))
  const onAdded = async (j) => { await refresh(); show(null, j.id); setAdding(false); notify('Job saved') }
  const removeJob = async () => {
    if (!window.confirm(`Remove ${job.title}, ${job.company}? CVs already built for it are kept.`)) return
    await attempt(notify)(async () => { await del(`/api/jobs/${job.id}`); await refresh(); show(null, BASE) })
  }
  const removeVersion = async (c) => {
    if (!window.confirm(`Delete ${c.name}? This cannot be undone.`)) return
    await attempt(notify)(async () => {
      await del(`/api/cv-versions/${c.id}`)
      if (open?.id === c.id) show(null)
      await refresh()
      notify('CV deleted')
    })
  }
  const onSaved = (saved) => { setFresh(saved); setOpenId(saved.id); refresh() }

  return (
    <>
      <PageHead title="CV" lede="Two-page UK CVs from your profile, for one job or none.">
        {!adding && <button className="btn ghost" onClick={() => setAdding(true)}>Add a job</button>}
      </PageHead>
      {adding && <div style={{ marginBottom: 16 }}><AddJob onAdded={onAdded} onCancel={() => setAdding(false)} /></div>}

      <section className="card">
        <h2>Build a CV</h2>
        <p className="sub">
          The AI writes only the wording; every fact is copied from your profile.{' '}
          <InfoTip label="What the AI does">Your employers, dates, courses and grades are copied from your profile. The AI writes the profile paragraph, picks and rewords your achievements, and orders your skills.</InfoTip>
        </p>
        <div className="row">
          <select value={job ? job.id : BASE} onChange={(e) => show(null, e.target.value)} aria-label="Which CV">
            <option value={BASE}>Base CV (no job)</option>
            {s.saved_jobs.map((j) => <option key={j.id} value={j.id}>{j.title}, {j.company}</option>)}
          </select>
          <button className="btn" disabled={build.loading || s.achievements.length === 0} onClick={start}>
            {build.loading ? 'Building, about 20 seconds' : job ? 'Build CV and cover letter' : 'Build base CV'}
          </button>
          {job && <button className="linkish small" onClick={removeJob}>Remove job</button>}
        </div>
        {job?.summary && <div style={{ marginTop: 10 }}><JobText key={job.id} text={job.summary} className="small muted" /></div>}
        {!job && <p className="small muted" style={{ marginTop: 10 }}>Uses your whole profile, no cover letter. To tailor one, <button className="linkish" onClick={() => setAdding(true)}>paste an advert</button>{s.config.jobs && <> or <button className="linkish" onClick={() => go('jobs')}>pick from Jobs</button></>}.</p>}
        {s.achievements.length === 0 && <p className="small" style={{ marginTop: 10 }}>Add achievements on your <button className="linkish" onClick={() => go('profile')}>Profile</button> first.</p>}
        {loose > 0 && <p className="small muted" style={{ marginTop: 10 }}>{plural(loose, 'achievement')} {loose === 1 ? 'prints' : 'print'} under Projects (not linked to a job or course). <button className="linkish" onClick={() => go('profile')}>Link {loose === 1 ? 'it' : 'them'} on Profile</button></p>}
        <ErrorRetry error={build.error} onRetry={build.retry} />
      </section>

      {asking && (
        <section className="card editing section">
          <h2>Contact details for your CV</h2>
          <p className="sub">Asked once. Printed on every CV, never sent to the AI, editable on Profile.</p>
          <ContactForm profile={p} submitLabel="Save and build" onSaved={async () => { await refresh(); build.run(job?.id || null) }}>
            <button type="button" className="btn ghost" onClick={() => build.run(job?.id || null)}>Build without them</button>
          </ContactForm>
        </section>
      )}

      <div className="section">
        {open && open.format_version === 2 && <CvEditor key={session} version={open} s={s} go={go} notify={notify} refresh={refresh} onSaved={onSaved} />}
        {open && open.format_version !== 2 && (
          <OldCv version={open} name={p.full_name} rebuilding={build.loading} canRebuild={s.saved_jobs.some((j) => j.id === open.saved_job_id)}
            onRebuild={() => build.run(open.saved_job_id)} />
        )}
        {!open && (
          <section className="card">
            <h2>{job ? 'No CV for this job yet' : 'No base CV yet'}</h2>
            <p className="sub">Build one above: 1 AI action, about 20 seconds.</p>
            <ShowMore label={`What a UK CV looks like (${s.content.cv_rules.length})`}>
              <ul className="dots small">{s.content.cv_rules.map((r) => <li key={r}>{r}</li>)}</ul>
            </ShowMore>
          </section>
        )}
      </div>

      {s.cv_versions.length > 0 && (
        <section className="card section">
          <h3>Your CV versions</h3>
          <div className="list" style={{ marginTop: 10 }}>
            {s.cv_versions.map((c) => (
              <div key={c.id} className={`entry resume-version ${open?.id === c.id ? 'current' : ''}`}>
                <div className="who">
                  <button className="linkish" aria-current={open?.id === c.id ? 'true' : undefined} onClick={() => show(c.id, c.saved_job_id || BASE)}>{c.name}</button>
                  {c.format_version !== 2 && <span className="chip muted" style={{ marginLeft: 8 }}>Old format</span>}
                  {s.applications.some((a) => a.cv_version_id === c.id) && <span className="chip good" style={{ marginLeft: 8 }}>Sent</span>}
                  {c.format_version === 2 && <div className="small muted">{plural(c.pages || 0, 'page')}{c.edited_at ? ', edited' : ''}</div>}
                </div>
                <div className="acts"><button className="icon-btn" aria-label={`Delete ${c.name}`} onClick={() => removeVersion(c)}><Trash2 size={15} /></button></div>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  )
}
