import { useImperativeHandle, useState } from 'react'
import { post } from '../api'
import { ErrorRetry, fmtMonth, period, useAction } from '../ui'

const FIELD_NAME = { job_title: 'job title', location: 'location', country: 'country', start_month: 'start month', end_month: 'end month',
  employer_context: 'what the employer does', grade: 'grade' }
const count = (facts) => (facts ? facts.work_history.length + facts.education.length + facts.skills.length + facts.languages.length : 0)

// Whether an import found any job, course, skill or language to offer
export const hasFacts = (found) => count(found?.facts) > 0

// What a second import found, added to what the first found and the user has not confirmed yet
export function mergeFound(before, after) {
  if (!hasFacts(before)) return after
  if (!hasFacts(after)) return { ...before, notice: after?.notice || before.notice }
  const a = before.facts, b = after.facts
  const skills = [...a.skills, ...b.skills.filter((x) => !a.skills.some((y) => y.toLowerCase() === x.toLowerCase()))]
  const languages = [...a.languages, ...b.languages.filter((x) => !a.languages.some((y) => y.language.toLowerCase() === x.language.toLowerCase()))]
  return { ...after, facts: { work_history: [...a.work_history, ...b.work_history], education: [...a.education, ...b.education], skills, languages } }
}

const adds = (e) => Object.entries(e.adds).map(([k, v]) => `${FIELD_NAME[k] || k} (${k.endsWith('_month') ? fmtMonth(v) : v})`).join(', ')
const jobLine = (e) => [[e.job_title, e.employer].filter(Boolean).join(', '), [e.location, e.country].filter(Boolean).join(', '), period(e)].filter(Boolean).join(' · ')
const courseLine = (e) => [[`${e.qualification} ${e.subject}`.trim(), e.institution].filter(Boolean).join(', '), e.country, period(e), e.grade].filter(Boolean).join(' · ')

/*
  "We also found": the jobs, courses, skills and languages an import read, for the user to
  confirm. Everything starts ticked. Nothing here is saved until they confirm it. An entry
  that matches one they already have only adds what that one is missing.
  With `embedded`, the page's own button saves through ref.current.save().
*/
export default function FoundFacts({ found, onSaved, onDismiss, embedded, ref }) {
  const [off, setOff] = useState(() => new Set())
  const { facts, source } = found
  const flip = (key) => setOff((was) => { const next = new Set(was); if (!next.delete(key)) next.add(key); return next })
  const kept = (list, prefix, id = (_, i) => i) => list.filter((x, i) => !off.has(`${prefix}:${id(x, i)}`))
  const entry = (e) => (e.id ? { id: e.id, ...e.adds, achievement_ids: e.achievement_ids } : e)
  const send = async () => {
    await post('/api/profile/facts', {
      source,
      work_history: kept(facts.work_history, 'job').map(entry),
      education: kept(facts.education, 'course').map(entry),
      skills: kept(facts.skills, 'skill', (x) => x),
      languages: kept(facts.languages, 'language', (x) => x.language),
    })
    await onSaved()
  }
  const save = useAction(send)
  // embedded: the page's own button saves, and shows the error itself if the save fails
  useImperativeHandle(ref, () => ({ save: send }))
  const ticked = count(facts) - off.size

  const tick = (key, text, sub) => (
    <label key={key} className="found-row">
      <input type="checkbox" checked={!off.has(key)} onChange={() => flip(key)} />
      <span>{text}{sub && <span className="small muted" style={{ display: 'block' }}>{sub}</span>}</span>
    </label>
  )
  const chips = (list, prefix, id, label) => (
    <div className="row">
      {list.map((x) => (
        <button key={id(x)} type="button" className={`chip chip-btn ${off.has(`${prefix}:${id(x)}`) ? '' : 'good'}`} aria-pressed={!off.has(`${prefix}:${id(x)}`)} onClick={() => flip(`${prefix}:${id(x)}`)}>
          {label(x)}
        </button>
      ))}
    </div>
  )

  return (
    <section className="card tint stack">
      <div>
        <h2>We also found</h2>
        <p className="small muted">Untick anything that is wrong. You can edit every entry on your Profile page afterwards.</p>
      </div>
      {facts.work_history.length > 0 && (
        <div className="stack" style={{ gap: 6 }}>
          <h3>Work history</h3>
          {facts.work_history.map((e, i) => (e.id
            ? tick(`job:${i}`, `Adds to ${e.name}`, adds(e) || 'Links your new achievements to this job')
            : tick(`job:${i}`, jobLine(e), e.employer_context && `${e.employer_context} (written by the AI: check it)`)))}
        </div>
      )}
      {facts.education.length > 0 && (
        <div className="stack" style={{ gap: 6 }}>
          <h3>Education</h3>
          {facts.education.map((e, i) => (e.id
            ? tick(`course:${i}`, `Adds to ${e.name}`, adds(e) || 'Links your new achievements to this course')
            : tick(`course:${i}`, courseLine(e))))}
        </div>
      )}
      {facts.skills.length > 0 && <div className="stack" style={{ gap: 6 }}><h3>Skills</h3>{chips(facts.skills, 'skill', (x) => x, (x) => x)}</div>}
      {facts.languages.length > 0 && (
        <div className="stack" style={{ gap: 6 }}>
          <h3>Languages</h3>
          {chips(facts.languages, 'language', (x) => x.language, (x) => (x.level ? `${x.language} (${x.level})` : x.language))}
        </div>
      )}
      {!embedded && <ErrorRetry error={save.error} onRetry={save.retry} />}
      {!embedded && (
        <div className="row">
          <button className="linkish small" onClick={onDismiss}>Dismiss</button>
          <span className="spacer" />
          <button className="btn" disabled={save.loading || ticked === 0} onClick={() => save.run()}>{save.loading ? 'Saving' : 'Add to my profile'}</button>
        </div>
      )}
    </section>
  )
}
