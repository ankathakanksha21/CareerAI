import { useEffect, useState } from 'react'
import { BriefcaseBusiness, FileText, MessagesSquare, PhoneCall } from 'lucide-react'
import { api, del, patch, post } from '../api'
import { ErrorRetry, Meter, PageHead, attempt, useAction } from '../ui'
import VoiceAgent from '../VoiceAgent'
import { AddJob, JobPicker } from '../components/Jobs'
import PrepPacks from '../components/PrepPacks'
import StoryCoverage from '../components/StoryCoverage'
import { packFor } from '../prep'

const TABS = [['sessions', 'Practice sessions'], ['stories', 'STAR stories'], ['tone', 'UK tone decoder'], ['prep', 'Prep packs']]
const SCORE_LABELS = { structure: 'Structure', clarity: 'Clarity', evidence: 'Evidence', uk_tone: 'UK tone' }
const PACK_QUESTIONS = new Set(['job', 'behavioural']) // sessions that ask from a prep pack's likely questions

// Each session type changes what the voice interviewer asks (sent as dynamic variables)
const SESSIONS = [
  { key: 'cv', icon: FileText, label: 'CV walkthrough', desc: 'Talk an interviewer through your CV. They pick two experiences and dig into what you did.',
    brief: 'Ask the candidate to walk through their CV briefly, then pick two experiences from the CV summary and probe what they personally did, how, and the result.',
    opening: 'Could you walk me through your CV, starting with your most recent role?' },
  { key: 'job', icon: BriefcaseBusiness, label: 'Job-specific interview', desc: 'Questions for the exact role you pick, built from its job description.',
    brief: 'Ask one motivation question about this role, then one competency question and one technical or case question tied to the role summary.',
    opening: 'To start, could you tell me a bit about yourself and why this role?' },
  { key: 'hr', icon: PhoneCall, label: 'HR screening call', desc: 'The first call with a recruiter: motivation, salary, right to work and availability.',
    brief: 'Act as an in-house recruiter. Ask why this company, their salary expectations, their right to work in the UK including whether they will need visa sponsorship, and their notice period or start date.',
    opening: 'Thanks for making time today. What attracted you to this role?' },
  { key: 'behavioural', icon: MessagesSquare, label: 'Behavioural round', desc: 'Three competency questions scored on STAR: teamwork, a setback, influencing.',
    brief: 'Ask three competency questions one at a time: working in a team under pressure, a time something went wrong and what they learned, and a time they influenced someone without authority. Expect STAR answers.',
    opening: 'Let us start with teamwork. Tell me about a time you worked in a team under pressure.' },
]

// A feedback comment with the user's own words it is about, when the transcript has them
function Points({ items }) {
  return (
    <ul className="dots small">
      {items.map((x) => (
        <li key={x.point}>
          {x.point}
          {x.you_said && <span className="said" style={{ display: 'block' }}>You said: "{x.you_said}"</span>}
        </li>
      ))}
    </ul>
  )
}

