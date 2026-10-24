import { useState } from 'react'
import { CalendarDays, ExternalLink, Pencil, Trash2 } from 'lucide-react'
import { del, patch, post } from '../api'
import { attempt, fmtDate } from '../ui'
import { ANSWERED, NEXT_STEPS, STEP_WORDS, label } from '../networking'
import DraftMessage from './DraftMessage'
import PersonForm from './PersonForm'

// One person: where they are, what to do next and by when, the steps so far, and the draft, chat and referral helpers
export default function ContactCard({ s, c, refresh, notify, go }) {
  const [open, setOpen] = useState(null) // 'draft' | 'edit' | null
  const [draftKey, setDraftKey] = useState(0) // a fresh draft each time the box is opened, kept while it stays open
  const openDraft = () => { setDraftKey((k) => k + 1); setOpen('draft') }
  const safely = attempt(notify)
  // recording a step closes an open draft, so the next one fits where they now are
  const step = (kind, words) => safely(async () => { setOpen(null); await post(`/api/contacts/${c.id}/events`, { kind }); await refresh(); notify(words) })
  const ownMessage = () => step('sent', `Message to ${c.name} counted`)
  const remove = () => {
    if (!window.confirm(`Delete ${c.name}? Messages you sent them still count toward your weekly targets.`)) return
    safely(async () => { await del(`/api/contacts/${c.id}`); await refresh(); notify('Contact deleted') })
  }
  const saveNotes = (e) => {
    if (e.target.value === c.notes) return
    safely(async () => { await patch(`/api/contacts/${c.id}`, { notes: e.target.value }); await refresh() })
  }
  const where = [c.role, c.company].filter(Boolean).join(' at ')

  return (
    <article className="card person">
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3>{c.name}</h3>
          {where && <p className="small">{where}</p>}
          <div className="row" style={{ gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
            <span className={`chip ${ANSWERED.has(c.status) ? 'good' : ''}`}>{label(s, 'contact_statuses', c.status)}</span>
            <span className="chip">{label(s, 'relationships', c.relationship)}{c.event_name ? `: ${c.event_name}` : ''}</span>
            {c.link && <a className="small" href={c.link} target="_blank" rel="noopener noreferrer">Profile <ExternalLink size={12} /></a>}
          </div>
        </div>
        <button className="icon-btn" aria-label={`Edit ${c.name}`} onClick={() => setOpen(open === 'edit' ? null : 'edit')}><Pencil size={16} /></button>
        <button className="icon-btn" aria-label={`Delete ${c.name}`} onClick={remove}><Trash2 size={16} /></button>
      </div>

      <p className={`next-line ${c.next.late ? 'late' : ''}`}>
        <span className="strong">Next: </span>{c.next.text}{' '}
        {c.next.due_on && (
          <span className={`chip contactcard-due ${c.next.late ? 'warn' : 'muted'}`}>
            <CalendarDays size={12} aria-hidden="true" />{c.next.late ? 'was due' : 'by'} {fmtDate(c.next.due_on, { day: 'numeric', month: 'short' })}
          </span>
        )}
      </p>

      <div className="row" style={{ flexWrap: 'wrap' }}>
        <button className="btn small" onClick={() => (open === 'draft' ? setOpen(null) : openDraft())}>{open === 'draft' ? 'Close draft' : 'Write a message'}</button>
        <button className="btn ghost small" onClick={ownMessage}>I sent my own message</button>
        {NEXT_STEPS[c.status].map(([kind, words]) => <button key={kind} className="btn ghost small" onClick={() => step(kind, words)}>{words}</button>)}
      </div>

      {c.status === 'chat_booked' && (
        <div className="sub-block">
          <h4>Questions to ask</h4>
          <ol className="small">{c.chat_questions.map((q) => <li key={q}>{q}</li>)}</ol>
          <p className="small muted">Keep to 15 minutes. End by asking who else you should talk to.</p>
        </div>
      )}

      {c.status === 'chat_done' && (
        <div className="sub-block">
          <h4>After the chat</h4>
          <label className="field">What you talked about<textarea rows={3} maxLength={4000} defaultValue={c.notes} key={c.notes} onBlur={saveNotes} /></label>
          <p className="small">Did you ask who else to talk to? A name from them is your warmest introduction.</p>
          {c.next.text.startsWith('Send a thank-you') && open !== 'draft' && (
            <div><button className="btn small" onClick={openDraft}>Write the thank-you</button></div>
          )}
        </div>
      )}

      {c.status === 'referral_offered' && (
        <div className="sub-block">
          <p className="small">In the application, choose {c.name} under Saved contact. Its source becomes Referral.</p>
          <div><button className="btn ghost small" onClick={() => go('applications')}>Open Applications</button></div>
        </div>
      )}

      {/* marking it as sent moves the contact on but keeps this draft on screen, to copy or read again */}
      {open === 'draft' && <DraftMessage key={draftKey} s={s} c={c} onSent={async () => { await refresh(); notify('Marked as sent') }} notify={notify} />}
      {open === 'edit' && (
        <PersonForm s={s} person={c} onSaved={async () => { setOpen(null); await refresh(); notify('Saved') }} onCancel={() => setOpen(null)} />
      )}

      {c.history.length > 0 && (
        <ol className="history">
          {c.history.map((h, i) => (
            <li key={i}>
              <span>{STEP_WORDS[h.kind]}{h.message_type && h.message_type !== 'own' ? ` (${label(s, 'message_types', h.message_type)})` : ''}</span>
              <span className="muted">{fmtDate(h.on_day, { day: 'numeric', month: 'short' })}</span>
            </li>
          ))}
        </ol>
      )}
    </article>
  )
}
