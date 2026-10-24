import { useEffect, useId, useState } from 'react'
import { BriefcaseBusiness, Check, ChevronDown, ClipboardList, Clock, FileText, Lightbulb, MessagesSquare, Pencil, PhoneCall, Sparkles, Trash2 } from 'lucide-react'
import { api, del, patch, post } from '../api'
import { ErrorRetry, InfoTip, Meter, PageHead, ShowMore, attempt, useAction } from '../ui'
import VoiceAgent from '../VoiceAgent'
import { AddJob, JobPicker } from '../components/Jobs'
import PrepPacks from '../components/PrepPacks'
import StoryCoverage from '../components/StoryCoverage'
import { packFor } from '../prep'

const TABS = [['sessions', 'Practice sessions'], ['stories', 'STAR stories'], ['tone', 'Tone decoder'], ['prep', 'Prep packs']]
const SCORE_LABELS = { structure: 'Structure', clarity: 'Clarity', evidence: 'Evidence', uk_tone: 'UK tone' }
const PACK_QUESTIONS = new Set(['job', 'behavioural']) // sessions that ask from a prep pack's likely questions

// Each session type changes what the voice interviewer asks (sent as dynamic variables)
const SESSIONS = [
  { key: 'cv', icon: FileText, label: 'CV walkthrough', desc: 'Walk through your CV, then two experiences in depth.',
    brief: 'Ask the candidate to walk through their CV briefly, then pick two experiences from the CV summary and probe what they personally did, how, and the result.',
    opening: 'Could you walk me through your CV, starting with your most recent role?' },
  { key: 'job', icon: BriefcaseBusiness, label: 'Job-specific interview', desc: 'Questions built from the job you pick.',
    brief: 'Ask one motivation question about this role, then one competency question and one technical or case question tied to the role summary.',
    opening: 'To start, could you tell me a bit about yourself and why this role?' },
  { key: 'hr', icon: PhoneCall, label: 'HR screening call', desc: "A recruiter's first call: motivation, salary, right to work, availability.",
    brief: 'Act as an in-house recruiter. Ask why this company, their salary expectations, their right to work in the UK including whether they will need visa sponsorship, and their notice period or start date.',
    opening: 'Thanks for making time today. What attracted you to this role?' },
  { key: 'behavioural', icon: MessagesSquare, label: 'Behavioural round', desc: 'STAR questions on teamwork, a setback and influencing.',
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
      {/* every session is the same length, so it is said once for all four */}
      <div className="interview-length"><span className="chip muted"><Clock size={13} aria-hidden="true" />3 questions, about 5 minutes</span></div>
      <div className="grid cols-4">
        {SESSIONS.map((t) => (
          <button key={t.key} className={`card session ${type.key === t.key ? 'selected' : ''}`} onClick={() => { setType(t); fb.setResult(null) }} aria-pressed={type.key === t.key}>
            <span className="icon-box"><t.icon size={19} /></span>
            <h3>{t.label}</h3>
            <p>{t.desc}</p>
          </button>
        ))}
      </div>

      <div className="grid cols-2 section">
        <VoiceAgent
          key={`${type.key}-${jobId}`}
          agent="interviewer"
          agentLabel="Interviewer"
          userId={session.user.id}
          intro={job ? (
            <>
              {type.label}: {job.title} at {job.company}
              {pack && <> <span className="chip muted interview-pack-chip"><ClipboardList size={13} aria-hidden="true" />Using prep pack</span></>}
            </>
          ) : `${type.label}: general practice`}
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
          {!d && !fb.loading && !fb.error && (
            // the four scores by name only: no meter and no number, so nothing reads as a score of zero
            <div className="stack" style={{ gap: 10, marginTop: 10 }}>
              <ul className="plain stack" style={{ gap: 8 }}>
                {Object.values(SCORE_LABELS).map((l) => <li key={l} className="score"><span>{l}</span><span className="interview-score-blank" aria-hidden="true" /></li>)}
              </ul>
              <p className="muted">Finish a session for scores. Each one is saved to your Journal.</p>
            </div>
          )}
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
                  <summary className="linkish small">Transcript</summary>
                  <pre className="draft small" style={{ marginTop: 8, fontFamily: 'inherit' }}>{heard}</pre>
                </details>
              )}
              <p className="small muted interview-saved"><Check size={14} aria-hidden="true" />Saved to Journal with transcript.</p>
            </div>
          )}
        </section>
      </div>
    </>
  )
}

const BANK = 8 // stories a candidate needs; "Build my story bank" fills up to this
const AIM = 6 // the fewest stories to aim for
const STORY_PARTS = [['situation', 'Situation'], ['task', 'Task'], ['action', 'Action'], ['result', 'Result']]
const STRENGTH_TONE = { strong: 'good', 'needs a number': 'warn', 'needs detail': 'bad' }
const MAX_COMPETENCIES = 3