function Sessions({ s, focus, go, refresh, session }) {
  const [jobId, setJobId] = useState(focus.jobId || '')
  const [type, setType] = useState(SESSIONS[1])
  const [adding, setAdding] = useState(false)
  const [heard, setHeard] = useState('') // the transcript being scored, kept so the user can read it back
  const fb = useAction(async (transcript) => {
    setHeard(transcript)
    const r = await post('/api/ai/interview-feedback', { transcript, job_id: jobId || null, interview_type: type.label })
    refresh()
    return r
  })
  const job = s.saved_jobs.find((j) => j.id === jobId)
  const packId = packFor(s, { jobId })?.id
  const [prepped, setPrepped] = useState(null) // what the interviewer is told from the job's prep pack
  useEffect(() => {
    if (packId) api(`/api/prep/${packId}`).then((p) => setPrepped({ id: p.id, ...p.interviewer })).catch(() => {}) // without it, practice is as before
  }, [packId])
  const pack = prepped && prepped.id === packId ? prepped : null
  const d = fb.result
  const target = s.role_families.find((f) => f.targeted)
  // with no job picked, the interviewer practises for the user's first target role
  const about = job
    ? { role: job.title, company: job.company, job_summary: job.summary || job.description.slice(0, 400) }
    : { role: target?.name || 'graduate role', company: 'a UK employer', job_summary: 'General practice, no specific job.' }
  const cvSummary = s.achievements.slice(0, 5).map((e) => e.uk_version).join(' ').slice(0, 900) || 'Not provided.'

  return (
    <>
      <div className="row" style={{ marginBottom: 14 }}>
        <span className="strong">Practising for</span>
        <JobPicker jobs={s.saved_jobs} value={jobId} allowNone onChange={(v) => { setJobId(v); fb.setResult(null) }} />
        <button className="linkish small" onClick={() => setAdding(!adding)}>{adding ? 'Cancel' : 'Add a job'}</button>
        {s.config.prep && (
          <button className="btn ghost small" disabled={!jobId} title={jobId ? undefined : 'Pick a job first'} onClick={() => go('interview', 'prep', { prepJobId: jobId })}>
            {packFor(s, { jobId }) ? 'Open prep pack' : 'Prepare'}
          </button>
        )}
      </div>
      {adding && <div style={{ marginBottom: 16 }}><AddJob onCancel={() => setAdding(false)} onAdded={async (j) => { await refresh(); setJobId(j.id); setAdding(false) }} /></div>}
      <div className="grid cols-4">
        {SESSIONS.map((t) => (
          <button key={t.key} className={`card session ${type.key === t.key ? 'selected' : ''}`} onClick={() => { setType(t); fb.setResult(null) }} aria-pressed={type.key === t.key}>
            <span className="icon-box"><t.icon size={19} /></span>
            <h3>{t.label}</h3>
            <p>{t.desc}</p>
            <span className="meta">3 questions, about 5 minutes</span>
          </button>
        ))}
      </div>

      <div className="grid cols-2 section">
        <VoiceAgent
          key={`${type.key}-${jobId}`}
          agent="interviewer"
          agentLabel="Interviewer"
          userId={session.user.id}
          intro={job ? `${type.label}: ${job.title} at ${job.company}${pack ? '. Using your prep pack' : ''}` : `${type.label}: general practice`}
          dynamicVariables={{ candidate_name: s.profile.first_name || 'there', ...about,
            interview_type: type.label.toLowerCase(), interview_brief: type.brief, opening_question: type.opening, cv_summary: cvSummary,
            // the company summary helps every session; the likely questions suit the job and behavioural rounds
            company_brief: pack?.company_brief || 'Not provided.',
            likely_questions: (pack && PACK_QUESTIONS.has(type.key) && pack.likely_questions) || 'None given.' }}
          onDone={(t) => fb.run(t)}
        />

        <section className="card">
          <h2>Feedback</h2>
          {fb.loading && <p className="muted" style={{ marginTop: 8 }}>Scoring your answers</p>}
          <ErrorRetry error={fb.error} onRetry={fb.retry} />
          {!d && !fb.loading && !fb.error && <p className="muted" style={{ marginTop: 8 }}>Finish a session to see scores for structure, clarity, evidence and UK tone. Every session is saved to your Journal.</p>}
          {d && (
            <div className="stack" style={{ gap: 16, marginTop: 10 }}>
              <p>{d.summary}</p>
              <div className="stack" style={{ gap: 8 }}>
                {Object.entries(d.scores).map(([k, v]) => (
                  <div key={k} className="score"><span>{SCORE_LABELS[k] || k}</span><Meter value={v * 20} /><b>{v}/5</b></div>
                ))}
              </div>
              {d.strengths.length > 0 && <div><h3>What worked</h3><Points items={d.strengths} /></div>}
              <div><h3>Change next time</h3><Points items={d.fixes} /></div>
              {d.rewrite.better_answer && <div><h3>A stronger answer</h3><p className="small muted">{d.rewrite.question}</p><p className="draft" style={{ marginTop: 6 }}>{d.rewrite.better_answer}</p></div>}
              {d.uk_tone_notes.length > 0 && <div><h3>UK tone</h3><ul className="dots small">{d.uk_tone_notes.map((x) => <li key={x}>{x}</li>)}</ul></div>}
              {heard && (
                <details>
                  <summary className="linkish small">View full transcript</summary>
                  <pre className="draft small" style={{ marginTop: 8, fontFamily: 'inherit' }}>{heard}</pre>
                </details>
              )}
              <p className="small muted">Saved to your Journal, with the transcript.</p>
            </div>
          )}
        </section>
      </div>
    </>
  )
}

const BANK = 8 // stories a candidate needs; "Build my story bank" fills up to this
const STORY_PARTS = [['situation', 'Situation'], ['task', 'Task'], ['action', 'Action'], ['result', 'Result']]
const STRENGTH_TONE = { strong: 'good', 'needs a number': 'warn', 'needs detail': 'bad' }
const MAX_COMPETENCIES = 3

