import { BriefcaseBusiness, Compass, FileText, Mic } from 'lucide-react'
import { Brand, Chips } from '../ui'

const FEATURES = [
  { icon: FileText, title: 'UK-standard CV and cover letter', body: 'A two-page UK CV built from your own records and tailored to each job. Edit on screen, download as Word or PDF.' },
  { icon: Mic, title: 'Interview practice', body: 'Voice mock interviews with feedback on your answers.', chips: ['HR screen', 'Behavioural', 'Job-specific'] },
  { icon: BriefcaseBusiness, title: 'Application tracker', body: 'Every application on one board, and what to fix.' },
  { icon: Compass, title: 'Career pathways and jobs', body: 'Roles that fit your background, then live adverts matched to your profile and checked against the gov.uk sponsor register.' },
]

// The same six steps a new account sees, shown as an example
const PREVIEW = [
  ['Build your profile', true], ['Pick your target roles', true], ['Save a job you want', false],
  ['Tailor a CV for it', false], ['Practise an interview', false], ['Log your first application', false],
]

export default function Landing({ go, signedIn }) {
  const start = () => (signedIn ? go('home') : go('auth', 'signup'))
  return (
    <div className="landing">
      <header className="topbar">
        <Brand onClick={() => go('landing')} />
        <span className="spacer" />
        {signedIn
          ? <button className="btn" onClick={() => go('home')}>Open dashboard</button>
          : <><button className="btn ghost" onClick={() => go('auth', 'signin')}>Sign in</button><button className="btn" onClick={start}>Get started</button></>}
      </header>

      <section className="hero">
        <div>
          <p className="hero-kicker">For international students and recent graduates in the UK</p>
          <h1>A clear plan for your UK job search.</h1>
          <p className="lede">Turn your experience into UK-standard applications, practise interviews out loud, and see what to fix.</p>
          <div className="row">
            <button className="btn large" onClick={start}>{signedIn ? 'Open dashboard' : 'Get started'}</button>
          </div>
          <p className="fine">Takes about three minutes.</p>
        </div>
        <div className="preview" aria-label="Example getting-started checklist">
          <div className="row"><span className="strong">Getting started</span><span className="spacer" /><span className="small muted">Example</span></div>
          {PREVIEW.map(([text, done]) => (
            <div key={text} className="ptask">
              <span className={`box ${done ? 'done' : ''}`} />
              <div style={{ textDecoration: done ? 'line-through' : 'none', color: done ? 'var(--ink-3)' : undefined, fontWeight: 600 }}>{text}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="land-section" id="features">
        <h2>Four tools, one profile</h2>
        <div className="grid cols-2">
          {FEATURES.map(({ icon: Icon, title, body, chips }) => (
            <div key={title} className="card feature" style={{ cursor: 'default' }}>
              <span className="icon-box"><Icon size={19} /></span>
              <h3>{title}</h3>
              <p>{body}</p>
              {chips && <Chips items={chips} tone="muted" />}
            </div>
          ))}
        </div>
      </section>

      <section className="land-section" id="how">
        <h2>How it works</h2>
        <div className="steps3">
          <div><h3>Tell us your background</h3><p>Talk to our coach or add your CV. We turn it into evidence UK employers understand.</p></div>
          <div><h3>See what employers look for</h3><p>What you already show for your target roles, and the gaps to close.</p></div>
          <div><h3>Apply, practise, track</h3><p>Tailor a CV to each job, rehearse the interview, see what to change.</p></div>
        </div>
        <div className="row" style={{ marginTop: 28 }}><button className="btn large" onClick={start}>{signedIn ? 'Open dashboard' : 'Get started'}</button></div>
      </section>

      <footer className="land-foot"><a href="#privacy">Privacy</a><a href="#contact">Contact us</a></footer>
    </div>
  )
}