// One STAR story, read or edited in place
function Story({ st, s, refresh, notify }) {
  const [form, setForm] = useState(null) // the fields being edited, or nothing
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [full, setFull] = useState(false) // Situation, Task and Action shown as well as the Result
  const partsId = useId()
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
          <legend>Competencies <span className="small muted" style={{ fontWeight: 400 }}>(up to {MAX_COMPETENCIES})</span></legend>
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
      {/* the Result shows; Situation, Task and Action open with Show full story */}
      <div className="star" id={partsId}>
        {(full ? STORY_PARTS : STORY_PARTS.filter(([key]) => key === 'result')).map(([key, label]) => <span key={key} style={{ display: 'contents' }}><b>{label[0]}</b><span>{st[key]}</span></span>)}
      </div>
      <div className="row">
        <button type="button" className="linkish small showmore-btn" aria-expanded={full} aria-controls={partsId} onClick={() => setFull(!full)}>
          {full ? 'Hide full story' : 'Show full story'}<ChevronDown size={15} aria-hidden="true" className={full ? 'flip' : ''} />
        </button>
        <span className="spacer" />
        <button type="button" className="icon-btn calm" aria-label="Edit story" title="Edit story" onClick={() => setForm({ title: st.title, competencies: st.competencies, situation: st.situation, task: st.task, action: st.action, result: st.result })}><Pencil size={16} aria-hidden="true" /></button>
        <button type="button" className="icon-btn" aria-label="Delete story" title="Delete story" onClick={remove}><Trash2 size={16} aria-hidden="true" /></button>
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
        <h2>Stories from your achievements</h2>
        <p className="sub">UK competency interviews expect STAR answers. <InfoTip label="What STAR stands for">Situation, task, action, result.</InfoTip></p>
        {/* the bank's size against the 6 to 8 to aim for; the bar stops at full when there are more */}
        <div className="interview-bank">
          <span className="small">{s.stories.length === 1 ? '1 story' : `${s.stories.length} stories`}, aim for {AIM} to {BANK}</span>
          <div className="meter interview-bank-meter" aria-hidden="true">
            <span style={{ width: `${Math.min(s.stories.length, BANK) / BANK * 100}%` }} />
            <i className="interview-bank-mark" style={{ left: `${AIM / BANK * 100}%` }} />
          </div>
        </div>
        {s.achievements.length === 0 ? (
          <p className="small">No achievements yet. <button className="linkish" onClick={() => go('profile')}>Build your profile</button> first.</p>
        ) : (
          <div className="stack">
            {room > 0 && (
              <div className="row">
                <button className="btn" disabled={bank.loading || make.loading} onClick={() => bank.run()}>{bank.loading ? 'Writing your stories' : 'Build my story bank'}</button>
                {bank.loading ? <span className="small muted">About 30 seconds.</span> : (
                  <span className="small muted interview-inline">
                    Writes {room === 1 ? 'a story' : `${room} stories`}
                    <InfoTip label="Which achievements">From your strongest achievements that have no story yet.</InfoTip>
                  </span>
                )}
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
        {make.result?.tip && <p className="small interview-tip"><Lightbulb size={15} aria-hidden="true" /><span><span className="sr-only">Tip: </span>{make.result.tip}</span></p>}
      </section>
      <StoryCoverage s={s} refresh={refresh} notify={notify} />
      {s.stories.length === 0 && <p className="muted">No stories yet.</p>}
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
  const phraseId = useId()
  const run = (t, m) => { setMode(m); setText(t); tone.run(t, m) }
  const d = tone.result
  return (
    <div className="grid cols-2">
      <div className="stack">
        <section className="card">
          <h2>Decode or rewrite</h2>
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. I am the best candidate for this role." aria-label="Phrase or sentence" style={{ marginTop: 10 }} />
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
          <ShowMore label={`UK communication norms (${s.content.tone_norms.length})`} heading="h3" buttonClassName="interview-norms-btn">
            <ul className="dots small">{s.content.tone_norms.map((n) => <li key={n}>{n}</li>)}</ul>
          </ShowMore>
        </section>
      </div>
      <section className="card">
        <h2>Phrases you will hear</h2>
        <div className="list" style={{ marginTop: 10 }}>
          {s.content.tone_phrases.map((p, i) => (
            <div key={p.phrase} className="phrase">
              <div><div className="strong" id={`${phraseId}-${i}`}>"{p.phrase}"</div><div className="small muted">{p.meaning}</div></div>
              <button type="button" className="icon-btn calm" aria-label="Decode with AI" title="Decode with AI" aria-describedby={`${phraseId}-${i}`} disabled={tone.loading} onClick={() => run(p.phrase, 'decode')}>
                <Sparkles size={16} aria-hidden="true" />
              </button>
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
      <PageHead title="Interview" lede="Practise out loud with a voice interviewer and get scored feedback." />
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
