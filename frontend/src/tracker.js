// The tracker's words and small rules, shared by the board, the detail panel and the home page
import { useEffect } from 'react'

export const STAGE_LABEL = { applied: 'Applied', no_response: 'No reply', rejected: 'Rejected at CV', screening: 'Phone screen', interview: 'Interview', rejected_after_interview: 'Rejected after interview', offer: 'Offer' }
export const REJECTED = new Set(['rejected', 'rejected_after_interview'])
export const CLOSED = new Set(['offer', ...REJECTED]) // an application that has ended: nothing to follow up

// Where a rejection ended, as the user answers it
export const ENDED = [['cv', 'At the CV stage'], ['screening', 'After a phone screen'], ['interview', 'After an interview'], ['final', 'After a final interview']]
export const ENDED_LABEL = Object.fromEntries(ENDED)
// The same, inside a sentence: "Ended at the CV stage."
export const ENDED_PHRASE = { cv: 'at the CV stage', screening: 'after a phone screen', interview: 'after an interview', final: 'after a final interview' }
// Which answers fit each rejected stage
export const ENDED_FOR = { rejected: ['cv', 'screening'], rejected_after_interview: ['interview', 'final'] }
const FROM_STAGE = { screening: 'screening', interview: 'interview', rejected_after_interview: 'interview', offer: 'final' }
// The answer the question form starts on: from where the card was, unless the user picked a rejected
// stage from a menu, which it must agree with
export const endedFrom = (stage, target = null) => {
  const guess = FROM_STAGE[stage] || 'cv'
  return !target || ENDED_FOR[target].includes(guess) ? guess : ENDED_FOR[target][0]
}

// The page that fixes what a lesson found, and its button
export const LESSON_LINK = { resume: 'Open Resume', interview: 'Practise an interview', profile: 'Open your profile' }

// The day stage changes started being recorded; an older card has no history before it
export const HISTORY_FROM = '14 October 2026'

export const isDue = (s, a) => s.follow_ups_due.some((f) => f.id === a.id && f.due)

// A failed lesson (the model, or the day's limit) still leaves the rejection and the answers saved
export const answersKept = (error) => Boolean(error) && (error.status === 429 || error.status === 502)

// Close a dialog or panel with the Escape key
export function useEscape(close) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])
}
