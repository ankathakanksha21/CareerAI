import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { del, post } from '../api'
import { ErrorRetry, PageHead, attempt, plural, useAction } from '../ui'
import { AddJob } from '../components/Jobs'
import ContactForm from '../components/ContactForm'
import CvEditor from '../components/CvEditor'
import OldCv from '../components/OldCv'
import { unlinked } from '../cv'

const BASE = '' // the picker's first choice: a CV for no particular job

export default function Resume({ s, focus, refresh, go, notify }) {
  const recent = s.cv_versions[0]
  const [target, setTarget] = useState(focus.jobId || (recent ? recent.saved_job_id || BASE : s.saved_jobs[0]?.id || BASE))
  const [openId, setOpenId] = useState(null)    // a version the user picked or just made; otherwise the newest for the target
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
      <PageHead title="Resume" lede="A complete two-page UK CV built from your profile, for one job or for none. Edit it here, download it as Word or PDF, and every version you send is kept so the tracker can tell which one gets replies.">
        {!adding && <button className="btn ghost" onClick={() => setAdding(true)}>Add a job</button>}
      </PageHead>
      {adding && <div style={{ marginBottom: 16 }}><AddJob onAdded={onAdded} onCancel={() => setAdding(false)} /></div>}

      <section className="card">
        <h2>Build a CV</h2>
        <p className="sub">Your employers, dates, courses and grades are copied from your profile. The AI writes the profile paragraph, picks and rewords your achievements, and orders your skills.</p>
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
        {job?.summary && <p className="small muted" style={{ marginTop: 10 }}>{job.summary}</p>}
        {!job && <p className="small muted" style={{ marginTop: 10 }}>A base CV uses your whole profile and has no cover letter. To tailor one, pick a saved job, <button className="linkish" onClick={() => setAdding(true)}>paste an advert</button>{s.config.jobs && <> or <button className="linkish" onClick={() => go('jobs')}>choose from matching jobs</button></>}.</p>}
        {s.achievements.length === 0 && <p className="small" style={{ marginTop: 10 }}>Your profile has no achievements yet. <button className="linkish" onClick={() => go('profile')}>Build your profile</button> first.</p>}
        {loose > 0 && <p className="small muted" style={{ marginTop: 10 }}>{plural(loose, 'achievement')} {loose === 1 ? 'is' : 'are'} not linked to a job or a course, so {loose === 1 ? 'it prints' : 'they print'} under Projects. <button className="linkish" onClick={() => go('profile')}>Link {loose === 1 ? 'it' : 'them'} on your Profile</button> to show {loose === 1 ? 'it' : 'them'} under the right employer.</p>}
        <ErrorRetry error={build.error} onRetry={build.retry} />
      </section>

      {asking && (
        <section className="card editing section">
          <h2>Contact details for your CV</h2>
          <p className="sub">Asked once. They are printed at the top of every CV, are never sent to the AI, and can be changed on your Profile.</p>
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
            <h2>{job ? `No CV for ${job.title}, ${job.company} yet` : 'No base CV yet'}</h2>
            <p className="sub">Build one above. It takes one AI action and about 20 seconds.</p>
            <ul className="dots small">{s.content.cv_rules.map((r) => <li key={r}>{r}</li>)}</ul>
          </section>
        )}
      </div>

      {s.cv_versions.length > 0 && (
        <section className="card section">
          <h3>Your CV versions</h3>
          <div className="list" style={{ marginTop: 10 }}>
            {s.cv_versions.map((c) => (
              <div key={c.id} className="entry">
                <div className="who">
                  <button className="linkish" onClick={() => show(c.id, c.saved_job_id || BASE)}>{c.name}</button>
                  {open?.id === c.id && <span className="chip good" style={{ marginLeft: 8 }}>On screen</span>}
                  <div className="small muted">
                    {c.format_version === 2 ? `${plural(c.pages || 0, 'page')}${c.edited_at ? ', edited' : ''}` : 'An earlier, shorter CV'}
                    {s.applications.some((a) => a.cv_version_id === c.id) && ', sent with an application'}
                  </div>
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
