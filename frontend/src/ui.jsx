import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { BookOpen, BriefcaseBusiness, Check, ChevronDown, Compass, FileText, Handshake, House, Info, Mic, Search, UserRound, Users } from 'lucide-react'

// Sidebar. key = route, label = what the user sees. Pages return here as their step goes live
export const NAV = [
  { key: 'home', label: 'This week', icon: House },
  { key: 'profile', label: 'Profile', icon: UserRound },
  { key: 'pathways', label: 'Pathways', icon: Compass },
  { key: 'jobs', label: 'Jobs', icon: Search },
  { key: 'resume', label: 'CV', icon: FileText },
  { key: 'interview', label: 'Interview', icon: Mic },
  { key: 'applications', label: 'Applications', icon: BriefcaseBusiness },
  { key: 'networking', label: 'Networking', icon: Users },
  { key: 'peers', label: 'Peers', icon: Handshake },
  { key: 'journal', label: 'Journal', icon: BookOpen },
]
export const PAGE_LABEL = Object.fromEntries(NAV.map((i) => [i.key, i.label]))

// info, if given, is a page's subtitle tucked behind an (i) beside the title. It opens on click, tap or Enter
export function PageHead({ title, lede, info, infoLabel = 'About this page', children }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <header className="page-head">
      <div style={{ flex: 1, minWidth: 260 }}>
        <div className="page-title">
          <h1>{title}</h1>
          {info && <InfoButton open={open} label={infoLabel} controls={id} onClick={() => setOpen(!open)} />}
        </div>
        {lede && <p className="lede">{lede}</p>}
        {info && <div id={id} className="lede" hidden={!open}>{info}</div>}
      </div>
      {children}
    </header>
  )
}

// The (i) button. Icon only, so it carries its words in aria-label and title
export function InfoButton({ open, label, controls, onClick }) {
  return (
    <button type="button" className={`info-btn ${open ? 'open' : ''}`} aria-label={label} title={label} aria-expanded={open} aria-controls={controls} onClick={onClick}>
      <Info size={16} aria-hidden="true" />
    </button>
  )
}

// Whether the person has asked their device for less motion: then nothing waits for an animation to finish
const lessMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// Open at once; close after the closing animation (index.css .closing), so a toggle or note leaves as gently as it came
function useOpenClose(initial, closeMs) {
  const [open, setOpen] = useState(initial)
  const [closing, setClosing] = useState(false)
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])
  const close = useCallback(() => {
    if (lessMotion()) { setOpen(false); return }
    setClosing(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => { setOpen(false); setClosing(false) }, closeMs)
  }, [closeMs])
  const openNow = () => { clearTimeout(timer.current); setClosing(false); setOpen(true) }
  return { open, closing, shown: open && !closing, openNow, close }
}

// A short explanation tucked behind an (i). It opens on click, tap or Enter, closes on Escape or a click elsewhere,
// and is kept inside the screen on a phone
export function InfoTip({ label = 'More information', children }) {
  const { open, closing, shown, openNow, close } = useOpenClose(false, 150)
  const id = useId()
  const box = useRef(null)
  const pop = useRef(null)
  useEffect(() => {
    if (!shown) return
    const away = (e) => { if (!box.current?.contains(e.target)) close() }
    const esc = (e) => { if (e.key === 'Escape') close() }
    document.addEventListener('pointerdown', away)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc) }
  }, [shown, close])
  useLayoutEffect(() => {
    const el = pop.current
    if (!open || !el) return
    const r = el.getBoundingClientRect()
    const shift = Math.min(0, window.innerWidth - 16 - r.right) || Math.max(0, 16 - r.left)
    if (shift) el.style.translate = `${shift}px 0`
  }, [open])
  return (
    <span className="info" ref={box}>
      <InfoButton open={shown} label={label} controls={shown ? id : undefined} onClick={() => (shown ? close() : openNow())} />
      {open && <span id={id} ref={pop} role="note" className={`info-pop ${closing ? 'closing' : ''}`}>{children}</span>}
    </span>
  )
}

