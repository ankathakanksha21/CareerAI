import { useRef, useState } from 'react'
import { BookOpen, BriefcaseBusiness, Check, Compass, FileText, Handshake, House, Mic, Search, UserRound, Users } from 'lucide-react'

// Sidebar. key = route, label = what the user sees. Pages return here as their step goes live
export const NAV = [
  { key: 'home', label: 'This week', icon: House },
  { key: 'profile', label: 'Profile', icon: UserRound },
  { key: 'pathways', label: 'Career pathways', icon: Compass },
  { key: 'jobs', label: 'Jobs', icon: Search },
  { key: 'resume', label: 'Resume', icon: FileText },
  { key: 'interview', label: 'Interview coach', icon: Mic },
  { key: 'applications', label: 'Applications', icon: BriefcaseBusiness },
  { key: 'networking', label: 'Networking', icon: Users },
  { key: 'peers', label: 'Peers', icon: Handshake },
  { key: 'journal', label: 'Journal', icon: BookOpen },
]
export const PAGE_LABEL = Object.fromEntries(NAV.map((i) => [i.key, i.label]))

export function PageHead({ title, lede, children }) {
  return (
    <header className="page-head">
      <div style={{ flex: 1, minWidth: 260 }}>
        <h1>{title}</h1>
        {lede && <p className="lede">{lede}</p>}
      </div>
      {children}
    </header>
  )
}

// Wraps a call so each button gets its own loading, result and error state, and can be retried
export function useAction(fn) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const last = useRef([])
  const run = async (...args) => {
    last.current = args
    setLoading(true)
    setError(null)
    try {
      const r = await fn(...args)
      setResult(r)
      return r
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }
  return { run, loading, result, error, setResult, retry: () => run(...last.current) }
}

// For one-click actions (tick, drag, delete): if the request fails, tell the user instead of failing silently.
// onGone, if given, runs when what was acted on no longer exists (404), so the page shows how things are now
export const attempt = (notify, onGone) => async (fn) => {
  try {
    return await fn()
  } catch (e) {
    notify(e.message || 'That did not work. Try again.')
    if (e.status === 404 && onGone) onGone()
  }
}

// A failed action: what went wrong, and a way to try again unless the daily limit was reached
export function ErrorRetry({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="row error" role="alert" style={{ marginTop: 10 }}>
      <span>{error.message || String(error)}</span>
      {onRetry && error.status !== 429 && <button className="btn ghost small" onClick={onRetry}>Retry</button>}
    </div>
  )
}

export function Empty({ title, body, action, onAction }) {
  return (
    <div className="card empty">
      <h2>{title}</h2>
      {body && <p className="muted">{body}</p>}
      {action && <button className="btn" onClick={onAction}>{action}</button>}
    </div>
  )
}

export function Meter({ value }) {
  return (
    <div className="meter">
      <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  )
}

export const initials = (name) => (name || '?').split(' ').filter(Boolean).map((w) => w[0]).slice(0, 2).join('').toUpperCase() || '?'
export function Avatar({ name, size = '' }) {
  return <span className={`avatar ${size}`} aria-hidden>{initials(name)}</span>
}

const pad = (n) => String(n).padStart(2, '0')
// Dates are handled as local calendar days ("2026-10-12"), never as UTC instants
export const isoDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
export const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d }
export const parseDay = (iso) => { const [y, m, d] = iso.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d) }
export const daysUntil = (iso) => Math.round((parseDay(iso) - today()) / 86400000)
export const pct = (x) => `${Math.round(x * 100)}%`
export const fmtDate = (iso, opts = { day: 'numeric', month: 'short' }) => parseDay(iso).toLocaleDateString('en-GB', opts)
export const fmtMonth = (iso) => fmtDate(iso, { month: 'short', year: 'numeric' })
// When a job or course ran: "Jul 2023 to Aug 2025", "Jul 2023 to present", or nothing if no dates were given
export const period = (e) => {
  const end = e.is_current ? 'present' : e.end_month ? fmtMonth(e.end_month) : ''
  if (e.start_month) return end ? `${fmtMonth(e.start_month)} to ${end}` : `From ${fmtMonth(e.start_month)}`
  return e.is_current ? 'Current' : end ? `Until ${end}` : ''
}
export const VISA_LABEL = { student: 'Student', graduate: 'Graduate' }
// An achievement's quote is labelled by where it really came from
export const QUOTE_LABEL = { voice: 'You said', paste: 'You wrote', cv: 'From your CV', github: 'From your repository' }
export const FIT_LABEL = { direct: 'Direct fit', near: 'Near fit', stretch: 'Stretch', none: 'Not a match' }
export const money = (n) => `£${Math.round(n).toLocaleString('en-GB')}`
export const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

// Live adverts for one targeted role family: how many, what they pay, how many employers can sponsor
function marketLine(m) {
  if (!m || !m.jobs) return 'No live jobs found yet.'
  const parts = [`${plural(m.jobs, 'live job')}.`]
  if (m.salary_n) parts.push(`Median advertised salary ${money(m.salary_median)} from ${plural(m.salary_n, 'advert')}.`)
  if (m.named) parts.push(`${m.listed} of ${plural(m.named, 'named employer')} ${m.listed === 1 ? 'is' : 'are'} on the sponsor register.`)
  return parts.join(' ')
}

// One AI-suggested role family: fit, estimated overlap, and what the user already shows or lacks
export function FamilyCard({ f, onToggle, market, onJobs }) {
  return (
    <article className={`card family ${f.targeted ? 'selected' : ''}`}>
      <div className="row">
        <span className="fit">{FIT_LABEL[f.fit]}</span>
        <span className="spacer" />
        <label className="check"><input type="checkbox" checked={f.targeted} onChange={() => onToggle(f)} />Targeting</label>
      </div>
      <h3 style={{ fontSize: 17 }}>{f.name}</h3>
      <div className="row small"><span style={{ width: 170 }}>{f.overlap}% overlap (AI estimate)</span><span style={{ flex: 1 }}><Meter value={f.overlap} /></span></div>
      {f.why && <p className="small">{f.why}</p>}
      {f.uk_titles.length > 0 && <p className="small muted">UK job titles: {f.uk_titles.join(', ')}</p>}
      {f.targeted && onJobs && (
        <p className="small market">{marketLine(market)} <button className="linkish" onClick={onJobs}>See jobs</button></p>
      )}
      <div className="stack" style={{ gap: 8 }}>
        {f.needs.map((n) => (
          <div key={n.need} className="need">
            <span className={`mark ${n.shown_by ? 'yes' : 'no'}`}>{n.shown_by ? <Check size={13} strokeWidth={3} /> : ''}</span>
            <div>
              <div className={n.shown_by ? '' : 'strong'}>{n.need}</div>
              <div className="small muted">{n.shown_by ? `Shown by: ${n.shown_by}` : 'Gap'}</div>
            </div>
          </div>
        ))}
      </div>
    </article>
  )
}

// The user's own words an achievement was built from. Shown only when they were found in the source
export function Quote({ a, style }) {
  if (!a.raw) return null
  return <p className="said" style={style}>{QUOTE_LABEL[a.source] || QUOTE_LABEL.voice}: "{a.raw}"</p>
}

export function Brand({ onClick }) {
  return (
    <button className="brand" onClick={onClick} aria-label="UK Career Navigator home">
      <span className="brand-mark"><Compass size={18} /></span>
      <span>
        <span className="brand-name">UK Career Navigator</span>
        <span className="brand-sub">for international students and graduates</span>
      </span>
    </button>
  )
}
