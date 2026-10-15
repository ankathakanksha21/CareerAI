import { parseDay } from './ui'

// Networking's words and small rules, shared by the Networking page, Home and the application panel.
// The labels themselves come from the server (s.options), so they are written once.

export const label = (s, list, key) => (s.options[list].find(([k]) => k === key) || [key, key])[1]

export const REFEREES = new Set(['tutor', 'supervisor'])
export const ANSWERED = new Set(['replied', 'chat_booked', 'chat_done', 'referral_offered'])

// The drafts a contact can be sent. A reference is asked only of a tutor, lecturer or supervisor
export const draftTypes = (s, c) => s.options.message_types.filter(([k]) => k !== 'own' && (k !== 'reference_ask' || REFEREES.has(c.relationship)))

// The draft that fits where someone is in the pipeline
export function suggestedDraft(c) {
  if (c.status === 'messaged') return 'follow_up'
  if (c.status === 'chat_done') return 'thank_you'
  if (c.relationship === 'recruiter') return 'recruiter_intro'
  if (c.status === 'to_contact' && c.relationship === 'none') return 'connection_note'
  return 'chat_request'
}

// The steps a user can record next, by where the contact is now. A message sent is recorded from the draft
export const NEXT_STEPS = {
  to_contact: [],
  messaged: [['replied', 'They replied']],
  replied: [['chat_booked', 'Chat booked'], ['referral_offered', 'Referral offered']],
  chat_booked: [['chat_done', 'Chat done']],
  chat_done: [['referral_offered', 'Referral offered']],
  referral_offered: [],
}

export const STEP_WORDS = { sent: 'Message sent', replied: 'They replied', chat_booked: 'Chat booked', chat_done: 'Chat done', referral_offered: 'Referral offered' }

const LONDON = 'Europe/London'

// An event's time as the UK sees it, wherever the browser is
export const eventWhen = (iso) => new Date(iso).toLocaleString('en-GB', {
  timeZone: LONDON, weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
})

// A stored time as the value of a date-and-time box, in London time
export function londonInput(iso) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone: LONDON, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(iso)).map((p) => [p.type, p.value]))
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`
}

// The date box beside an event: its London day
export function dayBox(onDay) {
  const d = parseDay(onDay)
  return { day: d.getDate(), month: d.toLocaleDateString('en-GB', { month: 'short' }) }
}
