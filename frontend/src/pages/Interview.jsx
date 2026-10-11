import { useState } from 'react'
import { BriefcaseBusiness, FileText, MessagesSquare, PhoneCall } from 'lucide-react'
import { post } from '../api'
import { ErrorRetry, Meter, PageHead, useAction } from '../ui'
import VoiceAgent from '../VoiceAgent'
import { AddJob, JobPicker } from '../components/Jobs'

const TABS = [['sessions', 'Practice sessions'], ['stories', 'STAR stories'], ['tone', 'UK tone decoder']]
const SCORE_LABELS = { structure: 'Structure', clarity: 'Clarity', evidence: 'Evidence', uk_tone: 'UK tone' }

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

function Sessions({ s, focus, refresh, session }) {
  const [jobId, setJobId] = useState(focus.jobId || '')
  const [type, setType] = useState(SESSIONS[1])
  const [adding, setAdding] = useState(false)
  const fb = useAction(async (transcript) => {
    const r = await post('/api/ai/interview-feedback', { transcript, job_id: jobId || null, interview_type: type.label })
    refresh()
    return r
  })
  const job = s.saved_jobs.find((j) => j.id === jobId)
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
          intro={job ? `${type.label}: ${job.title} at ${job.company}` : `${type.label}: general practice`}
          dynamicVariables={{ candidate_name: s.profile.first_name || 'there', ...about,
            interview_type: type.label.toLowerCase(), interview_brief: type.brief, opening_question: type.opening, cv_summary: cvSummary }}
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
              {d.strengths.length > 0 && <div><h3>What worked</h3><ul className="dots small">{d.strengths.map((x) => <li key={x}>{x}</li>)}</ul></div>}
              <div><h3>Change next time</h3><ul className="dots small">{d.fixes.map((x) => <li key={x}>{x}</li>)}</ul></div>
              {d.rewrite.better_answer && <div><h3>A stronger answer</h3><p className="small muted">{d.rewrite.question}</p><p className="draft" style={{ marginTop: 6 }}>{d.rewrite.better_answer}</p></div>}
              {d.uk_tone_notes.length > 0 && <div><h3>UK tone</h3><ul className="dots small">{d.uk_tone_notes.map((x) => <li key={x}>{x}</li>)}</ul></div>}
              <p className="small muted">Saved to your Journal.</p>
            </div>
          )}
        </section>
      </div>
    </>
  )
}

function Stories({ s, refresh, notify, go }) {
  const [evId, setEvId] = useState(s.achievements[0]?.id || '')
  const make = useAction(async (id) => { const r = await post('/api/ai/star', { achievement_id: id }); await refresh(); notify('Story added'); return r })
  const tone = { strong: 'good', 'needs a number': 'warn', 'needs detail': 'bad' }
  return (
    <>
      <section className="card" style={{ marginBottom: 16 }}>
        <h2>Turn an achievement into a story</h2>
        <p className="sub">UK competency interviews expect STAR answers: situation, task, action, result. Aim for 6 to 8 stories.</p>
        {s.achievements.length === 0 ? (
          <p className="small">Your profile has no achievements yet. <button className="linkish" onClick={() => go('profile')}>Build your profile</button> first.</p>
        ) : (
          <div className="row">
            <select value={evId} onChange={(e) => setEvId(e.target.value)} aria-label="Achievement">
              {s.achievements.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
            </select>
            <button className="btn" disabled={make.loading} onClick={() => make.run(evId)}>{make.loading ? 'Writing' : 'Write STAR story'}</button>
          </div>
        )}
        <ErrorRetry error={make.error} onRetry={make.retry} />
        {make.result?.tip && <p className="small" style={{ marginTop: 8 }}>Tip: {make.result.tip}</p>}
      </section>
      {s.stories.length === 0 && <p className="muted">No stories yet. Write one from an achievement above.</p>}
      <div className="grid cols-2">
        {s.stories.map((st) => (
          <article key={st.id} className="card stack">
            <div className="row"><h3 style={{ flex: 1 }}>{st.title}</h3><span className={`chip ${tone[st.strength] || ''}`}>{st.strength}</span></div>
            <span className="small muted">{st.competency}</span>
            <div className="star">
              <b>S</b><span>{st.situation}</span>
              <b>T</b><span>{st.task}</span>
              <b>A</b><span>{st.action}</span>
              <b>R</b><span>{st.result}</span>
            </div>
          </article>
        ))}
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
  const active = TABS.find(([k]) => k === tab) ? tab : 'sessions'
  return (
    <>
      <PageHead title="Interview coach" lede="Practise out loud with a voice interviewer, then get scored feedback. Pick the kind of interview you want to rehearse." />
      <div className="tabs" role="tablist">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={active === k} className={`tab ${active === k ? 'active' : ''}`} onClick={() => go('interview', k === 'sessions' ? null : k, focus)}>{label}</button>
        ))}
      </div>
      {active === 'sessions' && <Sessions s={s} focus={focus} refresh={refresh} session={session} />}
      {active === 'stories' && <Stories s={s} refresh={refresh} notify={notify} go={go} />}
      {active === 'tone' && <Tone s={s} />}
    </>
  )
}
