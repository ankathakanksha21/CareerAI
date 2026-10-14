import { useState } from 'react'
import { Download } from 'lucide-react'
import { download, post } from '../api'
import { ErrorRetry, attempt, plural, useAction } from '../ui'
import EditableText from './EditableText'
import { addAchievement, trimIdeas } from '../cv'

const LETTER_PARTS = [['why_them', 'Why them'], ['why_you', 'Why you'], ['what_you_deliver', 'What you will deliver']]
const fileUrl = (id, format, part) => `/api/cv-versions/${id}/download?format=${format}&part=${part}`

function Downloads({ id, part, disabled }) {
  const get = useAction((format) => download(fileUrl(id, format, part)))
  return (
    <>
      <div className="row">
        <button type="button" className="btn" disabled={disabled || get.loading} onClick={() => get.run('docx')}><Download size={15} />Word</button>
        <button type="button" className="btn ghost" disabled={disabled || get.loading} onClick={() => get.run('pdf')}><Download size={15} />PDF</button>
        {disabled && <span className="small muted">Saving your last change first</span>}
      </div>
      <ErrorRetry error={get.error} onRetry={get.retry} />
    </>
  )
}

// The job advert's main terms against this CV: what it already says, what the profile could add, and the gaps
function Keywords({ doc, change, achievements }) {
  const words = doc.keywords
  if (!words.terms.length) return null
  const byId = Object.fromEntries(achievements.map((a) => [a.id, a]))
  return (
    <section className="card">
      <h3>Keyword coverage</h3>
      <p className="sub">The main terms in the advert, matched word for word, as screening software does.</p>
      <div className="kw-group">
        <span className="small strong">In this CV ({words.covered.length} of {words.terms.length})</span>
        <div className="row">{words.covered.map((t) => <span key={t} className="chip good">{t}</span>)}{words.covered.length === 0 && <span className="small muted">None yet.</span>}</div>
      </div>
      {words.available.length > 0 && (
        <div className="kw-group">
          <span className="small strong">In your profile, not in this CV</span>
          {words.available.map(({ term, achievement_ids: ids }) => {
            const a = ids.map((id) => byId[id]).find(Boolean)
            return (
              <div key={term} className="row small">
                <span className="chip warn">{term}</span>
                {a
                  ? <><span className="muted" style={{ flex: 1, minWidth: 0 }}>Shown by: {a.title}</span><button type="button" className="linkish" onClick={() => change((d) => addAchievement(d, a))}>Add</button></>
                  : <span className="muted">Use the word in a bullet or your skills, if it is true of you.</span>}
              </div>
            )
          })}
        </div>
      )}
      {words.missing.length > 0 && (
        <div className="kw-group">
          <span className="small strong">Not in your profile</span>
          <div className="row">{words.missing.map((t) => <span key={t} className="chip">{t}</span>)}</div>
          <span className="small muted">Gaps. They are never added for you: only claim what you can show.</span>
        </div>
      )}
    </section>
  )
}

function Letter({ doc, meta, change, save, busy, notify }) {
  const [to, setTo] = useState(meta.contact_name || '')
  const name = to.trim()
  const letter = doc.cover_letter
  const whole = [`Dear ${name || 'Hiring Manager'},`, ...LETTER_PARTS.map(([key]) => letter[key]), `Yours ${name ? 'sincerely' : 'faithfully'},\n${doc.contact.name}`].join('\n\n')
  const copy = () => attempt(notify)(async () => { await navigator.clipboard.writeText(whole); notify('Cover letter copied') })
  return (
    <section className="card letter">
      <h2>Cover letter</h2>
      <p className="sub">UK letter form. Click any paragraph to edit it.</p>
      <label className="field" style={{ marginBottom: 12 }}>Who it is to <span className="muted" style={{ fontWeight: 400 }}>(optional, for example Ms Patel)</span>
        <input type="text" value={to} maxLength={120} onChange={(e) => setTo(e.target.value)}
          onBlur={() => { if (name !== (meta.contact_name || '')) save({ content: doc, contact_name: name }) }} />
      </label>
      <p>Dear {name || 'Hiring Manager'},</p>
      {LETTER_PARTS.map(([key, label]) => (
        <div key={key}>
          <p className="part">{label}</p>
          <p><EditableText value={letter[key]} max={2500} label={label.toLowerCase()} onChange={(v) => change((d) => { d.cover_letter[key] = v })} /></p>
        </div>
      ))}
      <p>Yours {name ? 'sincerely' : 'faithfully'},<br />{doc.contact.name}</p>
      <p className="small muted">The file is dated the day you download it and addressed to {name || 'Hiring Manager'}{doc.job ? ` at ${doc.job.company}` : ''}.</p>
      <div className="row" style={{ marginBottom: 8 }}><button type="button" className="btn ghost small" onClick={copy}>Copy text</button></div>
      <Downloads id={meta.id} part="letter" disabled={busy} />
    </section>
  )
}

