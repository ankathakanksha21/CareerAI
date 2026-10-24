import { useState } from 'react'
import { post } from '../api'
import { PageHead, attempt, fmtDate } from '../ui'
import PeerConsent from '../components/PeerConsent'
import PeerGroup, { ContactLinkBox, Proposal } from '../components/PeerGroup'

function Off({ p, onJoin }) {
  return (
    <section className="card empty">
      <h2>Job hunting is easier with company</h2>
      <p className="muted">Join a buddy group of two or three people in a similar position. Each week you see whether the others kept going, nudge them, and share one line about your focus. There is no chat, and nobody sees your applications.</p>
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
          ? <p>We have suggested {p.options.proposals_a_day} possible buddies for you today, the most in one day. We will look again tomorrow.</p>
          : <p>We will match you when someone joins. Nobody is invented: until then, you wait here.</p>}
        {p.waiting_since && <p className="small muted">On the list since {fmtDate(p.waiting_since.slice(0, 10), { day: 'numeric', month: 'long' })}.</p>}
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
  return (
    <>
      <PageHead title="Peers" lede="A small buddy group of people in the same position as you, to keep each other going. Your group sees your first name, university, course, target roles and weekly progress, and anything you choose to share. Never your visa, applications or CVs." />
      {p.status === 'off' && (joining && !p.barred
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
