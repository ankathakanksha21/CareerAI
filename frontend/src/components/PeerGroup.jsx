import { useState } from 'react'
import { Check, ExternalLink } from 'lucide-react'
import { post, put } from '../api'
import { Avatar, ErrorRetry, attempt, fmtDate, plural } from '../ui'

const linkName = (url) => (url.startsWith('https://wa.me/') ? 'WhatsApp' : 'LinkedIn')
const names = (members) => members.map((m) => m.first_name).join(' and ')

// What anyone may see of a member: first name, university, course and target roles
function Who({ m }) {
  return (
    <div className="head">
      <Avatar name={m.first_name} />
      <div>
        <div className="name">{m.first_name}</div>
        <div className="headline">{[m.course, m.university].filter(Boolean).join(', ')}</div>
        {m.target_roles.length > 0 && <div className="small muted">Aiming for {m.target_roles.join(', ')}</div>}
      </div>
    </div>
  )
}

// A report goes to the app's owner. A reported line disappears for the person who reported it straight away
function ReportForm({ s, member, checkin, refresh, notify, onDone }) {
  const [reason, setReason] = useState('')
  const [details, setDetails] = useState('')
  const [error, setError] = useState(null)
  const send = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await post('/api/peers/report', { member: member.member, reason, details, checkin_id: checkin?.id || null })
      onDone()
      await refresh()
      notify('Report sent. Thank you for telling us.')
    } catch (err) {
      setError(err)
    }
  }
  return (
    <form className="sub-block stack" onSubmit={send}>
      <h4>{checkin ? `Report ${member.first_name}'s line` : `Report ${member.first_name}`}</h4>
      {s.peers.options.report_reasons.map(([k, l]) => (
        <label key={k} className="check"><input type="radio" name={`reason-${member.member}`} value={k} checked={reason === k} onChange={() => setReason(k)} />{l}</label>
      ))}
      <label className="field">Anything else we should know (optional)<textarea rows={2} maxLength={500} value={details} onChange={(e) => setDetails(e.target.value)} /></label>
      <div className="row">
        <button className="btn small" type="submit" disabled={!reason}>Send report</button>
        <button className="btn ghost small" type="button" onClick={onDone}>Cancel</button>
      </div>
      <ErrorRetry error={error} />
    </form>
  )
}

// Block: the two of you are never shown to or matched with each other again
function blockAndLeave(m, refresh, notify, safely, inGroup) {
  const words = inGroup ? `Block ${m.first_name} and leave this group? You will never be matched with them again, and you go back on the list for a new group.`
    : `Block ${m.first_name}? You will never be matched with them again.`
  if (!window.confirm(words)) return
  safely(async () => { await post('/api/peers/block', { member: m.member }); await refresh(); notify(`${m.first_name} blocked`) })
}

function MemberCard({ s, g, m, refresh, notify }) {
  const [reporting, setReporting] = useState(null) // 'member' | 'line'
  const safely = attempt(notify)
  const met = m.progress.met === m.progress.of
  const nudge = () => safely(async () => { await post(`/api/peers/groups/${g.id}/nudge`, { to: m.member }); await refresh(); notify(`Nudge sent to ${m.first_name}`) })
  return (
    <article className="card peer">
      <Who m={m} />
      <div className="row small" style={{ gap: 14, flexWrap: 'wrap' }}>
        <span className={`chip ${met ? 'good' : ''}`}>{met && <Check size={12} strokeWidth={3} />} {m.progress.met} of {m.progress.of} targets met this week</span>
        <span>Streak: {plural(m.streak, 'week')}</span>
      </div>
      {m.checkin ? (
        <p className="said">This week: "{m.checkin.text}" <button className="linkish small" onClick={() => setReporting('line')}>Report</button></p>
      ) : <p className="small muted">No line from {m.first_name} to show this week.</p>}
      {m.inactive && <p className="small">{m.first_name} has not done anything that counts for three weeks. You can leave and find a new group below.</p>}
      <div className="row" style={{ flexWrap: 'wrap' }}>
        <button className="btn small" disabled={m.nudged_today} onClick={nudge}>{m.nudged_today ? 'Nudged today' : 'Send a nudge'}</button>
        {m.contact_link && <a className="btn ghost small" href={m.contact_link} target="_blank" rel="noopener noreferrer">{linkName(m.contact_link)} <ExternalLink size={12} /></a>}
        <span className="spacer" />
        <button className="linkish small" onClick={() => setReporting('member')}>Report</button>
        <button className="linkish small" onClick={() => blockAndLeave(m, refresh, notify, safely, true)}>Block and leave</button>
      </div>
      {reporting && <ReportForm s={s} member={m} checkin={reporting === 'line' ? m.checkin : null} refresh={refresh} notify={notify} onDone={() => setReporting(null)} />}
    </article>
  )
}

// A proposal: who they are, and yes or not this time. Nothing more is shown until everyone has said yes
export function Proposal({ s, p, refresh, notify }) {
  const [reporting, setReporting] = useState(null)
  const safely = attempt(notify)
  const answer = (yes) => safely(async () => {
    await post(`/api/peers/groups/${p.group_id}/${yes ? 'accept' : 'decline'}`)
    await refresh()
    notify(yes ? 'You said yes' : 'Not this time. We will look for someone else.')
  })
  return (
    <section className="card stack">
      <p className="kicker">{p.members.length > 1 ? 'We found a group for you' : 'We found a buddy for you'}</p>
      {p.members.map((m) => (
        <div key={m.member} className="peer">
          <Who m={m} />
          <div className="row">
            <span className="spacer" />
            <button className="linkish small" onClick={() => setReporting(m)}>Report</button>
            <button className="linkish small" onClick={() => blockAndLeave(m, refresh, notify, safely, false)}>Block</button>
          </div>
          {reporting?.member === m.member && <ReportForm s={s} member={m} refresh={refresh} notify={notify} onDone={() => setReporting(null)} />}
        </div>
      ))}
      {p.said_yes ? (
        <p className="small">You said yes. Waiting for {names(p.members)} to answer, until {fmtDate(p.expires_on, { day: 'numeric', month: 'long' })}.</p>
      ) : (
        <>
          <p className="small muted">If you say yes and so do they, you will see each other's weekly progress and check-ins. Nothing else.</p>
          <div className="row">
            <button className="btn" onClick={() => answer(true)}>Accept</button>
            <button className="btn ghost" onClick={() => answer(false)}>Not this time</button>
          </div>
        </>
      )}
    </section>
  )
}

