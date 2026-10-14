import { useEffect, useState } from 'react'
import { ArrowLeft, Mic, Printer, RefreshCw, Trash2 } from 'lucide-react'
import { api, del, patch, post } from '../api'
import { ErrorRetry, attempt, fmtDate, useAction } from '../ui'
import { INTERVIEW_TYPE_LABEL, QUESTION_KIND, SECTION_LABEL } from '../prep'

const host = (url) => { try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url } }
const longDate = (iso) => fmtDate(iso, { day: 'numeric', month: 'long', year: 'numeric' })
const MAX_TICKS = 3

// Where a line came from, as a link that opens the page it was read on
function Source({ f }) {
  return <a className="source" href={f.url} target="_blank" rel="noopener noreferrer">{f.kind === 'registry' ? 'Companies House' : host(f.url)}</a>
}

// One line of the brief, worded for its section, ending with its source
function Line({ f }) {
  if (f.section === 'news') {
    return <li><span className="muted">{f.published_on ? fmtDate(f.published_on, { day: 'numeric', month: 'short', year: 'numeric' }) : 'Undated'}: </span>{f.text} <Source f={f} /></li>
  }
  if (f.section === 'competitors') return <li>According to {f.source_title || host(f.url)}: {f.text} <Source f={f} /></li>
  const quoted = f.quote && !f.text.toLowerCase().includes(f.quote.toLowerCase()) // a sentence that already quotes it says it once
  return <li>{f.text}{quoted && <> In their words: <q>{f.quote}</q></>} <Source f={f} /></li>
}

function Brief({ brief }) {
  return (
    <>
      {brief.notice && <p>{brief.notice}</p>}
      {Object.entries(SECTION_LABEL).map(([key, label]) => {
        const lines = brief.facts.filter((f) => f.section === key)
        return lines.length > 0 && (
          <div key={key}>
            <h3>{label}</h3>
            <ul className="brief-lines">{lines.map((f) => <Line key={f.id} f={f} />)}</ul>
          </div>
        )
      })}
      {brief.missing.length > 0 && <p className="small muted">Not included: {brief.missing.join('; ')}.</p>}
    </>
  )
}

