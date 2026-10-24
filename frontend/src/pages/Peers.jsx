import { useState } from 'react'
import { BellRing, CalendarCheck, Clock, Eye, EyeOff, PenLine } from 'lucide-react'
import { post } from '../api'
import { PageHead, attempt, fmtDate } from '../ui'
import PeerConsent from '../components/PeerConsent'
import PeerGroup, { ContactLinkBox, Proposal } from '../components/PeerGroup'

const INTRO = 'A buddy group of two or three people in your position, to keep each other going.'

// What the group sees of the user, and never sees. Spans, so the rows can sit inside the page's lede
function Sees() {
  return (
    <span className="peers-sees">
      <span className="peers-sees-row"><Eye size={15} aria-hidden="true" /><span>Your group sees: first name, university, course, target roles, weekly progress and anything you share.</span></span>
      <span className="peers-sees-row"><EyeOff size={15} aria-hidden="true" /><span>Never: your visa, applications or CVs.</span></span>
    </span>
  )
}

function Off({ p, onJoin }) {
  return (
    <section className="card empty">
      <h2>Buddy groups</h2>
      <ul className="peers-features">
        <li><CalendarCheck size={16} aria-hidden="true" />See who kept going each week</li>
        <li><BellRing size={16} aria-hidden="true" />Send a nudge</li>
        <li><PenLine size={16} aria-hidden="true" />Share your weekly focus in one line</li>
      </ul>
      <p className="small muted">No chat.</p>
      {p.barred ? <p className="strong">You can't join buddy groups.</p> : <button className="btn" onClick={onJoin}>Join a buddy group</button>}
    </section>
  )
}

function Waiting({ s, refresh, notify, switchOff }) {
  const p = s.peers
  return (
    <div className="grid split">
      <section className="card stack">
        <h2>You are on the list</h2>
        {p.again_tomorrow
          ? <p>{p.options.proposals_a_day} possible buddies suggested today, the most in one day. We will look again tomorrow.</p>
          : <p>We will match you when someone joins. We never show invented people.</p>}
        {p.waiting_since && (
          <div>
            <span className="chip muted" title="On the list since">
              <Clock size={12} aria-hidden="true" /><span className="sr-only">On the list </span>Since {fmtDate(p.waiting_since.slice(0, 10), { day: 'numeric', month: 'long' })}
            </span>
          </div>
        )}
        <div><button className="btn ghost small" onClick={switchOff}>Switch Peers off</button></div>
      </section>
      <section className="card"><ContactLinkBox p={p} refresh={refresh} notify={notify} /></section>
    </div>
  )
}

// Buddy groups: off until the user consents; then on the list, a proposal, or a group
export default function Peers({ s, refresh, notify }) {
  const p = s.peers
  const [joining, setJoining] = useState(false)
  const safely = attempt(notify, refresh)
  const switchOff = () => {
    if (!window.confirm('Switch Peers off? You leave your group straight away, and your check-ins and nudges disappear for the others.')) return
    safely(async () => { await post('/api/peers/leave-all'); setJoining(false); await refresh(); notify('Peers is off') })
  }
  const consenting = p.status === 'off' && joining && !p.barred
  // what the group sees: in view while Peers is off, left to the consent screen's full lists, then one tap away once on
  const head = p.status === 'off'
    ? <PageHead title="Peers" lede={consenting ? INTRO : <>{INTRO}<Sees /></>} />
    : <PageHead title="Peers" lede={INTRO} info={<Sees />} infoLabel="What your group sees" />
  return (
    <>
      {head}
      {p.status === 'off' && (consenting
        ? <PeerConsent s={s} refresh={refresh} notify={notify} onCancel={() => setJoining(false)} />
        : <Off p={p} onJoin={() => setJoining(true)} />)}
      {p.status === 'waiting' && <Waiting s={s} refresh={refresh} notify={notify} switchOff={switchOff} />}
      {p.status === 'proposed' && (
        <div className="grid split">
          <Proposal s={s} p={p.proposal} refresh={refresh} notify={notify} />
          <section className="card stack">
            <ContactLinkBox p={p} refresh={refresh} notify={notify} />
            <div><button className="btn ghost small" onClick={switchOff}>Switch Peers off</button></div>
          </section>
        </div>
      )}
      {p.status === 'group' && <PeerGroup s={s} refresh={refresh} notify={notify} switchOff={switchOff} />}
    </>
  )
}
