import { useState } from 'react'
import { del, post } from '../api'
import { Empty, ErrorRetry, PageHead, useAction } from '../ui'
import { AddJob, JobPicker } from '../components/Jobs'

export default function Resume({ s, focus, refresh, go, notify }) {
  const [jobId, setJobId] = useState(focus.jobId || s.saved_jobs[0]?.id || '')
  const [adding, setAdding] = useState(false)
  const [openId, setOpenId] = useState(null) // which saved CV version is on screen
  const [source, setSource] = useState('Company site')
  const [postedOn, setPostedOn] = useState('')
  const job = s.saved_jobs.find((j) => j.id === jobId) || s.saved_jobs[0]
  const tailor = useAction(async (id) => {
    const cv = await post('/api/ai/tailor', { job_id: id })
    await refresh()
    setOpenId(cv.id)
  })
  const log = useAction(async (cv) => {
    await post('/api/applications', { company: job.company, role: job.title, saved_job_id: job.id, cv_version_id: cv.id,
      role_family_id: job.role_family_id, source, posted_on: postedOn || null })
    await refresh()
    notify(`Added to Applications with CV "${cv.name}"`)
  })

  const onAdded = async (j) => { await refresh(); setJobId(j.id); setOpenId(null); setAdding(false); notify('Job saved') }
  const removeJob = async () => {
    if (!window.confirm(`Remove ${job.title}, ${job.company}? CVs already tailored for it are kept.`)) return
    await del(`/api/jobs/${job.id}`)
    await refresh()
    setJobId('')
    setOpenId(null)
  }

  const versions = job ? s.cv_versions.filter((c) => c.saved_job_id === job.id) : []
  const cv = s.cv_versions.find((c) => c.id === openId) || versions[0]
  const d = cv?.content

  if (s.saved_jobs.length === 0 || adding) {
    return (
      <>
        <PageHead title="Resume" lede="A UK-standard CV and cover letter for each job, built from your profile." />
        {adding || s.saved_jobs.length > 0
          ? <AddJob onAdded={onAdded} onCancel={s.saved_jobs.length > 0 ? () => setAdding(false) : null} />
          : <Empty title="Add a job you want to apply for" body="Paste the job advert. Your CV and cover letter are tailored to its exact wording." action="Add a job" onAction={() => setAdding(true)} />}
      </>
    )
  }

  return (
    <>
      <PageHead title="Resume" lede="A UK-standard CV and cover letter for each job, built from your profile. Every tailored CV is saved as a version, so the tracker can tell which one gets replies.">
        <button className="btn ghost" onClick={() => setAdding(true)}>Add a job</button>
      </PageHead>

      <div className="grid split">
        <div className="stack">
          <section className="card">
            <h2>Tailor for one job</h2>
            <p className="sub">Picks the most relevant achievements from your profile and rewrites them in this job's language.</p>
            <div className="row">
              <JobPicker jobs={s.saved_jobs} value={job.id} onChange={(v) => { setJobId(v); setOpenId(null) }} />
              <button className="btn" disabled={tailor.loading || s.achievements.length === 0} onClick={() => tailor.run(job.id)}>{tailor.loading ? 'Tailoring' : 'Tailor CV and cover letter'}</button>
              <button className="linkish small" onClick={removeJob}>Remove job</button>
            </div>
            {job.summary && <p className="small muted" style={{ marginTop: 10 }}>{job.summary}</p>}
            {s.achievements.length === 0 && <p className="small" style={{ marginTop: 10 }}>Your profile has no achievements yet. <button className="linkish" onClick={() => go('profile')}>Build your profile</button> first.</p>}
            <ErrorRetry error={tailor.error} onRetry={tailor.retry} />
          </section>

          {d && (
            <section className="cv-sheet">
              <div className="row"><h2 style={{ fontSize: 20 }}>{s.profile.full_name}</h2><span className="spacer" /><span className="chip">{cv.name}</span></div>
              <h3>Profile</h3>
              <p>{d.profile}</p>
              <h3>Experience, selected for this role</h3>
              <ul>{d.bullets.map((b, i) => <li key={i}>{b.text}</li>)}</ul>
              {d.keywords.length > 0 && <><h3>Keywords covered</h3><div className="row">{d.keywords.map((k) => <span key={k} className="chip good">{k}</span>)}</div></>}
            </section>
          )}
        </div>

        <div className="stack">
          {d ? (
            <>
              <section className="card letter">
                <h2>Cover letter</h2>
                <p className="sub">UK structure: why them, why you, what you will deliver.</p>
                <p className="part">Why {job.company}</p><p>{d.cover_letter.why_them}</p>
                <p className="part">Why me</p><p>{d.cover_letter.why_you}</p>
                <p className="part">What I will deliver</p><p>{d.cover_letter.what_you_deliver}</p>
              </section>
              {d.gaps.length > 0 && (
                <section className="card">
                  <h3>Be ready to talk about</h3>
                  <ul className="dots small">{d.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
                </section>
              )}
              <section className="card">
                <h3>Applied with this CV?</h3>
                <div className="row" style={{ marginTop: 10, alignItems: 'end' }}>
                  <label className="field">Where you applied<select value={source} onChange={(e) => setSource(e.target.value)}>{s.options.sources.map((x) => <option key={x}>{x}</option>)}</select></label>
                  <label className="field">Date posted <span className="muted" style={{ fontWeight: 400 }}>(optional)</span><input type="date" value={postedOn} onChange={(e) => setPostedOn(e.target.value)} /></label>
                </div>
                <div className="row" style={{ marginTop: 12 }}><button className="btn" disabled={log.loading} onClick={() => log.run(cv)}>Add to Applications with this CV</button></div>
                <ErrorRetry error={log.error} />
              </section>
            </>
          ) : (
            <section className="card">
              <h2>UK CV rules</h2>
              <ul className="dots small" style={{ marginTop: 10 }}>{s.content.cv_rules.map((r) => <li key={r}>{r}</li>)}</ul>
            </section>
          )}
          {s.cv_versions.length > 0 && (
            <section className="card">
              <h3>Your CV versions</h3>
              <div className="row" style={{ marginTop: 10 }}>
                {s.cv_versions.map((c) => (
                  <button key={c.id} className={`chip chip-btn ${cv?.id === c.id ? 'good' : ''}`} onClick={() => { if (c.saved_job_id) setJobId(c.saved_job_id); setOpenId(c.id) }}>{c.name}</button>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </>
  )
}