// Longer text tucked behind a toggle, closed unless defaultOpen. With no label the toggle reads Show more / Show less.
// heading ('h2', 'h3') wraps the toggle in a heading, so a section title can open its own section
export function ShowMore({ label, openLabel, heading: Heading, defaultOpen = false, buttonClassName = 'linkish small', className = '', children }) {
  const { open, closing, shown, openNow, close } = useOpenClose(defaultOpen, 220)
  const id = useId()
  const text = shown ? (openLabel || label || 'Show less') : (label || 'Show more')
  const toggle = (
    <button type="button" className={`showmore-btn ${buttonClassName}`} aria-expanded={shown} aria-controls={id} onClick={() => (shown ? close() : openNow())}>
      {text}<ChevronDown size={15} aria-hidden="true" className={shown ? 'flip' : ''} />
    </button>
  )
  return (
    <div className={`showmore ${className}`}>
      {Heading ? <Heading className="showmore-head">{toggle}</Heading> : toggle}
      <div id={id} className={`showmore-body ${closing ? 'closing' : ''}`} hidden={!open}>{children}</div>
    </div>
  )
}

// Short facts as chips. label is a small muted word before them; tone is '', 'muted', 'good', 'warn' or 'bad'.
// Anything passed as children (a link, say) follows the chips on the same line
export function Chips({ label, items, tone = '', className = '', children }) {
  const id = useId()
  if (!items?.length) return null
  return (
    <div className={`chips ${className}`}>
      {label && <span className="chips-label" id={id}>{label}</span>}
      <ul className="chips-list" aria-labelledby={label ? id : undefined}>
        {items.map((x, i) => <li key={i} className={`chip ${tone}`}>{x}</li>)}
      </ul>
      {children}
    </div>
  )
}

// A small busy circle. Its label is read out to screen readers instead of being shown
export function Spinner({ label = 'Loading' }) {
  return <span className="spinner" role="status"><span className="sr-only">{label}</span></span>
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

// icon, if given, is a lucide icon shown above the heading
export function Empty({ icon: Icon, title, body, action, onAction }) {
  return (
    <div className="card empty">
      {Icon && <span className="icon-box" aria-hidden="true"><Icon size={20} /></span>}
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

// Live adverts for one targeted role family, as chips: how many, what they advertise, how many named employers are on the sponsor register
function marketChips(m) {
  const items = [plural(m.jobs, 'live job')]
  if (m.salary_n) items.push(`Median advertised ${money(m.salary_median)} from ${plural(m.salary_n, 'advert')}`)
  if (m.named) items.push(`${m.listed} of ${plural(m.named, 'named employer')} on the sponsor register`)
  return items
}

// One AI-suggested role family: fit, estimated overlap, and what the user already shows or lacks.
// Every need stays in view; what shows each met need is one tap away behind Show evidence
export function FamilyCard({ f, onToggle, market, onJobs }) {
  const [evidence, setEvidence] = useState(false)
  const needsId = useId()
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
      <Chips label="UK titles" items={f.uk_titles} tone="muted" />
      {f.targeted && onJobs && (market?.jobs
        ? <Chips items={marketChips(market)} className="market"><button className="linkish small" onClick={onJobs}>See jobs</button></Chips>
        : <p className="small market">No live jobs found yet. <button className="linkish" onClick={onJobs}>See jobs</button></p>
      )}
      <ul className="plain stack" id={needsId} style={{ gap: 8 }}>
        {f.needs.map((n) => (
          <li key={n.need} className="need">
            <span className={`mark ${n.shown_by ? 'yes' : 'no'}`} aria-hidden="true">{n.shown_by ? <Check size={13} strokeWidth={3} /> : ''}</span>
            <div>
              <div className={n.shown_by ? '' : 'strong'}>{n.need}{!n.shown_by && <span className="sr-only"> (Gap)</span>}</div>
              {n.shown_by && evidence && <div className="small muted"><span className="sr-only">Shown by: </span>{n.shown_by}</div>}
            </div>
          </li>
        ))}
      </ul>
      {f.needs.some((n) => n.shown_by) && (
        <button type="button" className="linkish small showmore-btn family-evidence" aria-expanded={evidence} aria-controls={needsId} onClick={() => setEvidence(!evidence)}>
          {evidence ? 'Hide evidence' : 'Show evidence'}<ChevronDown size={15} aria-hidden="true" className={evidence ? 'flip' : ''} />
        </button>
      )}
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
      <span className="brand-name">UK Career Navigator</span>
    </button>
  )
}