// One STAR story, read or edited in place
function Story({ st, s, refresh, notify }) {
  const [form, setForm] = useState(null) // the fields being edited, or nothing
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const save = async (ev) => {
    ev.preventDefault()
    if (!form.title.trim()) return setError('Give the story a title.')
    setBusy(true)
    setError(null)
    try {
      await patch(`/api/stories/${st.id}`, form)
      await refresh()
      setForm(null)
      notify('Story saved')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  const remove = async () => {
    if (!window.confirm('Delete this story? The achievement it came from is kept.')) return
    await attempt(notify)(async () => {
      await del(`/api/stories/${st.id}`)
      await refresh()
      notify('Story deleted')
    })
  }

  const label = Object.fromEntries(s.options.competencies)
  if (form) {
    return (
      <form className="card stack editing" onSubmit={save} noValidate>
        <label className="field">Title<input type="text" value={form.title} maxLength={200} onChange={set('title')} /></label>
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend>Competencies it shows <span className="small muted" style={{ fontWeight: 400 }}>(up to {MAX_COMPETENCIES})</span></legend>
          <div className="row" style={{ gap: 12 }}>
            {s.options.competencies.map(([key, label]) => {
              const on = form.competencies.includes(key)
              return (
                <label key={key} className="check">
                  <input type="checkbox" checked={on} disabled={!on && form.competencies.length >= MAX_COMPETENCIES}
                    onChange={() => setForm({ ...form, competencies: on ? form.competencies.filter((k) => k !== key) : [...form.competencies, key] })} />
                  {label}
                </label>
              )
            })}
          </div>
        </fieldset>
        {STORY_PARTS.map(([key, label]) => (
          <label key={key} className="field">{label}<textarea rows={key === 'action' ? 4 : 2} value={form[key]} maxLength={2000} onChange={set(key)} /></label>
        ))}
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn ghost small" onClick={() => setForm(null)}>Cancel</button>
          <button className="btn small" type="submit" disabled={busy}>{busy ? 'Saving' : 'Save'}</button>
        </div>
      </form>
    )
  }
  return (
    <article className="card stack">
      <div className="row"><h3 style={{ flex: 1 }}>{st.title}</h3><span className={`chip ${STRENGTH_TONE[st.strength] || ''}`}>{st.strength}</span></div>
      {st.competencies.length > 0 && (
        <div className="row" style={{ gap: 6 }}>{st.competencies.map((k) => <span key={k} className="chip">{label[k]}</span>)}</div>
      )}
      <div className="star">
        {STORY_PARTS.map(([key, label]) => <span key={key} style={{ display: 'contents' }}><b>{label[0]}</b><span>{st[key]}</span></span>)}
      </div>
      <div className="row">
        <button className="linkish small" onClick={() => setForm({ title: st.title, competencies: st.competencies, situation: st.situation, task: st.task, action: st.action, result: st.result })}>Edit</button>
        <button className="linkish small" onClick={remove}>Delete</button>
      </div>
    </article>
  )
}

function Stories({ s, refresh, notify, go }) {
  const [evId, setEvId] = useState(s.achievements[0]?.id || '')
  const make = useAction(async (id) => { const r = await post('/api/ai/star', { achievement_id: id }); await refresh(); notify('Story added'); return r })
  const bank = useAction(async () => {
    const r = await post('/api/ai/stories/bank')
    await refresh()
    notify(r.stories.length === 1 ? '1 story added' : `${r.stories.length} stories added`)
    return r
  })
  const told = new Set(s.stories.map((st) => st.achievement_id))
  const untold = s.achievements.filter((a) => !told.has(a.id)).length
  const room = Math.min(BANK - s.stories.length, untold) // how many the bank would write now
  return (
    <>
      <section className="card" style={{ marginBottom: 16 }}>
        <h2>Turn your achievements into stories</h2>
        <p className="sub">UK competency interviews expect STAR answers: situation, task, action, result. Aim for 6 to 8 stories.</p>
        {s.achievements.length === 0 ? (
          <p className="small">Your profile has no achievements yet. <button className="linkish" onClick={() => go('profile')}>Build your profile</button> first.</p>
        ) : (
          <div className="stack">
            {room > 0 && (
              <div className="row">
                <button className="btn" disabled={bank.loading || make.loading} onClick={() => bank.run()}>{bank.loading ? 'Writing your stories' : 'Build my story bank'}</button>
                <span className="small muted">
                  {bank.loading ? 'This takes about half a minute.' : `Writes ${room === 1 ? 'a story' : `${room} stories`} from your strongest achievements that have none.`}
                </span>
              </div>
            )}
            <div className="row">
              <select value={evId} onChange={(e) => setEvId(e.target.value)} aria-label="Achievement">
                {s.achievements.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
              </select>
              <button className={room > 0 ? 'btn ghost' : 'btn'} disabled={make.loading || bank.loading} onClick={() => make.run(evId)}>{make.loading ? 'Writing' : 'Write one story'}</button>
            </div>
          </div>
        )}
        <ErrorRetry error={bank.error} onRetry={bank.retry} />
        {bank.result?.notice && !bank.loading && <p className="small muted" role="status" style={{ marginTop: 8 }}>{bank.result.notice}</p>}
        <ErrorRetry error={make.error} onRetry={make.retry} />
        {make.result?.tip && <p className="small" style={{ marginTop: 8 }}>Tip: {make.result.tip}</p>}
      </section>
      <StoryCoverage s={s} refresh={refresh} notify={notify} />
      {s.stories.length === 0 && <p className="muted">No stories yet. Build your story bank above, or write one at a time.</p>}
      <div className="grid cols-2">
        {s.stories.map((st) => <Story key={st.id} st={st} s={s} refresh={refresh} notify={notify} />)}
      </div>
    </>
  )
}

function Tone({ s }) {
  const [text, setText] = useState('')
  const tone = useAction((t, mode) => post('/api/ai/tone', { text: t, mode }))
  const [mode, setMode] = useState(null)
  const run = (t, m) => { setMode(m); setText(t); tone.run(t, m) }
  const d = tone.result
  return (
    <div className="grid cols-2">
      <div className="stack">
        <section className="card">
          <h2>Decode or rewrite</h2>
          <p className="sub">Paste something an interviewer said, or a sentence of yours to make more British.</p>
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. I am the best candidate for this role." aria-label="Phrase or sentence" />
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn" disabled={tone.loading || !text.trim()} onClick={() => run(text, 'rewrite')}>Rewrite in UK tone</button>
            <button className="btn ghost" disabled={tone.loading || !text.trim()} onClick={() => run(text, 'decode')}>What do they mean?</button>
          </div>
          <ErrorRetry error={tone.error} onRetry={tone.retry} />
        </section>
        {d && !tone.loading && (
          <section className="card">
            <h3>{mode === 'decode' ? 'What it means' : 'UK version'}</h3>
            {mode === 'decode' ? (
              <div className="stack" style={{ marginTop: 8 }}>
                <p>{d.meaning}</p>
                <p className="small"><span className="strong">How to respond: </span>{d.how_to_respond}</p>
              </div>
            ) : (
              <div className="stack" style={{ marginTop: 8 }}>
                <p className="draft">{d.rewrite}</p>
                <ul className="dots small">{d.changes?.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
            )}
          </section>
        )}
        <section className="card">
          <h3>UK communication norms</h3>
          <ul className="dots small">{s.content.tone_norms.map((n) => <li key={n}>{n}</li>)}</ul>
        </section>
      </div>
      <section className="card">
        <h2>Phrases you will hear</h2>
        <p className="sub">British understatement, translated.</p>
        <div className="list">
          {s.content.tone_phrases.map((p) => (
            <div key={p.phrase} className="phrase">
              <div><div className="strong">"{p.phrase}"</div><div className="small muted">{p.meaning}</div></div>
              <button className="btn ghost small" disabled={tone.loading} onClick={() => run(p.phrase, 'decode')}>Decode</button>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

export default function Interview({ s, tab, go, focus, refresh, notify, session }) {
  const tabs = TABS.filter(([k]) => k !== 'prep' || s.config.prep) // prep packs need the research settings
  const active = tabs.find(([k]) => k === tab) ? tab : 'sessions'
  return (
    <>
      <PageHead title="Interview coach" lede="Practise out loud with a voice interviewer, then get scored feedback. Pick the kind of interview you want to rehearse." />
      <div className="tabs" role="tablist">
        {tabs.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={active === k} className={`tab ${active === k ? 'active' : ''}`} onClick={() => go('interview', k === 'sessions' ? null : k, focus)}>{label}</button>
        ))}
      </div>
      {active === 'sessions' && <Sessions s={s} focus={focus} go={go} refresh={refresh} session={session} />}
      {active === 'stories' && <Stories s={s} refresh={refresh} notify={notify} go={go} />}
      {active === 'tone' && <Tone s={s} />}
      {active === 'prep' && <PrepPacks key={JSON.stringify(focus)} s={s} focus={focus} go={go} refresh={refresh} notify={notify} />}
    </>
  )
}