// One prep pack: the company brief, talking points, pitch, likely questions, questions to ask, right to work, on the day
export default function PrepPack({ id, s, go, refresh, notify, onBack }) {
  const [pack, setPack] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api(`/api/prep/${id}`).then(setPack).catch(setError) }, [id])
  const save = (changes) => attempt(notify)(async () => setPack(await patch(`/api/prep/${id}`, changes)))
  const [researched, setResearched] = useState(null) // a refresh's research, so a failed rewrite is retried without researching again
  const again = useAction(async () => {
    const company = researched || await post(`/api/prep/${id}/refresh`)
    setResearched(company)
    const target = pack.saved_job_id ? { job_id: pack.saved_job_id } : { application_id: pack.application_id }
    setPack(await post('/api/ai/prep', { company_id: company.company_id, ...target }))
    setResearched(null)
    await refresh()
    notify('Pack refreshed')
  })
  const remove = () => {
    if (!window.confirm(`Delete the prep pack for ${pack.role} at ${pack.company}?`)) return
    attempt(notify)(async () => { await del(`/api/prep/${id}`); await refresh(); notify('Prep pack deleted'); onBack() })
  }

  if (error) return <ErrorRetry error={error} onRetry={() => { setError(null); api(`/api/prep/${id}`).then(setPack).catch(setError) }} />
  if (!pack) return <p className="muted">Opening your pack</p>
  const c = pack.content
  const facts = Object.fromEntries(c.brief.facts.map((f) => [f.id, f]))
  const achievements = Object.fromEntries(s.achievements.map((a) => [a.id, a]))
  const stories = Object.fromEntries(s.stories.map((st) => [st.id, st]))
  const kinds = { ...Object.fromEntries(s.options.competencies), ...QUESTION_KIND }
  const blur = (key, stored) => (e) => { if (e.target.value.trim() !== stored) save({ [key]: e.target.value.trim() }) }
  const tick = (i) => save({ ticked: c.ticked.includes(i) ? c.ticked.filter((x) => x !== i) : [...c.ticked, i] })
  const canRefresh = pack.saved_job_id || pack.application_id

  return (
    <div className="stack pack">
      <div className="row no-print">
        <button className="linkish small" onClick={onBack}><ArrowLeft size={14} />All packs</button>
      </div>
      <section className="card">
        <div className="row">
          <div style={{ flex: 1, minWidth: 220 }}>
            <h2>{pack.role} at {pack.company}</h2>
            <p className="small muted">Researched on {longDate(c.brief.researched_at)}. Every line links to where it was read.</p>
          </div>
          <div className="row no-print">
            {pack.saved_job_id && <button className="btn ghost small" onClick={() => go('interview', null, { jobId: pack.saved_job_id })}><Mic size={14} />Practise with this pack</button>}
            {canRefresh && <button className="btn ghost small" disabled={again.loading} onClick={() => again.run()}><RefreshCw size={14} />{again.loading ? 'Refreshing' : 'Refresh'}</button>}
            <button className="btn ghost small" onClick={() => window.print()}><Printer size={14} />Print</button>
            <button className="icon-btn" aria-label="Delete this pack" onClick={remove}><Trash2 size={16} /></button>
          </div>
        </div>
        {again.loading && <p className="small muted no-print">Researching again and rewriting the pack. About a minute. Your own pitch and right-to-work line are kept.</p>}
        <ErrorRetry error={again.error} onRetry={again.retry} />
      </section>

      <section className="card pack-section">
        <h2>Company brief</h2>
        <Brief brief={c.brief} />
      </section>

      <section className="card pack-section">
        <h2>Why this company, for you</h2>
        {c.talking_points.length === 0 ? <p className="muted">Nothing was found about the company to build these from.</p> : (
          <ol className="stack" style={{ gap: 10, paddingLeft: 18 }}>
            {c.talking_points.map((t, i) => (
              <li key={i}>
                {t.text}
                <span className="small muted" style={{ display: 'block' }}>
                  {facts[t.fact_id] && <>From: {facts[t.fact_id].text} <Source f={facts[t.fact_id]} /></>}
                  {achievements[t.achievement_id] && <> Your achievement: {achievements[t.achievement_id].title}</>}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="card pack-section">
        <h2>Tell me about yourself</h2>
        <p className="small muted no-print">About a minute to 90 seconds spoken. Edit it into your own words; your version is kept when the pack is refreshed.</p>
        <textarea key={`pitch:${c.pitch}`} rows={9} defaultValue={c.pitch} maxLength={2500} onBlur={blur('pitch', c.pitch)} aria-label="Tell me about yourself" />
        <p className="print-only draft">{c.pitch}</p>
      </section>

      <section className="card pack-section">
        <h2>Likely questions</h2>
        <ol className="stack" style={{ gap: 12, paddingLeft: 18 }}>
          {c.likely_questions.map((q, i) => (
            <li key={i}>
              <span className="strong">{q.question}</span> <span className="chip">{kinds[q.competency] || 'Role knowledge'}</span>
              {q.why && <span className="small muted" style={{ display: 'block' }}>{q.why}</span>}
              <span className="small" style={{ display: 'block' }}>
                {stories[q.story_id] ? <>Use your story: <span className="strong">{stories[q.story_id].title}</span></>
                  : <>No story yet. <button className="linkish small no-print" onClick={() => go('interview', 'stories')}>Write one</button></>}
              </span>
            </li>
          ))}
        </ol>
      </section>

      <section className="card pack-section">
        <h2>Questions to ask them</h2>
        <p className="small muted no-print">Tick two or three to take with you.</p>
        <div className={`stack ${c.ticked.length ? 'ticked-some' : ''}`} style={{ gap: 8 }}>
          {c.questions_to_ask.map((q, i) => (
            <label key={i} className={`check ${c.ticked.includes(i) ? '' : 'unticked'}`}>
              <input type="checkbox" checked={c.ticked.includes(i)} disabled={!c.ticked.includes(i) && c.ticked.length >= MAX_TICKS} onChange={() => tick(i)} />
              <span>{q.question}{facts[q.fact_id] && <> <Source f={facts[q.fact_id]} /></>}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="card pack-section">
        <h2>Your right-to-work answer</h2>
        {c.right_to_work || c.right_to_work_edited ? (
          <input type="text" key={`rtw:${c.right_to_work}`} defaultValue={c.right_to_work} maxLength={300} onBlur={blur('right_to_work', c.right_to_work)} aria-label="Your right-to-work answer" />
        ) : (
          <p className="small">Add your visa type and end date in <button className="linkish" onClick={() => go('profile')}>Your details</button> to get this line.</p>
        )}
        <p className="print-only">{c.right_to_work}</p>
        <p className="small muted">Employers often ask next whether you will need sponsorship. That answer is yours to add. This is not immigration advice.</p>
      </section>

      <section className="card pack-section">
        <div className="row">
          <h2 style={{ flex: 1 }}>On the day</h2>
          <select value={c.interview_type} onChange={(e) => save({ interview_type: e.target.value })} aria-label="Interview type" className="no-print">
            {s.options.interview_types.map((t) => <option key={t} value={t}>{INTERVIEW_TYPE_LABEL[t]}</option>)}
          </select>
        </div>
        <h3>{INTERVIEW_TYPE_LABEL[c.interview_type]} interview</h3>
        <ul className="dots small">{s.content.interview_day[c.interview_type].map((x) => <li key={x}>{x}</li>)}</ul>
        <h3>UK interview norms</h3>
        <ul className="dots small">{s.content.tone_norms.map((x) => <li key={x}>{x}</li>)}</ul>
      </section>
    </div>
  )
}