function Newcomer({ g, n, refresh, notify }) {
  const safely = attempt(notify)
  const answer = (yes) => safely(async () => {
    await post(`/api/peers/groups/${g.id}/${yes ? 'accept' : 'decline'}`)
    await refresh()
    notify(yes ? 'You said yes' : `${n.first_name} will not join`)
  })
  return (
    <section className="card tint stack">
      <p className="kicker">Someone could join your group</p>
      <div className="peer"><Who m={n} /></div>
      {n.said_yes ? <p className="small">You said yes. They join once everyone has, by {fmtDate(n.expires_on, { day: 'numeric', month: 'long' })}.</p> : (
        <div className="row">
          <button className="btn small" onClick={() => answer(true)}>Accept</button>
          <button className="btn ghost small" onClick={() => answer(false)}>Not this time</button>
        </div>
      )}
    </section>
  )
}

function CheckinBox({ g, me, refresh, notify }) {
  const [text, setText] = useState(me.checkin?.text || '')
  const [error, setError] = useState(null)
  const save = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await put(`/api/peers/groups/${g.id}/checkin`, { text })
      await refresh()
      notify('Your line for this week is saved')
    } catch (err) {
      setError(err)
    }
  }
  return (
    <form className="stack" onSubmit={save}>
      <label className="field">What is your focus this week?
        <input type="text" maxLength={140} value={text} onChange={(e) => setText(e.target.value)} placeholder="Two tailored applications and one mock interview" />
        <span className="small muted">{140 - text.length} characters left. You can change it until Sunday.</span>
      </label>
      <div><button className="btn small" type="submit" disabled={!text.trim() || text === me.checkin?.text}>Save</button></div>
      <ErrorRetry error={error} />
    </form>
  )
}

export function ContactLinkBox({ p, refresh, notify }) {
  const [link, setLink] = useState(p.contact_link || '')
  const [error, setError] = useState(null)
  const save = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await put('/api/peers/contact-link', { link })
      await refresh()
      notify(link ? 'Contact link saved' : 'Contact link removed')
    } catch (err) {
      setError(err)
    }
  }
  return (
    <form className="stack" onSubmit={save}>
      <label className="field">Share a contact link (optional)
        <input type="text" maxLength={300} value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://www.linkedin.com/in/your-name or https://wa.me/447700900123" />
        <span className="small muted">Only the people in your group see it. A WhatsApp link shows them your phone number.</span>
      </label>
      <div><button className="btn ghost small" type="submit" disabled={link === (p.contact_link || '')}>{!link && p.contact_link ? 'Remove link' : 'Save link'}</button></div>
      <ErrorRetry error={error} />
    </form>
  )
}

// The group: everyone's week, the group streak, this week's lines, nudges, and the ways out
export default function PeerGroup({ s, refresh, notify, switchOff }) {
  const p = s.peers
  const g = p.group
  const safely = attempt(notify)
  const leave = (words) => {
    if (!window.confirm(words)) return
    safely(async () => { await post(`/api/peers/groups/${g.id}/leave`); await refresh(); notify('You left the group') })
  }
  const quiet = g.members.some((m) => m.inactive)
  return (
    <div className="grid split">
      <div className="stack">
        <section className="card">
          <div className="row"><h2>Your group</h2><span className="spacer" /><span className="chip good">Group streak: {plural(g.streak, 'week')}</span></div>
          <p className="small muted">The weeks in a row in which everyone met all their targets.</p>
        </section>
        {g.newcomer && <Newcomer g={g} n={g.newcomer} refresh={refresh} notify={notify} />}
        {g.members.map((m) => <MemberCard key={m.member} s={s} g={g} m={m} refresh={refresh} notify={notify} />)}
      </div>
      <div className="stack">
        {p.nudges.length > 0 && (
          <section className="card">
            <h2>Nudges this week</h2>
            <div className="list" style={{ marginTop: 10 }}>{p.nudges.map((n) => <p key={n.first_name} className="small">{n.text}</p>)}</div>
          </section>
        )}
        <section className="card stack">
          <h2>You</h2>
          <p className="small">{g.me.progress.met} of {g.me.progress.of} targets met this week. Streak: {plural(g.me.streak, 'week')}.</p>
          <CheckinBox g={g} me={g.me} refresh={refresh} notify={notify} />
          <ContactLinkBox p={p} refresh={refresh} notify={notify} />
        </section>
        <section className="card stack">
          <h2>Leave or stop</h2>
          {quiet && <button className="btn small" onClick={() => leave('Find a new group? You leave this one and go back on the list.')}>Find a new group</button>}
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <button className="btn ghost small" onClick={() => leave('Leave this group? You go back on the list for a new group. To stop altogether, switch Peers off.')}>Leave group</button>
            <button className="btn ghost small" onClick={switchOff}>Switch Peers off</button>
          </div>
        </section>
      </div>
    </div>
  )
}