function Applied({ doc, meta, s, busy, refresh, notify }) {
  const [source, setSource] = useState('Company site')
  const [postedOn, setPostedOn] = useState('')
  const saved = s.saved_jobs.find((j) => j.id === meta.saved_job_id)
  const log = useAction(async () => {
    await post('/api/applications', { company: doc.job.company, role: doc.job.title, saved_job_id: saved?.id ?? null, cv_version_id: meta.id,
      role_family_id: saved?.role_family_id ?? null, source, posted_on: postedOn || null })
    await refresh()
    notify(`Added to Applications with CV "${meta.name}"`)
  })
  return (
    <section className="card">
      <h3>Applied with this CV?</h3>
      <p className="small muted" style={{ marginTop: 4 }}>Once it is logged, this version is kept exactly as sent. Any later edit is saved as a new version.</p>
      <div className="row" style={{ marginTop: 10, alignItems: 'end' }}>
        <label className="field">Where you applied<select value={source} onChange={(e) => setSource(e.target.value)}>{s.options.sources.map((x) => <option key={x}>{x}</option>)}</select></label>
        <label className="field">Date posted <span className="muted" style={{ fontWeight: 400 }}>(optional)</span><input type="date" value={postedOn} onChange={(e) => setPostedOn(e.target.value)} /></label>
      </div>
      <div className="row" style={{ marginTop: 12 }}><button type="button" className="btn" disabled={busy || log.loading} onClick={() => log.run()}>Add to Applications with this CV</button></div>
      <ErrorRetry error={log.error} />
    </section>
  )
}

// Beside the CV: whether it is saved, how long it is, the files, keyword coverage, the letter, and logging the application
export default function CvSide({ doc, meta, status, retry, change, save, s, notify, refresh }) {
  const busy = status !== 'saved'
  const over = meta.pages > 2
  return (
    <div className="stack">
      <section className="card">
        <div className="row"><h3>{meta.name}</h3><span className="spacer" /><span className="small muted" role="status">{status === 'saving' ? 'Saving' : status === 'saved' ? 'Saved' : 'Not saved'}</span></div>
        {status !== 'saving' && status !== 'saved' && <ErrorRetry error={status} onRetry={retry} />}
        <p className={`verdict ${over ? 'warn' : 'good'}`} style={{ margin: '12px 0' }}>
          {plural(meta.pages, 'page')}{over ? '. A UK CV should be no more than two.' : meta.pages === 2 ? ', the usual length for a UK CV.' : '. Up to two is fine.'}
        </p>
        {over && (
          <>
            <p className="small strong">What you could trim</p>
            <ul className="dots small" style={{ marginBottom: 12 }}>{trimIdeas(doc).map((x) => <li key={x}>{x}</li>)}</ul>
          </>
        )}
        <Downloads id={meta.id} part="cv" disabled={busy} />
        {meta.unsupported && (
          <p className="note" role="status" style={{ marginTop: 10 }}>
            The PDF cannot show {meta.unsupported.length === 1 ? 'this character' : 'these characters'}: {[...meta.unsupported].join(' ')}. {meta.unsupported.length === 1 ? 'It prints' : 'They print'} as ? there. The Word file shows everything.
          </p>
        )}
        <p className="small muted" style={{ marginTop: 10 }}>Pages are counted from the PDF itself. Nothing is cut for you: hide or shorten what matters least.</p>
      </section>

      <Keywords doc={doc} change={change} achievements={s.achievements} />

      {doc.gaps.length > 0 && (
        <section className="card">
          <h3>Be ready to talk about</h3>
          <ul className="dots small">{doc.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
        </section>
      )}

      {doc.cover_letter && <Letter doc={doc} meta={meta} change={change} save={save} busy={busy} notify={notify} />}
      {doc.job && <Applied doc={doc} meta={meta} s={s} busy={busy} refresh={refresh} notify={notify} />}
    </div>
  )
}
