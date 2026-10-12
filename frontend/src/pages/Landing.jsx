import { BriefcaseBusiness, Compass, FileText, Mic } from 'lucide-react'
import { Brand } from '../ui'

const FEATURES = [
  { icon: FileText, title: 'UK-standard CV and cover letter', body: 'Your experience rewritten in the words UK recruiters scan for, then tailored to each job you paste in.' },
  { icon: Mic, title: 'Interview practice', body: 'Voice mock interviews for HR screens, behavioural rounds and job-specific questions, with feedback on your answers.' },
  { icon: BriefcaseBusiness, title: 'Application tracker', body: 'A board for every application, and a plain answer to what is not working.' },
  { icon: Compass, title: 'Career pathways', body: 'Role families that fit your background, with UK job titles and the gaps to close.' },
]

// The same six steps a new account sees, shown as an example
const PREVIEW = [
  ['Build your profile', true], ['Pick your target roles', true], ['Add a job you want', false],
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
          <h1>A clear plan for your UK job search.</h1>
          <p className="lede">For international students and recent graduates in the UK. Turn your experience into UK-standard applications, practise interviews out loud, and see why applications are or are not working.</p>
          <div className="row">
            <button className="btn large" onClick={start}>{signedIn ? 'Open dashboard' : 'Get started'}</button>
          </div>
          <p className="fine">Takes about three minutes. Talk to our coach or paste your CV.</p>
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
        <h2>What you can do</h2>
        <p>Four tools that share one profile, so each one knows what the others found.</p>
        <div className="grid cols-2">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="card feature" style={{ cursor: 'default' }}>
              <span className="icon-box"><Icon size={19} /></span>
              <h3>{title}</h3>
              <p>{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="land-section" id="how">
        <h2>How it works</h2>
        <p>From your background to a tracked search.</p>
        <div className="steps3">
          <div><h3>Tell us your background</h3><p>Talk to our careers coach for a few minutes, or paste your CV. We turn it into evidence UK employers understand.</p></div>
          <div><h3>See what employers look for</h3><p>Your profile against the roles you target: what you already show, and the gaps to close.</p></div>
          <div><h3>Apply, practise, track</h3><p>Tailor a CV to each job, rehearse the interview, and let the tracker show what to change.</p></div>
        </div>
        <div className="row" style={{ marginTop: 28 }}><button className="btn large" onClick={start}>{signedIn ? 'Open dashboard' : 'Get started'}</button></div>
      </section>

      <footer className="land-foot"><a href="#privacy">Privacy</a></footer>
    </div>
  )
}
