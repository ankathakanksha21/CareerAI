import { useState } from 'react'
import { Copy, Trash2, X } from 'lucide-react'
import { del, patch, post } from '../api'
import { ErrorRetry, attempt, fmtDate, useAction } from '../ui'
import { CLOSED, ENDED_PHRASE, HISTORY_FROM, REJECTED, STAGE_LABEL, useEscape } from '../tracker'
import { Lesson } from './RejectQuestions'

const SPONSOR = { yes: true, no: false, '': null }
const sponsorValue = (v) => (v === true ? 'yes' : v === false ? 'no' : '')
const when = (at) => new Date(at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })

// Every field of one application, each saved as it changes, with its stage history, follow-up and lesson
export default function ApplicationPanel({ app: a, s, refresh, go, notify, close, onReject }) {
  const [refused, setRefused] = useState({}) // per field: a new number puts the stored value back after a refused or blank edit
  const draft = useAction(() => post(`/api/ai/applications/${a.id}/follow-up`))
  const relearn = useAction(async () => {
    const r = await post(`/api/applications/${a.id}/reject`, { ended_at: a.rejected_at_stage, feedback: a.feedback_received || '' })
    await refresh()
    return r
  })
  const safely = attempt(notify)
  // the field being edited is saved first, as clicking away would save it: its leave handler is run
  // directly, since a browser need not fire one for a field that is about to disappear
  useEscape(() => {
    const field = document.activeElement
    if (field?.closest('.panel')) field.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
    close()
  })
  const putBack = (keys) => setRefused((r) => ({ ...r, ...Object.fromEntries(keys.map((k) => [k, (r[k] || 0) + 1])) }))

  const save = (fields) => safely(async () => {
    try {
      await patch(`/api/applications/${a.id}`, fields)
    } catch (e) {
      // a refused edit shows the stored value again; after a network or server failure the typing is kept to try again
      if (e.status >= 400 && e.status < 500) putBack(Object.keys(fields))
      throw e
    }
    await refresh()
  })
  // a text or date field, saved on leaving it if it changed; a required one is never blanked
  const text = (key, { required = false } = {}) => ({
    defaultValue: a[key] || '',
    onBlur: (e) => {
      const value = e.target.value.trim()
      if (value === (a[key] || '')) return
      if (required && !value) { putBack([key]); return }
      save({ [key]: value || null })
    },
  })
  // an input remounts, showing what is stored, when its stored value changes or an edit of it is refused
  const stamp = (key) => `${refused[key] || 0}:${a[key] ?? ''}`
  const followedUp = () => safely(async () => { await post(`/api/applications/${a.id}/followed-up`); await refresh(); notify('Next follow-up in a week') })
  const remove = () => {
    if (!window.confirm(`Delete the application to ${a.company}? Its history and lesson go with it.`)) return
    safely(async () => { await del(`/api/applications/${a.id}`); close(); await refresh(); notify('Application deleted') })
  }
  const copy = (value) => safely(async () => { await navigator.clipboard.writeText(value); notify('Copied') })
  const setStage = (stage) => (REJECTED.has(stage) ? onReject(a, stage) : save({ stage }))
  const cv = s.cv_versions.find((c) => c.id === a.cv_version_id)

  return (
    <div className="backdrop" onClick={close}>
      <aside className="panel" role="dialog" aria-modal="true" aria-labelledby="panel-title" onClick={(e) => e.stopPropagation()}>
        <div className="row">
          <h2 id="panel-title" style={{ flex: 1 }}>{a.role} at {a.company}</h2>
          <button className="icon-btn" aria-label="Close" onClick={close}><X size={18} /></button>
        </div>

        <div className="stack" style={{ marginTop: 14 }}>
          <div className="grid cols-2">
            <label className="field">Company<input type="text" maxLength={160} key={stamp('company')} {...text('company', { required: true })} /></label>
            <label className="field">Role<input type="text" maxLength={160} key={stamp('role')} {...text('role', { required: true })} /></label>
          </div>

          <div>
            <label className="field">Status
              <select value={a.stage} onChange={(e) => setStage(e.target.value)}>
                {s.options.stages.map((k) => <option key={k} value={k}>{STAGE_LABEL[k]}</option>)}
              </select>
            </label>
            {a.history.length > 0 ? (
              <ol className="history">
                {a.history.map((h, i) => <li key={i}><span>{h.from_stage ? `Moved to ${STAGE_LABEL[h.to_stage]}` : `Logged at ${STAGE_LABEL[h.to_stage]}`}</span><span className="muted">{when(h.at)}</span></li>)}
              </ol>
            ) : <p className="small muted" style={{ marginTop: 6 }}>Stage changes are recorded from {HISTORY_FROM}.</p>}
          </div>

          <div className="grid cols-2">
            <label className="field">Date applied<input type="date" key={stamp('applied_on')} {...text('applied_on', { required: true })} /></label>
            <label className="field">Date posted<input type="date" key={stamp('posted_on')} {...text('posted_on')} /></label>
          </div>

          <label className="field">CV version
            <span className="row">
              <select value={a.cv_version_id || ''} onChange={(e) => save({ cv_version_id: e.target.value || null })} style={{ flex: 1 }}>
                <option value="">No CV recorded</option>
                {s.cv_versions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              {cv && <button type="button" className="btn ghost small" onClick={() => go('resume', null, { cvId: cv.id })}>Open CV</button>}
            </span>
            {!cv && <span className="small muted" style={{ fontWeight: 400 }}>Without a CV recorded, this application does not count toward your weekly goal.</span>}
          </label>

          <div className="grid cols-2">
            <label className="field">Where you applied
              <select value={a.source} onChange={(e) => save({ source: e.target.value })}>{s.options.sources.map((x) => <option key={x}>{x}</option>)}</select>
            </label>
            <label className="field">Sponsor licence
              <select value={sponsorValue(a.sponsor_licence)} onChange={(e) => save({ sponsor_licence: SPONSOR[e.target.value] })}>
                <option value="">Not known</option><option value="yes">Yes, on the register</option><option value="no">No</option>
              </select>
            </label>
          </div>
          <label className="field">Link to the advert
            <span className="row"><input type="text" maxLength={500} placeholder="https://" style={{ flex: 1 }} key={stamp('job_url')} {...text('job_url')} />
              {/^https?:\/\//.test(a.job_url || '') && <a className="small" href={a.job_url} target="_blank" rel="noopener noreferrer">Open advert</a>}</span>
          </label>

          <section className="sub-block">
            <h3>Follow-up</h3>
            {CLOSED.has(a.stage) ? <p className="small muted">This application has ended, so there is nothing to follow up.</p> : (
              <>
                <div className="form-row">
                  <label className="field">Follow up on<input type="date" key={stamp('follow_up_on')} {...text('follow_up_on')} /></label>
                  <button type="button" className="btn ghost small" onClick={followedUp}>Mark as followed up</button>
                  {a.follow_up_on && <button type="button" className="linkish small" onClick={() => save({ follow_up_on: null })}>Clear</button>}
                </div>
                {a.last_followed_up_on && <p className="small muted">You last followed up on {fmtDate(a.last_followed_up_on, { day: 'numeric', month: 'long' })}.</p>}
                {a.stage === 'no_response' && <p className="small muted">At No reply, this application is not listed under Follow-ups due. Move it back to Applied to be reminded.</p>}
                <div className="row">
                  <button type="button" className="btn ghost small" disabled={draft.loading} onClick={() => draft.run()}>{draft.loading ? 'Drafting' : 'Draft a follow-up'}</button>
                  <span className="small muted">One AI action. Nothing is sent for you: copy it into your email.</span>
                </div>
                <ErrorRetry error={draft.error} onRetry={draft.retry} />
                {draft.result && (
                  <div className="stack" style={{ gap: 6 }}>
                    <p className="small"><span className="strong">Subject: </span>{draft.result.subject}</p>
                    <textarea readOnly rows={8} value={draft.result.message} aria-label="Follow-up message" />
                    <div><button type="button" className="btn small" onClick={() => copy(draft.result.message)}><Copy size={14} />Copy message</button></div>
                  </div>
                )}
              </>
            )}
          </section>

          <div className="grid cols-2">
            <label className="field">Contact name<input type="text" maxLength={120} placeholder="Who you dealt with" key={stamp('contact_name')} {...text('contact_name')} /></label>
            <label className="field">How to reach them<input type="text" maxLength={200} placeholder="Email, phone or LinkedIn" key={stamp('contact')} {...text('contact')} /></label>
          </div>
          <p className="small muted" style={{ marginTop: -6 }}>Only the name is used in a follow-up draft.</p>
          <label className="field">Notes<textarea rows={4} maxLength={4000} key={stamp('notes')} {...text('notes')} /></label>

          {REJECTED.has(a.stage) && (
            <section className="sub-block">
              <h3>Lesson</h3>
              {a.rejected_at_stage ? (
                <>
                  <p className="small">Ended {ENDED_PHRASE[a.rejected_at_stage]}. {a.feedback_received ? <>They said: "{a.feedback_received}"</> : 'No feedback given.'}</p>
                  {a.lesson ? <Lesson lesson={a.lesson} go={go} /> : relearn.result?.notice ? <p className="small">{relearn.result.notice}</p> : (
                    <div className="row"><button type="button" className="btn small" disabled={relearn.loading} onClick={() => relearn.run()}>{relearn.loading ? 'Writing the lesson' : 'Get the lesson'}</button></div>
                  )}
                  <ErrorRetry error={relearn.error} onRetry={relearn.retry} />
                  <button type="button" className="linkish small" onClick={() => onReject(a)}>Change the answers</button>
                </>
              ) : (
                <div className="row"><span className="small">Say where it ended to get one lesson from it.</span><button type="button" className="btn small" onClick={() => onReject(a)}>Where did it end?</button></div>
              )}
            </section>
          )}

          <div><button type="button" className="btn ghost small" onClick={remove}><Trash2 size={14} />Delete application</button></div>
        </div>
      </aside>
    </div>
  )
}
