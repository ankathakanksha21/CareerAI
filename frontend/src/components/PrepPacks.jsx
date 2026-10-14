import { useState } from 'react'
import { ClipboardList } from 'lucide-react'
import { fmtDate } from '../ui'
import { packFor, targetFor } from '../prep'
import { AddJob, JobPicker } from './Jobs'
import CompanyConfirm from './CompanyConfirm'
import PrepPack from './PrepPack'

// The Prep packs tab: the user's packs, starting a new one, and the open pack
export default function PrepPacks({ s, focus, go, refresh, notify }) {
  const start = { jobId: focus.prepJobId, appId: focus.prepAppId }
  const [view, setView] = useState(() => {
    if (focus.packId) return { packId: focus.packId }
    if (!start.jobId && !start.appId) return {}
    const existing = packFor(s, start)
    return existing ? { packId: existing.id } : { target: targetFor(s, start) }
  })
  const [jobId, setJobId] = useState(s.saved_jobs[0]?.id || '')
  const [adding, setAdding] = useState(false)
  const prepare = (id) => {
    const existing = packFor(s, { jobId: id })
    setView(existing ? { packId: existing.id } : { target: targetFor(s, { jobId: id }) })
  }

  if (view.packId) return <PrepPack key={view.packId} id={view.packId} s={s} go={go} refresh={refresh} notify={notify} onBack={() => setView({})} />
  if (view.target) {
    return <CompanyConfirm target={view.target} onCancel={() => setView({})}
      onBuilt={async (pack) => { await refresh(); setView({ packId: pack.id }) }} />
  }
  return (
    <div className="stack">
      <section className="card">
        <h2>Prepare for an interview</h2>
        <p className="sub">One page to prepare from: who the company is, with a source for every line, the questions you are likely to be asked matched to your stories, and good questions to ask back.</p>
        {s.saved_jobs.length > 0 && (
          <div className="row">
            <JobPicker jobs={s.saved_jobs} value={jobId} onChange={setJobId} />
            <button className="btn" disabled={!jobId} onClick={() => prepare(jobId)}>Prepare</button>
            <button className="linkish small" onClick={() => setAdding(!adding)}>{adding ? 'Cancel' : 'Add a job'}</button>
          </div>
        )}
        {s.saved_jobs.length === 0 && !adding && (
          <div className="row"><span className="small">Save the job you are interviewing for first.</span><button className="btn" onClick={() => setAdding(true)}>Add a job</button></div>
        )}
        {adding && <div style={{ marginTop: 14 }}><AddJob onCancel={() => setAdding(false)} onAdded={async (j) => { await refresh(); setAdding(false); setJobId(j.id); notify('Job saved') }} /></div>}
      </section>

      {s.prep_packs.length === 0 ? (
        <p className="muted">No prep packs yet. When you have an interview, prepare for it here or from the application.</p>
      ) : (
        <section className="card">
          <h2>Your packs</h2>
          <div className="list" style={{ marginTop: 10 }}>
            {s.prep_packs.map((p) => (
              <div key={p.id} className="row">
                <ClipboardList size={16} />
                <button className="linkish" style={{ flex: 1, textAlign: 'left' }} onClick={() => setView({ packId: p.id })}>{p.role} at {p.company}</button>
                <span className="small muted">Updated {fmtDate(p.updated_at, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
