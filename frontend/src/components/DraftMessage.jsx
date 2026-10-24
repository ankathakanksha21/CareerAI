import { useState } from 'react'
import { Copy } from 'lucide-react'
import { post } from '../api'
import { ErrorRetry, attempt, useAction } from '../ui'
import { draftTypes, suggestedDraft } from '../networking'

const NOTE_LIMIT = 200

// A saved job at the contact's company, guessed from the first word of its name. The server checks it properly
function likelyJob(s, c) {
  const first = (c.company || '').toLowerCase().split(/\s+/)[0]
  return first ? s.saved_jobs.find((j) => j.company.toLowerCase().includes(first)) : null
}

// One draft for one contact: the user picks the kind, the AI writes it, the user copies it and sends it themselves
export default function DraftMessage({ s, c, kind, onSent, notify }) {
  const [type, setType] = useState(kind || suggestedDraft(c))
  const [learned, setLearned] = useState('')
  const [start, setStart] = useState('')
  const [jobId, setJobId] = useState(() => likelyJob(s, c)?.id || '')
  const [marked, setMarked] = useState(null)
  const write = useAction(() => post('/api/ai/outreach', {
    contact_id: c.id, type, learned, start, job_id: type === 'referral_ask' && jobId ? jobId : null,
  }))
  const safely = attempt(notify)
  const choose = (value) => { setType(value); write.setResult(null); setMarked(null) }
  const copy = () => safely(async () => { await navigator.clipboard.writeText(write.result.message); notify('Copied') })
  const sent = () => safely(async () => {
    const updated = await post(`/api/contacts/${c.id}/events`, { kind: 'sent', message_type: type })
    setMarked(type)
    onSent(updated)
  })
  const r = write.result

  return (
    <div className="sub-block">
      <div className="form-row">
        <label className="field">Message
          <select value={type} onChange={(e) => choose(e.target.value)}>
            {draftTypes(s, c).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        {type === 'referral_ask' && (
          <label className="field" style={{ flex: 1 }}>The job
            <select value={jobId} onChange={(e) => setJobId(e.target.value)}>
              <option value="">Choose a saved job</option>
              {s.saved_jobs.map((j) => <option key={j.id} value={j.id}>{j.title}, {j.company}</option>)}
            </select>
          </label>
        )}
      </div>
      {type === 'thank_you' && (
        <label className="field">One thing you learned
          <input type="text" maxLength={500} placeholder="How the team tests its reports before they go out" value={learned} onChange={(e) => setLearned(e.target.value)} />
        </label>
      )}
      {type === 'recruiter_intro' && (
        <label className="field">When can you start? (optional)
          <input type="text" maxLength={80} placeholder="From 2 November" value={start} onChange={(e) => setStart(e.target.value)} />
          <span className="small muted" style={{ fontWeight: 400 }}>Left empty, the draft says only when your course ends.</span>
        </label>
      )}
      {type === 'referral_ask' && <p className="small muted">Ask only after you have spoken, and only for a saved job at their company.</p>}
      {type === 'connection_note' && <p className="small muted">Up to {NOTE_LIMIT} characters. A free LinkedIn account gets only a few notes a month.</p>}
      <div className="row">
        <button type="button" className="btn small" disabled={write.loading || (type === 'thank_you' && !learned.trim())} onClick={() => write.run()}>
          {write.loading ? 'Writing' : r ? 'Write again' : 'Write a draft'}
        </button>
        <span className="chip muted">1 AI action</span>
      </div>
      <ErrorRetry error={write.error} onRetry={write.retry} />
      {r && (
        <div className="stack" style={{ gap: 6 }}>
          <textarea readOnly rows={type === 'connection_note' ? 5 : 9} value={r.message} aria-label="Draft message" />
          <span className="small muted">{type === 'connection_note' ? `${r.characters} of ${NOTE_LIMIT} characters` : `${r.words} words`}. Copy, edit and send it yourself.</span>
          <div className="row">
            <button type="button" className="btn small" onClick={copy}><Copy size={14} />Copy</button>
            {marked === type
              ? <span className="small strong">Marked as sent</span>
              : <button type="button" className="btn ghost small" onClick={sent}>Mark as sent</button>}
          </div>
        </div>
      )}
    </div>
  )
}
