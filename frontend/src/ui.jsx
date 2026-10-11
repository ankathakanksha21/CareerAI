import { useRef, useState } from 'react'
import { BookOpen, BriefcaseBusiness, Check, Compass, FileText, House, Mic, UserRound } from 'lucide-react'

// Sidebar. key = route, label = what the user sees. Pages return here as their step goes live
export const NAV = [
  { key: 'home', label: 'This week', icon: House },
  { key: 'profile', label: 'Profile', icon: UserRound },
  { key: 'pathways', label: 'Career pathways', icon: Compass },
  { key: 'resume', label: 'Resume', icon: FileText },
  { key: 'interview', label: 'Interview coach', icon: Mic },
  { key: 'applications', label: 'Applications', icon: BriefcaseBusiness },
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
export const VISA_LABEL = { student: 'Student', graduate: 'Graduate' }
export const FIT_LABEL = { direct: 'Direct fit', near: 'Near fit', stretch: 'Stretch' }

// One AI-suggested role family: fit, estimated overlap, and what the user already shows or lacks
export function FamilyCard({ f, onToggle }) {
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
