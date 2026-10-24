import { useState } from 'react'
import { post } from '../api'
import { ErrorRetry, useAction } from '../ui'
import { ENDED, ENDED_FOR, LESSON_LINK, answersKept, endedFrom, useEscape } from '../tracker'

// One rejection's lesson: a possibility, never a verdict, and the page that fixes it
export function Lesson({ lesson, go }) {
  return (
    <div className="lesson">
      <p className="kicker">What probably happened</p>
      <p>{lesson.likely_reason}</p>
      <p className="kicker">One change for next time</p>
      <p className="strong">{lesson.one_change}</p>
      <button type="button" className="btn small" onClick={() => go(lesson.page)}>{LESSON_LINK[lesson.page]}</button>
    </div>
  )
}

// Asked when a card moves to Rejected: where it ended and whether they gave feedback. Nothing
// changes until it is sent, so Cancel leaves the card where it was. `target` is a rejected stage the
// user picked from a menu; the answer the form starts on agrees with it.
export default function RejectQuestions({ app, from, target, refresh, go, close }) {
  const fits = (answer) => answer && (!target || ENDED_FOR[target].includes(answer))
  const [ended, setEnded] = useState(fits(app.rejected_at_stage) ? app.rejected_at_stage : endedFrom(from || app.stage, target))
  const [feedback, setFeedback] = useState(app.feedback_received || '')
  const send = useAction(() => post(`/api/applications/${app.id}/reject`, { ended_at: ended, feedback }))
  const done = send.result
  const leave = send.loading ? () => {} : close // once Save is pressed the rejection is on its way: it cannot be cancelled
  useEscape(leave)
  const submit = async (e) => {
    e.preventDefault()
    await send.run()
    refresh()
  }

  return (
    <div className="backdrop" onClick={leave}>
      <div className="dialog card" role="dialog" aria-modal="true" aria-labelledby="reject-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="reject-title">{app.role} at {app.company}</h2>
        {!done ? (
          <form className="stack" onSubmit={submit}>
            <fieldset className="choices">
              <legend>Where did it end?</legend>
              {ENDED.map(([key, label]) => (
                <label key={key} className="check"><input type="radio" name="ended" value={key} checked={ended === key} onChange={() => setEnded(key)} />{label}</label>
              ))}
            </fieldset>
            <label className="field"><span>Did they give feedback? <span className="muted" style={{ fontWeight: 400 }}>(optional)</span></span>
              <textarea rows={3} maxLength={2000} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Their words, as near as you remember them" />
            </label>
            <p className="small muted">Writes one lesson from the CV you sent and the job description, if either was recorded. One AI action.</p>
            <div className="row">
              <button className="btn" type="submit" disabled={send.loading}>{send.loading ? 'Saving and writing a lesson' : 'Save'}</button>
              <button className="btn ghost" type="button" disabled={send.loading} onClick={close}>{answersKept(send.error) ? 'Close' : 'Cancel'}</button>
            </div>
            {answersKept(send.error) && <p className="small">Rejection and answers saved. Ask for the lesson again from the application.</p>}
            <ErrorRetry error={send.error} onRetry={async () => { await send.retry(); refresh() }} />
          </form>
        ) : (
          <div className="stack">
            {done.lesson ? <Lesson lesson={done.lesson} go={go} /> : <p>{done.notice}</p>}
            <div><button className="btn ghost" onClick={close}>Done</button></div>
          </div>
        )}
      </div>
    </div>
  )
}
